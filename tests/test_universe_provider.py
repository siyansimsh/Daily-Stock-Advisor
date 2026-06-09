import pandas as pd

from src import main as cli
from src.screener import load_universe_from_sources
from src.universe_provider import (
    UNIVERSE_COLUMNS,
    build_universe,
    load_portfolio_holdings,
    normalize_universe,
)


def write_universe(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=UNIVERSE_COLUMNS).to_csv(path, index=False)


def test_normalize_universe_deduplicates_and_fills_missing_values():
    data = pd.DataFrame(
        [
            {"ticker": " 2330.TW ", "market": "tw", "name": "", "sector": "semiconductor"},
            {"ticker": "2330.TW", "market": "TW", "name": "TSMC", "sector": ""},
            {"ticker": "AAPL", "market": "", "name": "", "sector": ""},
            {"ticker": " ", "market": "US", "name": "Blank", "sector": "technology"},
        ]
    )

    result = normalize_universe(data)

    assert set(result["ticker"]) == {"2330.TW", "AAPL"}
    tsmc = result.loc[result["ticker"] == "2330.TW"].iloc[0]
    assert tsmc["market"] == "TW"
    assert tsmc["name"] == "TSMC"
    assert tsmc["sector"] == "semiconductor"
    apple = result.loc[result["ticker"] == "AAPL"].iloc[0]
    assert apple["market"] == "US"
    assert apple["name"] == "AAPL"
    assert apple["sector"] == "unknown"


def test_portfolio_holdings_are_added_with_note_as_name(tmp_path):
    portfolio_path = tmp_path / "portfolio.csv"
    pd.DataFrame(
        [
            ["2317.TW", "TW", 100, 100.0, "", "electronics", "Foxconn"],
            ["MSFT", "US", 0, 300.0, "", "technology", "Microsoft"],
        ],
        columns=["ticker", "market", "shares", "avg_cost", "current_price", "sector", "note"],
    ).to_csv(portfolio_path, index=False)

    result = normalize_universe(load_portfolio_holdings(portfolio_path))

    assert set(result["ticker"]) == {"2317.TW"}
    assert result.loc[0, "name"] == "Foxconn"
    assert result.loc[0, "sector"] == "electronics"


def test_build_universe_merges_config_watchlist_and_splits_markets(tmp_path):
    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True)
    write_universe(
        config_dir / "universe_tw.csv",
        [
            ["2330.TW", "TW", "", "semiconductor"],
            ["0050.TW", "TW", "Taiwan 50", ""],
        ],
    )
    write_universe(config_dir / "universe_us.csv", [["AAPL", "US", "Apple", "technology"]])
    write_universe(config_dir / "watchlist_tw.csv", [["2330.TW", "TW", "TSMC", "semiconductor"]])
    write_universe(config_dir / "watchlist_us.csv", [["MSFT", "", "Microsoft", "technology"]])
    pd.DataFrame(
        [["TSLA", "US", 2, 180.0, "", "consumer", "Tesla"]],
        columns=["ticker", "market", "shares", "avg_cost", "current_price", "sector", "note"],
    ).to_csv(data_dir / "portfolio.csv", index=False)

    result = build_universe(settings={}, config_dir=config_dir, data_dir=data_dir)

    tw = result["TW"]
    us = result["US"]
    assert set(tw["ticker"]) == {"0050.TW", "2330.TW"}
    assert set(us["ticker"]) == {"AAPL", "MSFT", "TSLA"}
    assert tw.loc[tw["ticker"] == "2330.TW", "name"].iloc[0] == "TSMC"
    assert tw.loc[tw["ticker"] == "0050.TW", "sector"].iloc[0] == "unknown"


def test_screener_prefers_generated_universe_when_available(tmp_path):
    config_dir = tmp_path / "config"
    universe_dir = tmp_path / "data" / "universe"
    write_universe(config_dir / "universe_tw.csv", [["2330.TW", "TW", "Config TSMC", "semiconductor"]])
    write_universe(config_dir / "universe_us.csv", [["AAPL", "US", "Apple", "technology"]])
    write_universe(universe_dir / "universe_tw.csv", [["2317.TW", "TW", "Generated Foxconn", "electronics"]])

    result = load_universe_from_sources(config_dir=config_dir, universe_dir=universe_dir)

    assert "2317.TW" in set(result["ticker"])
    assert "2330.TW" not in set(result["ticker"])
    assert "AAPL" in set(result["ticker"])


def test_build_universe_cli_writes_outputs(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    config_dir.mkdir(parents=True)
    data_dir.mkdir(parents=True)
    (config_dir / "settings.yaml").write_text("portfolio:\n  cash_twd: 0\n", encoding="utf-8")
    write_universe(config_dir / "universe_tw.csv", [["2330.TW", "TW", "TSMC", "semiconductor"]])
    write_universe(config_dir / "universe_us.csv", [["AAPL", "US", "Apple", "technology"]])

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "DATA_DIR", data_dir)
    monkeypatch.setattr(cli, "UNIVERSE_DIR", data_dir / "universe")

    assert cli.main(["build-universe"]) == 0

    tw_path = data_dir / "universe" / "universe_tw.csv"
    us_path = data_dir / "universe" / "universe_us.csv"
    assert tw_path.exists()
    assert us_path.exists()
    assert list(pd.read_csv(tw_path).columns) == UNIVERSE_COLUMNS
    assert list(pd.read_csv(us_path).columns) == UNIVERSE_COLUMNS
