import pandas as pd
import pytest

from src.portfolio import PORTFOLIO_COLUMNS
from src.transactions import build_portfolio_from_transactions, load_transactions, validate_transactions


def transaction_rows(rows):
    return pd.DataFrame(
        rows,
        columns=[
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
        ],
    )


def test_buy_creates_position():
    transactions = transaction_rows(
        [["2026-06-04", "2330.TW", "TW", "BUY", 10, 100, 0, 0, "TWD", "semiconductor", "台積電"]]
    )

    portfolio = build_portfolio_from_transactions(transactions)

    assert len(portfolio) == 1
    assert portfolio.loc[0, "ticker"] == "2330.TW"
    assert portfolio.loc[0, "shares"] == 10
    assert portfolio.loc[0, "avg_cost"] == 100


def test_multiple_buys_calculate_weighted_average_cost():
    transactions = transaction_rows(
        [
            ["2026-06-04", "AAPL", "US", "BUY", 10, 100, 0, 0, "USD", "technology", "Apple"],
            ["2026-06-05", "AAPL", "US", "BUY", 10, 200, 10, 0, "USD", "technology", "Apple"],
        ]
    )

    portfolio = build_portfolio_from_transactions(transactions)

    assert portfolio.loc[0, "shares"] == 20
    assert portfolio.loc[0, "avg_cost"] == pytest.approx(150.5)


def test_sell_reduces_shares_without_changing_average_cost():
    transactions = transaction_rows(
        [
            ["2026-06-04", "AAPL", "US", "BUY", 10, 100, 0, 0, "USD", "technology", "Apple"],
            ["2026-06-05", "AAPL", "US", "SELL", 4, 120, 0, 0, "USD", "technology", "Apple"],
        ]
    )

    portfolio = build_portfolio_from_transactions(transactions)

    assert portfolio.loc[0, "shares"] == 6
    assert portfolio.loc[0, "avg_cost"] == 100


def test_sell_more_than_position_raises_error():
    transactions = transaction_rows(
        [
            ["2026-06-04", "AAPL", "US", "BUY", 3, 100, 0, 0, "USD", "technology", "Apple"],
            ["2026-06-05", "AAPL", "US", "SELL", 4, 120, 0, 0, "USD", "technology", "Apple"],
        ]
    )

    with pytest.raises(ValueError, match="Cannot SELL"):
        build_portfolio_from_transactions(transactions)


def test_sell_to_zero_removes_position():
    transactions = transaction_rows(
        [
            ["2026-06-04", "AAPL", "US", "BUY", 3, 100, 0, 0, "USD", "technology", "Apple"],
            ["2026-06-05", "AAPL", "US", "SELL", 3, 120, 0, 0, "USD", "technology", "Apple"],
        ]
    )

    portfolio = build_portfolio_from_transactions(transactions)

    assert portfolio.empty
    assert list(portfolio.columns) == PORTFOLIO_COLUMNS


def test_build_portfolio_outputs_portfolio_compatible_columns():
    transactions = transaction_rows(
        [["2026-06-04", "AAPL", "US", "BUY", 2, 180, 0, 0, "USD", "technology", "Apple"]]
    )

    portfolio = build_portfolio_from_transactions(transactions)

    assert list(portfolio.columns) == PORTFOLIO_COLUMNS
    assert portfolio.loc[0, "current_price"] == ""


def test_load_transactions_reads_and_validates_csv(tmp_path):
    path = tmp_path / "transactions.csv"
    transactions = transaction_rows(
        [["2026-06-04", "0050.TW", "TW", "buy", 1000, 50, 1, 0, "TWD", "ETF", "元大台灣50"]]
    )
    transactions.to_csv(path, index=False)

    loaded = load_transactions(path)

    assert loaded.loc[0, "side"] == "BUY"
    assert loaded.loc[0, "fee"] == 1


def test_validate_transactions_rejects_invalid_side():
    transactions = transaction_rows(
        [["2026-06-04", "AAPL", "US", "DIVIDEND", 1, 100, 0, 0, "USD", "technology", "Apple"]]
    )

    with pytest.raises(ValueError, match="Invalid transaction side"):
        validate_transactions(transactions)
