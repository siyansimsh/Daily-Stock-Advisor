"""yfinance-based OHLCV data provider with local CSV caching."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, cast

import pandas as pd

try:
    import yfinance as _yf
except ImportError:  # pragma: no cover - exercised only when dependency is missing
    yf: Any | None = None
else:
    yf = _yf


PRICE_COLUMNS = ["Date", "Open", "High", "Low", "Close", "Adj Close", "Volume"]


@dataclass(frozen=True)
class DownloadResult:
    ticker: str
    status: str
    rows: int
    latest_date: str | None
    latest_close: float | None
    cache_path: Path
    message: str = ""


class YFinanceProvider:
    """Download daily OHLCV data and cache it under ``data/prices``."""

    def __init__(self, cache_dir: str | Path):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def cache_path(self, ticker: str) -> Path:
        safe_ticker = ticker.replace("/", "_").replace("\\", "_")
        return self.cache_dir / f"{safe_ticker}.csv"

    def fetch_ohlcv(
        self,
        ticker: str,
        period: str = "1y",
        interval: str = "1d",
        force: bool = False,
    ) -> pd.DataFrame:
        """Return OHLCV data for one ticker, using today's cache when available."""

        ticker = ticker.strip()
        if not ticker:
            raise ValueError("ticker must not be empty")

        cache_path = self.cache_path(ticker)
        if cache_path.exists() and not force and self._cache_is_fresh(cache_path):
            return self._read_cache(cache_path)

        data = self._download(ticker=ticker, period=period, interval=interval)
        self._write_cache(data, cache_path)
        return data

    def update_tickers(
        self,
        tickers: Iterable[str],
        period: str = "1y",
        interval: str = "1d",
        force: bool = False,
    ) -> list[DownloadResult]:
        """Download or refresh all tickers and return per-ticker statuses."""

        results: list[DownloadResult] = []
        for ticker in sorted({item.strip() for item in tickers if str(item).strip()}):
            cache_path = self.cache_path(ticker)
            try:
                data = self.fetch_ohlcv(
                    ticker=ticker,
                    period=period,
                    interval=interval,
                    force=force,
                )
                latest = data.iloc[-1] if not data.empty else None
                results.append(
                    DownloadResult(
                        ticker=ticker,
                        status="ok",
                        rows=len(data),
                        latest_date=str(latest["Date"].date()) if latest is not None else None,
                        latest_close=float(latest["Close"]) if latest is not None else None,
                        cache_path=cache_path,
                    )
                )
            except Exception as exc:  # noqa: BLE001 - CLI should report every ticker failure
                results.append(
                    DownloadResult(
                        ticker=ticker,
                        status="error",
                        rows=0,
                        latest_date=None,
                        latest_close=None,
                        cache_path=cache_path,
                        message=str(exc),
                    )
                )
        return results

    def _download(self, ticker: str, period: str, interval: str) -> pd.DataFrame:
        yf_module = yf
        if yf_module is None:
            raise RuntimeError("yfinance is not installed. Run: pip install -r requirements.txt")

        raw = cast(
            pd.DataFrame | None,
            yf_module.download(
                tickers=ticker,
                period=period,
                interval=interval,
                auto_adjust=False,
                progress=False,
                threads=False,
            ),
        )
        if raw is None or raw.empty:
            raise ValueError(f"No price data returned for {ticker}.")

        data = self._normalize_columns(raw, ticker)
        missing = [column for column in PRICE_COLUMNS if column not in data.columns]
        if "Adj Close" in missing and "Close" in data.columns:
            data["Adj Close"] = data["Close"]
            missing.remove("Adj Close")
        if missing:
            raise ValueError(f"Missing expected columns for {ticker}: {missing}")

        data = data[PRICE_COLUMNS].copy()
        data["Date"] = pd.to_datetime(data["Date"]).dt.tz_localize(None)
        numeric_columns = [column for column in PRICE_COLUMNS if column != "Date"]
        data[numeric_columns] = data[numeric_columns].apply(pd.to_numeric, errors="coerce")
        data = data.dropna(subset=["Date", "Close"]).sort_values("Date")
        if data.empty:
            raise ValueError(f"No usable OHLCV rows returned for {ticker}.")
        return data

    def _normalize_columns(self, raw: pd.DataFrame, ticker: str) -> pd.DataFrame:
        data = raw.copy()
        if isinstance(data.columns, pd.MultiIndex):
            if ticker in data.columns.get_level_values(-1):
                data = data.xs(ticker, axis=1, level=-1)
            else:
                data.columns = data.columns.get_level_values(0)

        data = data.reset_index()
        if "Datetime" in data.columns and "Date" not in data.columns:
            data = data.rename(columns={"Datetime": "Date"})
        return data

    def _read_cache(self, cache_path: Path) -> pd.DataFrame:
        return pd.read_csv(cache_path, parse_dates=["Date"])

    def _write_cache(self, data: pd.DataFrame, cache_path: Path) -> None:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        data.to_csv(cache_path, index=False, date_format="%Y-%m-%d")

    def _cache_is_fresh(self, cache_path: Path) -> bool:
        modified = datetime.fromtimestamp(cache_path.stat().st_mtime).date()
        return modified == date.today()
