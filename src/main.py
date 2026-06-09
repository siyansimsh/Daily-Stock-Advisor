"""Command line entry point for Daily Stock Advisor."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable
import warnings

import pandas as pd

try:
    import yaml
except ImportError:  # pragma: no cover - dependency is listed in requirements.txt
    yaml = None

from src.data_providers import YFinanceProvider
from src.portfolio import refresh_portfolio_current_prices
from src.recommender import RecommendationPaths, generate_recommendations
from src.report_generator import ReportPaths, generate_daily_report
from src.screener import ScreenerPaths, load_universe_from_sources, screen_universe
from src.transactions import build_portfolio_from_transactions, load_transactions
from src.universe_provider import build_universe, save_universe


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = PROJECT_ROOT / "config"
DATA_DIR = PROJECT_ROOT / "data"
PRICE_DIR = DATA_DIR / "prices"
UNIVERSE_DIR = DATA_DIR / "universe"
REPORTS_DIR = PROJECT_ROOT / "reports"
TRANSACTIONS_PATH = DATA_DIR / "transactions.csv"
PORTFOLIO_PATH = DATA_DIR / "portfolio.csv"
SCREENER_RESULT_PATH = DATA_DIR / "screener_result.csv"
RECOMMENDATIONS_PATH = DATA_DIR / "recommendations.csv"


def load_settings(path: Path = CONFIG_DIR / "settings.yaml") -> dict:
    settings_path = Path(path)
    if not settings_path.exists():
        raise FileNotFoundError(f"Settings file not found: {settings_path}")

    try:
        content = settings_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"Unable to read settings file: {settings_path}") from exc

    if yaml is not None:
        try:
            settings = yaml.safe_load(content)
        except Exception as exc:  # noqa: BLE001 - fallback should report parser failures clearly
            _warn_settings_fallback(
                f"PyYAML failed to parse {settings_path}; using limited fallback parser. Error: {exc}"
            )
            settings = parse_simple_yaml(content.splitlines())
    else:
        _warn_settings_fallback("PyYAML is not installed; using limited fallback parser for settings.yaml.")
        settings = parse_simple_yaml(content.splitlines())

    if not isinstance(settings, dict) or not settings:
        raise ValueError(f"Settings file is empty or invalid: {settings_path}")
    return settings


def _warn_settings_fallback(message: str) -> None:
    print(f"Warning: {message}")
    warnings.warn(message, RuntimeWarning, stacklevel=2)


def parse_simple_yaml(lines: list[str]) -> dict:
    """Small fallback for this project's simple settings.yaml structure."""

    result: dict = {}
    current_section: str | None = None
    current_list_key: str | None = None

    for raw_line in lines:
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        indent = len(line) - len(line.lstrip(" "))
        if indent == 0:
            key, value = _split_yaml_key_value(stripped)
            if value == "":
                result[key] = {}
                current_section = key
                current_list_key = None
            else:
                result[key] = _parse_yaml_scalar(value)
                current_section = None
                current_list_key = None
        elif indent == 2 and current_section:
            key, value = _split_yaml_key_value(stripped)
            if value == "":
                result[current_section][key] = []
                current_list_key = key
            else:
                result[current_section][key] = _parse_yaml_scalar(value)
                current_list_key = None
        elif indent == 4 and current_section and current_list_key and stripped.startswith("- "):
            result[current_section][current_list_key].append(_parse_yaml_scalar(stripped[2:].strip()))

    return result


def _split_yaml_key_value(line: str) -> tuple[str, str]:
    key, _, value = line.partition(":")
    return key.strip(), value.strip()


def _parse_yaml_scalar(value: str):
    if value in {"true", "True"}:
        return True
    if value in {"false", "False"}:
        return False
    try:
        if any(char in value for char in ".eE"):
            return float(value)
        return int(value)
    except ValueError:
        return value.strip("\"'")


def read_tickers_from_csv(path: Path) -> list[str]:
    if not path.exists():
        return []
    data = pd.read_csv(path)
    if "ticker" not in data.columns:
        raise ValueError(f"{path} must contain a ticker column")
    return data["ticker"].dropna().astype(str).str.strip().loc[lambda values: values != ""].tolist()


def collect_default_tickers() -> list[str]:
    tickers: list[str] = []
    universe = load_universe_from_sources(CONFIG_DIR, UNIVERSE_DIR)
    if "ticker" in universe.columns:
        tickers.extend(universe["ticker"].dropna().astype(str).str.strip().loc[lambda values: values != ""].tolist())
    tickers.extend(read_tickers_from_csv(PORTFOLIO_PATH))
    return sorted(set(tickers))


def print_update_results(results: Iterable) -> None:
    rows = []
    for result in results:
        rows.append(
            {
                "ticker": result.ticker,
                "status": result.status,
                "rows": result.rows,
                "latest_date": result.latest_date or "",
                "latest_close": "" if result.latest_close is None else round(result.latest_close, 4),
                "message": result.message,
            }
        )

    if not rows:
        print("No tickers to update.")
        return

    print(pd.DataFrame(rows).to_string(index=False))


