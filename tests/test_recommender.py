import pandas as pd

from src.recommender import RECOMMENDATION_COLUMNS, RecommendationPaths, generate_recommendations


def settings(max_position_weight=0.25, cash_twd=0, cash_usd=0, usd_twd=32.0):
    return {
        "user": {"max_position_weight": max_position_weight, "stop_loss_pct": -0.10},
        "fx": {"USD_TWD": usd_twd},
        "portfolio": {
            "cash_twd": cash_twd,
            "cash_usd": cash_usd,
            "default_tw_lot_size": 1,
            "default_us_lot_size": 1,
        },
    }


def write_inputs(tmp_path, portfolio_rows, screener_rows):
    portfolio_path = tmp_path / "portfolio.csv"
    screener_path = tmp_path / "screener_result.csv"
    output_path = tmp_path / "recommendations.csv"
    pd.DataFrame(portfolio_rows).to_csv(portfolio_path, index=False)
    pd.DataFrame(screener_rows).to_csv(screener_path, index=False)
    return RecommendationPaths(
        portfolio_path=portfolio_path,
        screener_result_path=screener_path,
        output_path=output_path,
    )


def portfolio_row(ticker, market="US", shares=10, avg_cost=100, current_price=100):
    return {
        "ticker": ticker,
        "market": market,
        "shares": shares,
        "avg_cost": avg_cost,
        "current_price": current_price,
        "sector": "technology",
        "note": "",
    }


def screener_row(ticker, market="US", score=80, signal="BUY", reason="RSI in healthy range", close=100.0):
    return {
        "ticker": ticker,
        "market": market,
        "name": ticker,
        "close": close,
        "score": score,
        "signal": signal,
        "reason": reason,
    }


def test_stop_loss_holding_is_sell(tmp_path):
    paths = write_inputs(
        tmp_path,
        [portfolio_row("LOSS", shares=10, avg_cost=100, current_price=85)],
        [screener_row("LOSS", score=70, signal="WATCH")],
    )

    result = generate_recommendations(settings(), paths)
    row = result.loc[result["ticker"] == "LOSS"].iloc[0]

    assert row["action"] == "SELL"
    assert row["suggested_quantity"] == 10
    assert row["confidence"] >= 0.8
    assert "stop loss triggered" in row["risk"]


def test_overweight_holding_is_reduce(tmp_path):
    paths = write_inputs(
        tmp_path,
        [
            portfolio_row("OVER", shares=10, avg_cost=100, current_price=100),
            portfolio_row("SMALL", shares=1, avg_cost=100, current_price=100),
        ],
        [
            screener_row("OVER", score=70, signal="WATCH"),
            screener_row("SMALL", score=70, signal="WATCH"),
        ],
    )

    result = generate_recommendations(settings(), paths)
    row = result.loc[result["ticker"] == "OVER"].iloc[0]

    assert row["action"] == "REDUCE"
    assert row["suggested_quantity"] == 2
    assert "position concentration risk" in row["risk"]


def test_non_holding_high_score_buy_signal_is_buy(tmp_path):
    paths = write_inputs(
        tmp_path,
        [portfolio_row("HELD", shares=10, avg_cost=100, current_price=100)],
        [
            screener_row("HELD", score=60, signal="WATCH"),
            screener_row("NEW", score=90, signal="BUY"),
        ],
    )

    result = generate_recommendations(settings(cash_usd=1000), paths)
    row = result.loc[result["ticker"] == "NEW"].iloc[0]

    assert row["action"] == "BUY"
    assert row["confidence"] == 0.9
    assert "no current position" in row["risk"]


def test_overbought_watch_candidate_does_not_become_buy(tmp_path):
    paths = write_inputs(
        tmp_path,
        [portfolio_row("HELD", shares=10, avg_cost=100, current_price=100)],
        [
            screener_row("HELD", score=60, signal="WATCH"),
            screener_row("HOT", score=90, signal="WATCH", reason="RSI overbought; avoid chasing high"),
        ],
    )

    result = generate_recommendations(settings(cash_usd=1000), paths)
    row = result.loc[result["ticker"] == "HOT"].iloc[0]

    assert row["action"] == "WATCH"
    assert row["action"] != "BUY"
    assert "overbought risk" in row["risk"]


