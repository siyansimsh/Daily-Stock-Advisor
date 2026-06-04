"""Transaction ledger loading and portfolio generation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from src.portfolio import PORTFOLIO_COLUMNS


TRANSACTION_COLUMNS = [
    "date",
    "ticker",
    "market",
    "side",
    "shares",
    "price",
    "fee",
    "tax",
    "currency",
    "sector",
    "note",
]
ALLOWED_SIDES = {"BUY", "SELL"}


def load_transactions(path: str | Path) -> pd.DataFrame:
    transaction_path = Path(path)
    if not transaction_path.exists():
        raise FileNotFoundError(f"Transaction file not found: {transaction_path}")
    return validate_transactions(pd.read_csv(transaction_path))


def validate_transactions(df: pd.DataFrame) -> pd.DataFrame:
    missing = [column for column in TRANSACTION_COLUMNS if column not in df.columns]
    if missing:
        raise ValueError(f"Transactions are missing columns: {missing}")

    result = df[TRANSACTION_COLUMNS].copy()
    if result.empty:
        return result

    result["date"] = pd.to_datetime(result["date"], errors="raise").dt.date
    for column in ["ticker", "market", "side", "currency", "sector", "note"]:
        result[column] = result[column].fillna("").astype(str).str.strip()

    result["side"] = result["side"].str.upper()
    invalid_sides = sorted(set(result.loc[~result["side"].isin(ALLOWED_SIDES), "side"]))
    if invalid_sides:
        raise ValueError(f"Invalid transaction side: {invalid_sides}. Allowed sides: BUY, SELL")

    empty_tickers = result["ticker"] == ""
    if empty_tickers.any():
        raise ValueError("Transactions contain empty ticker values")

    empty_markets = result["market"] == ""
    if empty_markets.any():
        raise ValueError("Transactions contain empty market values")

    for column in ["shares", "price", "fee", "tax"]:
        result[column] = pd.to_numeric(result[column], errors="coerce")

    if result["shares"].isna().any() or (result["shares"] <= 0).any():
        raise ValueError("Transaction shares must be positive numbers")
    if result["price"].isna().any() or (result["price"] < 0).any():
        raise ValueError("Transaction price must be zero or positive")

    for column in ["fee", "tax"]:
        result[column] = result[column].fillna(0.0)
        if (result[column] < 0).any():
            raise ValueError(f"Transaction {column} must be zero or positive")

    return result


def build_portfolio_from_transactions(df: pd.DataFrame) -> pd.DataFrame:
    transactions = validate_transactions(df)
    if transactions.empty:
        return pd.DataFrame(columns=PORTFOLIO_COLUMNS)

    ordered = transactions.copy()
    ordered["_row_order"] = range(len(ordered))
    ordered = ordered.sort_values(["date", "_row_order"])

    positions: dict[str, dict[str, Any]] = {}
    for _, row in ordered.iterrows():
        ticker = row["ticker"]
        side = row["side"]
        shares = float(row["shares"])
        price = float(row["price"])
        fee = float(row["fee"])

        position = positions.get(
            ticker,
            {
                "ticker": ticker,
                "market": row["market"],
                "shares": 0.0,
                "avg_cost": 0.0,
                "current_price": "",
                "sector": row["sector"],
                "note": row["note"],
            },
        )
        _merge_metadata(position, row)

        if side == "BUY":
            previous_shares = float(position["shares"])
            previous_cost = previous_shares * float(position["avg_cost"])
            buy_cost = shares * price + fee
            new_shares = previous_shares + shares
            position["shares"] = new_shares
            position["avg_cost"] = (previous_cost + buy_cost) / new_shares
            positions[ticker] = position
            continue

        if shares > float(position["shares"]):
            raise ValueError(f"Cannot SELL {shares:g} shares of {ticker}; only {position['shares']:g} available")

        remaining_shares = float(position["shares"]) - shares
        if remaining_shares == 0:
            positions.pop(ticker, None)
        else:
            position["shares"] = remaining_shares
            positions[ticker] = position

    portfolio = pd.DataFrame(list(positions.values()), columns=PORTFOLIO_COLUMNS)
    if portfolio.empty:
        return pd.DataFrame(columns=PORTFOLIO_COLUMNS)

    portfolio = portfolio.sort_values("ticker").reset_index(drop=True)
    portfolio["shares"] = portfolio["shares"].map(_format_number_for_csv)
    portfolio["avg_cost"] = portfolio["avg_cost"].map(_format_number_for_csv)
    return portfolio[PORTFOLIO_COLUMNS]


def _merge_metadata(position: dict[str, Any], row: pd.Series) -> None:
    for column in ["market", "sector", "note"]:
        value = str(row.get(column, "")).strip()
        if value:
            position[column] = value


def _format_number_for_csv(value: float) -> int | float:
    number = float(value)
    if number.is_integer():
        return int(number)
    return round(number, 6)
