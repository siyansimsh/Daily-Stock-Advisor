"""Rule-based stock screener for Phase 2."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from src.indicators import add_indicators


RESULT_COLUMNS = [
    "ticker",
    "market",
    "name",
    "close",
    "ma20",
    "ma60",
    "ma120",
    "rsi14",
    "macd",
    "macd_signal",
    "volume_ratio",
    "return_20d",
    "return_60d",
    "volatility",
    "max_drawdown",
    "score",
    "signal",
    "reason",
]


@dataclass(frozen=True)
class ScreenerPaths:
    config_dir: Path
    price_dir: Path
    output_path: Path


def load_universe(config_dir: str | Path) -> pd.DataFrame:
    """Read TW and US universe files and return one normalized table."""

    config_path = Path(config_dir)
    frames = []
    for filename in ("universe_tw.csv", "universe_us.csv"):
        path = config_path / filename
        if not path.exists():
            continue
        data = pd.read_csv(path)
        missing = {"ticker", "market", "name"} - set(data.columns)
        if missing:
            raise ValueError(f"{path} is missing required columns: {sorted(missing)}")
        frames.append(data)

    if not frames:
        return pd.DataFrame(columns=["ticker", "market", "name"])

    universe = pd.concat(frames, ignore_index=True)
    universe["ticker"] = universe["ticker"].astype(str).str.strip()
    return universe.loc[universe["ticker"] != ""].drop_duplicates(subset=["ticker"], keep="first")


def screen_universe(
    settings: dict[str, Any],
    paths: ScreenerPaths,
) -> pd.DataFrame:
    """Screen all configured tickers and write the result CSV."""

    universe = load_universe(paths.config_dir)
    rows = [screen_ticker(record, settings, paths.price_dir) for record in _dataframe_records(universe)]
    result = pd.DataFrame(rows, columns=RESULT_COLUMNS)
    result = result.sort_values(["score", "ticker"], ascending=[False, True], ignore_index=True)

    paths.output_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(paths.output_path, index=False)
    return result


def screen_ticker(
    universe_row: dict[str, Any],
    settings: dict[str, Any],
    price_dir: str | Path,
) -> dict[str, Any]:
    ticker = str(universe_row["ticker"]).strip()
    price_path = _price_path(Path(price_dir), ticker)
    base = {
        "ticker": ticker,
        "market": universe_row.get("market", ""),
        "name": universe_row.get("name", ""),
    }

    if not price_path.exists():
        return _error_row(base, f"missing price file: {price_path.name}")

    prices = pd.read_csv(price_path, parse_dates=["Date"])
    if prices.empty:
        return _error_row(base, "empty price file")

    indicators = add_indicators(prices).dropna(subset=["Close"])
    if indicators.empty:
        return _error_row(base, "no usable price rows")

    latest = indicators.iloc[-1]
    score, signal, reason = score_latest(latest, settings)

    return {
        **base,
        "close": _number(latest.get("Close")),
        "ma20": _number(latest.get("MA20")),
        "ma60": _number(latest.get("MA60")),
        "ma120": _number(latest.get("MA120")),
        "rsi14": _number(latest.get("RSI14")),
        "macd": _number(latest.get("MACD")),
        "macd_signal": _number(latest.get("MACD_signal")),
        "volume_ratio": _number(latest.get("Volume_Ratio")),
        "return_20d": _number(latest.get("Return_20D")),
        "return_60d": _number(latest.get("Return_60D")),
        "volatility": _number(latest.get("Volatility_20D")),
        "max_drawdown": _number(latest.get("Max_Drawdown")),
        "score": score,
        "signal": signal,
        "reason": reason,
    }


def score_latest(latest: pd.Series, settings: dict[str, Any]) -> tuple[int, str, str]:
    screener = settings.get("screener", {}) if isinstance(settings, dict) else {}
    min_volume_ratio = float(screener.get("min_volume_ratio", 1.0))

    score = 0
    reasons: list[str] = []
    close = latest.get("Close")

    if _gt(close, latest.get("MA20")):
        score += 10
        _add_reason(reasons, "close above MA20")
    if _gt(close, latest.get("MA60")):
        score += 10
        _add_reason(reasons, "close above MA60")
    if _gt(close, latest.get("MA120")):
        score += 10
        _add_reason(reasons, "close above MA120")

    if _gt(latest.get("Return_20D"), 0):
        score += 8
        _add_reason(reasons, "positive 20d return")
    if _gt(latest.get("Return_60D"), 0):
        score += 8
        _add_reason(reasons, "positive 60d return")
    if _gt(latest.get("MACD"), latest.get("MACD_signal")):
        score += 4
        _add_reason(reasons, "MACD above signal")

    if _gte(latest.get("Volume_Ratio"), min_volume_ratio):
        score += 10
        _add_reason(reasons, "volume ratio meets threshold")

    rsi = _to_float(latest.get("RSI14"))
    if rsi is not None:
        if 45 <= rsi <= 70:
            score += 15
            _add_reason(reasons, "RSI in healthy range")
        elif 70 < rsi <= 75:
            score += 5
            _add_reason(reasons, "RSI slightly overbought")
        elif rsi > 75:
            score -= 10
            _add_reason(reasons, "RSI overbought")
        elif rsi < 35:
            score -= 5
            _add_reason(reasons, "RSI weak or oversold")

    volatility = _to_float(latest.get("Volatility_20D"))
    if volatility is not None:
        if volatility <= 0.25:
            score += 10
            _add_reason(reasons, "low volatility")
        elif volatility <= 0.45:
            score += 5
            _add_reason(reasons, "moderate volatility")
        else:
            score -= 5
            _add_reason(reasons, "high volatility")

    max_drawdown_value = _to_float(latest.get("Max_Drawdown"))
    if max_drawdown_value is not None:
        if max_drawdown_value >= -0.10:
            score += 10
            _add_reason(reasons, "limited drawdown")
        elif max_drawdown_value >= -0.20:
            score += 5
            _add_reason(reasons, "moderate drawdown")
        else:
            score -= 5
            _add_reason(reasons, "large drawdown risk")

    if _gte(close, latest.get("MA60")):
        score += 5
    elif _gt(latest.get("MA60"), close):
        score -= 10
        _add_reason(reasons, "below MA60")

    score = _clamp_score(score)

    if score >= 80 and rsi is not None and rsi <= 70:
        signal = "BUY"
    elif score >= 70 and rsi is not None and rsi <= 75:
        signal = "WATCH"
    elif score >= 60:
        signal = "WATCH"
    elif score >= 40:
        signal = "NEUTRAL"
    else:
        signal = "AVOID"

    if rsi is not None and rsi > 75:
        if signal == "BUY":
            signal = "WATCH"
        _add_reason(reasons, "trend is strong but RSI is overbought; avoid chasing high")

    return score, signal, "; ".join(reasons) if reasons else "no rules passed"


def _price_path(price_dir: Path, ticker: str) -> Path:
    safe_ticker = ticker.replace("/", "_").replace("\\", "_")
    return price_dir / f"{safe_ticker}.csv"


def _error_row(base: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        **base,
        "close": pd.NA,
        "ma20": pd.NA,
        "ma60": pd.NA,
        "ma120": pd.NA,
        "rsi14": pd.NA,
        "macd": pd.NA,
        "macd_signal": pd.NA,
        "volume_ratio": pd.NA,
        "return_20d": pd.NA,
        "return_60d": pd.NA,
        "volatility": pd.NA,
        "max_drawdown": pd.NA,
        "score": 0,
        "signal": "ERROR",
        "reason": reason,
    }


def _number(value: Any) -> float | None:
    if pd.isna(value):
        return None
    return float(value)


def _to_float(value: Any) -> float | None:
    if pd.isna(value):
        return None
    return float(value)


def _clamp_score(score: int) -> int:
    return max(0, min(100, int(score)))


def _add_reason(reasons: list[str], reason: str) -> None:
    if reason not in reasons:
        reasons.append(reason)


def _gt(left: Any, right: Any) -> bool:
    return not pd.isna(left) and not pd.isna(right) and float(left) > float(right)


def _gte(left: Any, right: Any) -> bool:
    return not pd.isna(left) and not pd.isna(right) and float(left) >= float(right)


def _dataframe_records(data: pd.DataFrame) -> list[dict[str, Any]]:
    return [{str(key): value for key, value in record.items()} for record in data.to_dict("records")]


def _between(value: Any, lower: float, upper: float) -> bool:
    return not pd.isna(value) and lower <= float(value) <= upper
