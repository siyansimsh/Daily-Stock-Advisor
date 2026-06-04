from datetime import date

import pandas as pd

from src.report_generator import DISCLAIMER, REPORT_TITLE, ReportPaths, generate_daily_report


SETTINGS = {
    "fx": {"USD_TWD": 32.0},
    "portfolio": {"cash_twd": 100000, "cash_usd": 3000},
}


def write_report_inputs(tmp_path):
    recommendations_path = tmp_path / "recommendations.csv"
    screener_path = tmp_path / "screener_result.csv"
    portfolio_path = tmp_path / "portfolio.csv"
    output_dir = tmp_path / "reports"
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    recommendations = pd.DataFrame(
        [
            {
                "ticker": "2330.TW",
                "market": "TW",
                "name": "",
                "shares": 10,
                "avg_cost": 580,
                "current_price_native": 2425,
                "current_price_twd": 2425,
                "market_value_native": 24250,
                "market_value_twd": 24250,
                "unrealized_pnl_native": 18450,
                "unrealized_pnl_pct": 3.18,
                "weight": 0.09,
                "score": 85,
                "signal": "BUY",
                "action": "ADD",
                "confidence": 0.85,
                "suggested_quantity": 17,
                "suggested_price_range": "2376.50 - 2449.25",
                "reason": "close above MA20; currently profitable",
                "risk": "",
            },
            {
                "ticker": "SPY",
                "market": "US",
                "name": "SPDR S&P 500 ETF",
                "shares": 0,
                "avg_cost": 0,
                "current_price_native": 754,
                "current_price_twd": 24128,
                "market_value_native": 0,
                "market_value_twd": 0,
                "unrealized_pnl_native": 0,
                "unrealized_pnl_pct": None,
                "weight": 0,
                "score": 86,
                "signal": "BUY",
                "action": "BUY",
                "confidence": 0.86,
                "suggested_quantity": 2,
                "suggested_price_range": "739.16 - 761.78",
                "reason": "close above MA20; no current position; high score candidate",
                "risk": "no current position",
            },
            {
                "ticker": "QQQ",
                "market": "US",
                "name": "Invesco QQQ ETF",
                "shares": 0,
                "avg_cost": 0,
                "current_price_native": 744,
                "current_price_twd": 23808,
                "market_value_native": 0,
                "market_value_twd": 0,
                "unrealized_pnl_native": 0,
                "unrealized_pnl_pct": None,
                "weight": 0,
                "score": 65,
                "signal": "WATCH",
                "action": "WATCH",
                "confidence": 0.65,
                "suggested_quantity": 0,
                "suggested_price_range": "",
                "reason": "RSI overbought; no current position",
                "risk": "overbought risk; no current position",
            },
        ]
    )
    screener = pd.DataFrame(
        [
            {"ticker": "2330.TW", "market": "TW", "name": "台積電", "score": 85, "signal": "BUY", "reason": ""},
            {"ticker": "SPY", "market": "US", "name": "SPDR S&P 500 ETF", "score": 86, "signal": "BUY", "reason": ""},
            {"ticker": "QQQ", "market": "US", "name": "Invesco QQQ ETF", "score": 65, "signal": "WATCH", "reason": ""},
        ]
    )
    portfolio = pd.DataFrame(
        [
            {
                "ticker": "2330.TW",
                "market": "TW",
                "shares": 10,
                "avg_cost": 580,
                "current_price": 2425,
                "sector": "semiconductor",
                "note": "",
            }
        ]
    )
    universe_tw = pd.DataFrame(
        [{"ticker": "2330.TW", "market": "TW", "name": "台積電", "sector": "semiconductor"}]
    )
    universe_us = pd.DataFrame(
        [
            {"ticker": "SPY", "market": "US", "name": "SPDR S&P 500 ETF", "sector": "ETF"},
            {"ticker": "QQQ", "market": "US", "name": "Invesco QQQ ETF", "sector": "ETF"},
        ]
    )

    recommendations.to_csv(recommendations_path, index=False)
    screener.to_csv(screener_path, index=False)
    portfolio.to_csv(portfolio_path, index=False)
    universe_tw.to_csv(config_dir / "universe_tw.csv", index=False)
    universe_us.to_csv(config_dir / "universe_us.csv", index=False)
    return ReportPaths(
        recommendations_path=recommendations_path,
        screener_result_path=screener_path,
        portfolio_path=portfolio_path,
        output_dir=output_dir,
        config_dir=config_dir,
    )


