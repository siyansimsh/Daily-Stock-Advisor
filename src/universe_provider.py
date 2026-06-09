"""Local universe builder for config, watchlist, and portfolio holdings."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


UNIVERSE_COLUMNS = ["ticker", "market", "name", "sector"]
CONFIG_UNIVERSE_FILES = ("universe_tw.csv", "universe_us.csv")
WATCHLIST_FILES = ("watchlist_tw.csv", "watchlist_us.csv")


def load_config_universe(config_dir: str | Path) -> pd.DataFrame:
    """Load the default TW/US universe CSV files from config."""

    return _load_universe_files(Path(config_dir), CONFIG_UNIVERSE_FILES)


def load_watchlist(config_dir: str | Path) -> pd.DataFrame:
    """Load optional local watchlist CSV files from config."""

    return _load_universe_files(Path(config_dir), WATCHLIST_FILES)


def load_portfolio_holdings(portfolio_path: str | Path) -> pd.DataFrame:
    """Load open portfolio positions as universe rows."""

    path = Path(portfolio_path)
    if not path.exists():
        return _empty_universe()

    data = pd.read_csv(path)
    if "ticker" not in data.columns:
        raise ValueError(f"{path} must contain a ticker column")

    rows = data.copy()
    if "shares" in rows.columns:
        shares = pd.to_numeric(rows["shares"], errors="coerce").fillna(0)
        rows = rows.loc[shares > 0].copy()

    result = pd.DataFrame(index=rows.index)
    result["ticker"] = rows["ticker"]
    result["market"] = rows["market"] if "market" in rows.columns else ""

    if "name" in rows.columns:
        result["name"] = rows["name"]
    elif "note" in rows.columns:
        result["name"] = rows["note"]
    else:
        result["name"] = ""

    result["sector"] = rows["sector"] if "sector" in rows.columns else ""
    return result.reindex(columns=UNIVERSE_COLUMNS)


def normalize_universe(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize columns, fill missing fields, and de-duplicate by ticker."""

    if df.empty:
        return _empty_universe()

    data = pd.DataFrame()
    for column in UNIVERSE_COLUMNS:
        if column in df.columns:
            data[column] = df[column]
        else:
            data[column] = ""

    data = data.reset_index(drop=True)
    data["_order"] = data.index
    data["ticker"] = data["ticker"].map(_clean_text)
    data = data.loc[data["ticker"] != ""].copy()
    if data.empty:
        return _empty_universe()

    data["market"] = [
        _normalize_market(market, ticker) for market, ticker in zip(data["market"], data["ticker"], strict=False)
    ]
    data["name"] = data["name"].map(_clean_text)
    data["sector"] = data["sector"].map(_clean_text)
    data["_score"] = data.apply(_completeness_score, axis=1)

    rows: list[dict[str, Any]] = []
    for _, group in data.groupby("ticker", sort=False):
        sorted_group = group.sort_values(["_score", "_order"], ascending=[False, True])
        base = sorted_group.iloc[0].to_dict()
        for column in ("market", "name", "sector"):
            if not _clean_text(base.get(column)):
                replacement = next(
                    (_clean_text(value) for value in sorted_group[column].tolist() if _clean_text(value)),
                    "",
                )
                base[column] = replacement

        ticker = _clean_text(base.get("ticker"))
        market = _normalize_market(base.get("market"), ticker)
        name = _clean_text(base.get("name")) or ticker
        sector = _clean_text(base.get("sector")) or "unknown"
        rows.append({"ticker": ticker, "market": market, "name": name, "sector": sector})

    result = pd.DataFrame(rows, columns=UNIVERSE_COLUMNS)
    return result.sort_values(["market", "ticker"], ignore_index=True)


def build_universe(settings: dict[str, Any], config_dir: str | Path, data_dir: str | Path) -> dict[str, pd.DataFrame]:
    """Build separate TW/US universes from config, watchlist, and portfolio."""

    del settings  # Reserved for future local-only filters.
    config_path = Path(config_dir)
    data_path = Path(data_dir)
    combined = pd.concat(
        [
            load_config_universe(config_path),
            load_watchlist(config_path),
            load_portfolio_holdings(data_path / "portfolio.csv"),
        ],
        ignore_index=True,
    )
    normalized = normalize_universe(combined)
    return {
        "TW": normalized.loc[normalized["market"] == "TW"].reset_index(drop=True),
        "US": normalized.loc[normalized["market"] == "US"].reset_index(drop=True),
    }


def save_universe(df: pd.DataFrame, output_path: str | Path) -> Path:
    """Save a universe CSV, creating the output directory when needed."""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.reindex(columns=UNIVERSE_COLUMNS).to_csv(path, index=False)
    return path


def _load_universe_files(base_dir: Path, filenames: tuple[str, ...]) -> pd.DataFrame:
    frames = []
    for filename in filenames:
        path = base_dir / filename
        if not path.exists():
            continue
        data = pd.read_csv(path)
        if "ticker" not in data.columns:
            raise ValueError(f"{path} must contain a ticker column")
        frames.append(data.reindex(columns=UNIVERSE_COLUMNS))

    if not frames:
        return _empty_universe()
    return pd.concat(frames, ignore_index=True)


def _empty_universe() -> pd.DataFrame:
    return pd.DataFrame(columns=UNIVERSE_COLUMNS)


def _clean_text(value: Any) -> str:
    if pd.isna(value):
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"nan", "none", "<na>"} else text


def _normalize_market(value: Any, ticker: str) -> str:
    market = _clean_text(value).upper()
    if market in {"TW", "US"}:
        return market
    if ticker.upper().endswith(".TW"):
        return "TW"
    return "US"


def _completeness_score(row: pd.Series) -> int:
    score = 0
    if _clean_text(row.get("market")).upper() in {"TW", "US"}:
        score += 1
    if _clean_text(row.get("name")):
        score += 1
    sector = _clean_text(row.get("sector"))
    if sector and sector.lower() != "unknown":
        score += 1
    return score