def command_update_data(args: argparse.Namespace) -> int:
    load_settings(CONFIG_DIR / "settings.yaml")
    tickers = args.tickers if args.tickers else collect_default_tickers()
    provider = YFinanceProvider(cache_dir=PRICE_DIR)
    results = provider.update_tickers(
        tickers=tickers,
        period=args.period,
        interval=args.interval,
        force=args.force,
    )
    print_update_results(results)

    successful_tickers = {result.ticker for result in results if result.status == "ok"}
    if successful_tickers and PORTFOLIO_PATH.exists():
        portfolio = refresh_portfolio_current_prices(PORTFOLIO_PATH, PRICE_DIR)
        refreshed = portfolio[portfolio["ticker"].isin(successful_tickers)]["ticker"].tolist()
        if refreshed:
            print(f"Updated portfolio current_price for: {', '.join(refreshed)}")

    return 0 if any(result.status == "ok" for result in results) else 1


def command_build_portfolio(args: argparse.Namespace) -> int:
    transactions = load_transactions(TRANSACTIONS_PATH)
    portfolio = build_portfolio_from_transactions(transactions)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    portfolio.to_csv(PORTFOLIO_PATH, index=False)
    print(f"Wrote portfolio to {PORTFOLIO_PATH}")
    if portfolio.empty:
        print("No open positions generated from transactions.")
    else:
        print(portfolio.to_string(index=False))
    return 0


def command_build_universe(args: argparse.Namespace) -> int:
    settings = load_settings(CONFIG_DIR / "settings.yaml")
    universes = build_universe(settings=settings, config_dir=CONFIG_DIR, data_dir=DATA_DIR)
    tw_path = save_universe(universes["TW"], UNIVERSE_DIR / "universe_tw.csv")
    us_path = save_universe(universes["US"], UNIVERSE_DIR / "universe_us.csv")
    print(f"Wrote TW universe ({len(universes['TW'])}) to {tw_path}")
    print(f"Wrote US universe ({len(universes['US'])}) to {us_path}")
    return 0


def command_screen(args: argparse.Namespace) -> int:
    settings = load_settings(CONFIG_DIR / "settings.yaml")
    result = screen_universe(
        settings=settings,
        paths=ScreenerPaths(
            config_dir=CONFIG_DIR,
            price_dir=PRICE_DIR,
            output_path=SCREENER_RESULT_PATH,
            universe_dir=UNIVERSE_DIR,
        ),
    )
    if result.empty:
        print("No universe tickers to screen.")
        return 1

    print(f"Wrote screener results to {SCREENER_RESULT_PATH}")
    print(result[["ticker", "market", "name", "score", "signal", "reason"]].to_string(index=False))
    return 0 if not (result["signal"] == "ERROR").all() else 1


def command_recommend(args: argparse.Namespace) -> int:
    settings = load_settings(CONFIG_DIR / "settings.yaml")
    result = generate_recommendations(
        settings=settings,
        paths=RecommendationPaths(
            portfolio_path=PORTFOLIO_PATH,
            screener_result_path=SCREENER_RESULT_PATH,
            output_path=RECOMMENDATIONS_PATH,
        ),
    )
    if result.empty:
        print("No recommendations generated.")
        return 1

    print(f"Wrote recommendations to {RECOMMENDATIONS_PATH}")
    print(result[["ticker", "market", "name", "score", "signal", "action", "confidence", "reason", "risk"]].to_string(index=False))
    return 0


def command_generate_report(args: argparse.Namespace) -> int:
    settings = load_settings(CONFIG_DIR / "settings.yaml")
    result = generate_daily_report(
        settings=settings,
        paths=ReportPaths(
            recommendations_path=RECOMMENDATIONS_PATH,
            screener_result_path=SCREENER_RESULT_PATH,
            portfolio_path=PORTFOLIO_PATH,
            output_dir=REPORTS_DIR,
            config_dir=CONFIG_DIR,
        ),
    )
    print(f"Wrote Markdown report to {result.markdown_path}")
    print(f"Wrote HTML report to {result.html_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Daily TW/US stock advisor CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    update_data = subparsers.add_parser("update-data", help="Download OHLCV data and refresh price cache")
    update_data.add_argument("--tickers", nargs="*", help="Optional tickers to update")
    update_data.add_argument("--period", default="1y", help="yfinance period, e.g. 6mo, 1y, 2y")
    update_data.add_argument("--interval", default="1d", help="yfinance interval, e.g. 1d")
    update_data.add_argument("--force", action="store_true", help="Ignore today's cache and redownload")
    update_data.set_defaults(func=command_update_data)

    build_portfolio = subparsers.add_parser("build-portfolio", help="Build portfolio.csv from transactions.csv")
    build_portfolio.set_defaults(func=command_build_portfolio)

    build_universe_parser = subparsers.add_parser(
        "build-universe",
        help="Build generated TW/US universe CSVs from config, watchlist, and portfolio",
    )
    build_universe_parser.set_defaults(func=command_build_universe)

    screen = subparsers.add_parser("screen", help="Run rule-based stock screener")
    screen.set_defaults(func=command_screen)

    recommend = subparsers.add_parser("recommend", help="Generate personalized recommendations")
    recommend.set_defaults(func=command_recommend)

    generate_report = subparsers.add_parser("generate-report", help="Generate daily Markdown and HTML reports")
    generate_report.set_defaults(func=command_generate_report)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