def html_section(html: str, heading: str, next_heading: str) -> str:
    start = html.index(heading)
    end = html.index(next_heading, start)
    return html[start:end]


def test_generate_report_creates_markdown_file(tmp_path):
    paths = write_report_inputs(tmp_path)

    result = generate_daily_report(SETTINGS, paths, report_date=date(2026, 6, 4))

    assert result.markdown_path.exists()


def test_generate_report_creates_html_file(tmp_path):
    paths = write_report_inputs(tmp_path)

    result = generate_daily_report(SETTINGS, paths, report_date=date(2026, 6, 4))

    assert result.html_path.exists()


def test_markdown_contains_required_sections_and_disclaimer(tmp_path):
    paths = write_report_inputs(tmp_path)

    result = generate_daily_report(SETTINGS, paths, report_date=date(2026, 6, 4))
    markdown = result.markdown_path.read_text(encoding="utf-8")

    assert "日期：2026-06-04" in markdown
    assert "## 2. 投資組合摘要" in markdown
    assert "## 3. 建議行動" in markdown
    assert "## 4. 新增買進候選" in markdown
    assert "## 5. 加碼候選" in markdown
    assert "## 8. 風險控制" in markdown
    assert DISCLAIMER in markdown


def test_html_contains_utf8_meta_style_and_chinese_title(tmp_path):
    paths = write_report_inputs(tmp_path)

    result = generate_daily_report(SETTINGS, paths, report_date=date(2026, 6, 4))
    html = result.html_path.read_text(encoding="utf-8")

    assert '<meta charset="UTF-8">' in html
    assert REPORT_TITLE in html
    assert "<style>" in html
    assert DISCLAIMER in html


def test_html_contains_action_badge_class(tmp_path):
    paths = write_report_inputs(tmp_path)

    result = generate_daily_report(SETTINGS, paths, report_date=date(2026, 6, 4))
    html = result.html_path.read_text(encoding="utf-8")

    assert "badge badge-buy" in html
    assert "badge badge-add" in html
    assert "badge badge-watch" in html


def test_reason_and_risk_are_translated(tmp_path):
    paths = write_report_inputs(tmp_path)

    result = generate_daily_report(SETTINGS, paths, report_date=date(2026, 6, 4))
    markdown = result.markdown_path.read_text(encoding="utf-8")
    html = result.html_path.read_text(encoding="utf-8")

    assert "投資組合摘要" in markdown
    assert "股價站上 MA20" in markdown
    assert "RSI 過熱" in html


def test_portfolio_summary_html_contains_name_column(tmp_path):
    paths = write_report_inputs(tmp_path)

    result = generate_daily_report(SETTINGS, paths, report_date=date(2026, 6, 4))
    html = result.html_path.read_text(encoding="utf-8")

    portfolio_section = html_section(html, "2. 投資組合摘要", "3. 建議行動")
    assert "<th>名稱</th>" in portfolio_section


def test_html_displays_universe_name_for_2330(tmp_path):
    paths = write_report_inputs(tmp_path)

    result = generate_daily_report(SETTINGS, paths, report_date=date(2026, 6, 4))
    html = result.html_path.read_text(encoding="utf-8")

    assert "2330.TW" in html
    assert "台積電" in html


def test_non_held_buy_appears_in_new_buy_candidates(tmp_path):
    paths = write_report_inputs(tmp_path)

    result = generate_daily_report(SETTINGS, paths, report_date=date(2026, 6, 4))
    html = result.html_path.read_text(encoding="utf-8")

    new_buy_section = html_section(html, "4. 新增買進候選", "5. 加碼候選")
    assert "SPY" in new_buy_section
    assert "SPDR S&amp;P 500 ETF" in new_buy_section
    assert "739.16 - 761.78" in new_buy_section


def test_held_add_appears_in_add_candidates(tmp_path):
    paths = write_report_inputs(tmp_path)

    result = generate_daily_report(SETTINGS, paths, report_date=date(2026, 6, 4))
    html = result.html_path.read_text(encoding="utf-8")

    add_section = html_section(html, "5. 加碼候選", "6. 減碼 / 賣出候選")
    assert "2330.TW" in add_section
    assert "台積電" in add_section
    assert "2376.50 - 2449.25" in add_section


def test_markdown_contains_new_buy_candidates(tmp_path):
    paths = write_report_inputs(tmp_path)

    result = generate_daily_report(SETTINGS, paths, report_date=date(2026, 6, 4))
    markdown = result.markdown_path.read_text(encoding="utf-8")

    assert "## 4. 新增買進候選" in markdown
    assert "SPY" in markdown
