"""Portfolio loading and first-version P/L calculations."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


PORTFOLIO_COLUMNS = ["ticker", "market", "shares", "avg_cost", "current_price", "sector", "note"]


def load_portfolio(path: str | Path) -> pd.DataFrame:
    portfolio_path = Path(path)
    if not portfolio_path.exists():
        raise FileNotFoundError(f"Portfolio file not found: {portfolio_path}")

    data = pd.read_csv(portfolio_path)
    missing = [column for column in PORTFOLIO_COLUMNS if column not in data.columns]
    if missing:
        raise ValueError(f"Portfolio is missing columns: {missing}")

    result = data[PORTFOLIO_COLUMNS].copy()
    result["ticker"] = result["ticker"].astype(str).str.strip()
    result["market"] = result["market"].astype(str).str.strip()
    result["shares"] = pd.to_numeric(result["shares"], errors="coerce").fillna(0.0)
    result["avg_cost"] = pd.to_numeric(result["avg_cost"], errors="coerce").fillna(0.0)
    result["current_price"] = pd.to_numeric(result["current_price"], errors="coerce")
    return result


def latest_close_from_cache(ticker: str, price_dir: str | Path) -> float | None:
    safe_ticker = ticker.replace("/", "_").replace("\\", "_")
    price_path = Path(price_dir) / f"{safe_ticker}.csv"
    if not price_path.exists():
        return None

    data = pd.read_csv(price_path)
    if data.empty or "Close" not in data.columns:
        return None
    close = pd.to_numeric(data["Close"], errors="coerce").dropna()
    if close.empty:
        return None
    return float(close.iloc[-1])


def refresh_portfolio_current_prices(
    portfolio_path: str | Path,
    price_dir: str | Path,
) -> pd.DataFrame:
    """Update ``current_price`` in portfolio.csv from cached close prices."""

    portfolio_path = Path(portfolio_path)
    portfolio = load_portfolio(portfolio_path)
    for index, row in portfolio.iterrows():
        latest_close = latest_close_from_cache(row["ticker"], price_dir)
        if latest_close is not None:
            portfolio.at[index, "current_price"] = latest_close

    portfolio.to_csv(portfolio_path, index=False)
    return portfolio


def calculate_portfolio_metrics(
    portfolio: pd.DataFrame,
    max_position_weight: float = 0.25,
    usd_twd: float = 1.0,
    cash_twd: float = 0.0,
    cash_usd: float = 0.0,
) -> pd.DataFrame:
    """Calculate native/TWD market value, unrealized P/L, P/L %, and weight."""

    result = portfolio.copy()
    result["current_price_native"] = pd.to_numeric(result["current_price"], errors="coerce").fillna(0.0)
    result["current_price_twd"] = result.apply(
        lambda row: convert_price_to_twd(row["current_price_native"], row["market"], usd_twd),
        axis=1,
    )
    result["market_value_native"] = result["shares"] * result["current_price_native"]
    result["market_value_twd"] = result["shares"] * result["current_price_twd"]
    result["cost_basis_native"] = result["shares"] * result["avg_cost"]
    result["unrealized_pnl_native"] = result["market_value_native"] - result["cost_basis_native"]
    result["unrealized_pnl_pct"] = result["unrealized_pnl_native"] / result["cost_basis_native"].mask(
        result["cost_basis_native"] == 0
    )

    total_portfolio_value_twd = (
        result["market_value_twd"].sum()
        + float(cash_twd)
        + float(cash_usd) * float(usd_twd)
    )
    if total_portfolio_value_twd > 0:
        result["weight"] = result["market_value_twd"] / total_portfolio_value_twd
    else:
        result["weight"] = 0.0

    result["position_risk_high"] = result["weight"] > max_position_weight
    result["total_portfolio_value_twd"] = total_portfolio_value_twd

    result["market_value"] = result["market_value_native"]
    result["cost_basis"] = result["cost_basis_native"]
    result["unrealized_pl"] = result["unrealized_pnl_native"]
    result["unrealized_pl_pct"] = result["unrealized_pnl_pct"]
    return result


def convert_price_to_twd(price: float, market: str, usd_twd: float) -> float:
    if str(market).upper() == "US":
        return float(price) * float(usd_twd)
    return float(price)