def test_us_market_value_twd_uses_usd_twd(tmp_path):
    paths = write_inputs(
        tmp_path,
        [portfolio_row("US1", market="US", shares=2, current_price=100)],
        [screener_row("US1", market="US", score=70, signal="WATCH")],
    )

    result = generate_recommendations(settings(usd_twd=32), paths)
    row = result.loc[result["ticker"] == "US1"].iloc[0]

    assert row["market_value_native"] == 200
    assert row["market_value_twd"] == 6400
    assert row["current_price_twd"] == 3200


def test_tw_market_value_twd_does_not_convert(tmp_path):
    paths = write_inputs(
        tmp_path,
        [portfolio_row("TW1", market="TW", shares=2, current_price=100)],
        [screener_row("TW1", market="TW", score=70, signal="WATCH")],
    )

    result = generate_recommendations(settings(usd_twd=32), paths)
    row = result.loc[result["ticker"] == "TW1"].iloc[0]

    assert row["market_value_native"] == 200
    assert row["market_value_twd"] == 200
    assert row["current_price_twd"] == 100


def test_weight_uses_twd_total_value_including_cash(tmp_path):
    paths = write_inputs(
        tmp_path,
        [
            portfolio_row("US1", market="US", shares=1, current_price=100),
            portfolio_row("TW1", market="TW", shares=100, current_price=10),
        ],
        [
            screener_row("US1", market="US", score=70, signal="WATCH"),
            screener_row("TW1", market="TW", score=70, signal="WATCH", close=10),
        ],
    )

    result = generate_recommendations(settings(cash_twd=5800, usd_twd=32), paths)
    us_row = result.loc[result["ticker"] == "US1"].iloc[0]
    tw_row = result.loc[result["ticker"] == "TW1"].iloc[0]

    assert us_row["weight"] == 3200 / 10000
    assert tw_row["weight"] == 1000 / 10000


def test_buy_quantity_does_not_exceed_cash_usd(tmp_path):
    paths = write_inputs(
        tmp_path,
        [portfolio_row("HELD", market="TW", shares=1, avg_cost=100, current_price=100)],
        [
            screener_row("HELD", market="TW", score=60, signal="WATCH"),
            screener_row("NEW", market="US", score=90, signal="BUY", close=100),
        ],
    )

    result = generate_recommendations(settings(max_position_weight=1.0, cash_twd=1_000_000, cash_usd=150), paths)
    row = result.loc[result["ticker"] == "NEW"].iloc[0]

    assert row["action"] == "BUY"
    assert row["suggested_quantity"] == 1
    assert row["suggested_quantity"] * row["current_price_native"] <= 150


def test_add_quantity_does_not_exceed_max_position_weight(tmp_path):
    paths = write_inputs(
        tmp_path,
        [portfolio_row("ADDME", market="US", shares=1, avg_cost=80, current_price=100)],
        [screener_row("ADDME", market="US", score=96, signal="BUY", close=100)],
    )

    result = generate_recommendations(settings(max_position_weight=0.25, cash_usd=10_000), paths)
    row = result.loc[result["ticker"] == "ADDME"].iloc[0]

    assert row["action"] == "ADD"
    assert row["suggested_quantity"] == 24
    assert row["market_value_twd"] + row["suggested_quantity"] * row["current_price_twd"] <= 323200 * 0.25


def test_recommendations_csv_has_required_columns(tmp_path):
    paths = write_inputs(
        tmp_path,
        [portfolio_row("HELD", shares=10, avg_cost=100, current_price=100)],
        [screener_row("HELD", score=70, signal="WATCH")],
    )

    generate_recommendations(settings(), paths)
    written = pd.read_csv(paths.output_path)

    assert list(written.columns) == RECOMMENDATION_COLUMNS
