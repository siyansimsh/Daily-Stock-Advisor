"""Daily Markdown and HTML report generation for Phase 4."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from html import escape
from pathlib import Path
from typing import Any

import pandas as pd


REPORT_TITLE = "每日TW/美國股票投資報告"
DISCLAIMER = (
    "本系統僅作為個人研究、學習與投資決策輔助工具，不構成任何投資建議、招攬或保證獲利。"
    "股票投資具有市場風險，使用者應自行判斷並承擔投資結果。"
)

ACTION_ORDER = ["BUY", "ADD", "HOLD", "REDUCE", "SELL", "WATCH"]
ACTION_LABELS = {
    "BUY": "買進",
    "ADD": "加碼",
    "HOLD": "持有",
    "REDUCE": "減碼",
    "SELL": "賣出",
    "WATCH": "觀察",
}
ACTION_BADGE_CLASSES = {
    "BUY": "badge-buy",
    "ADD": "badge-add",
    "HOLD": "badge-hold",
    "REDUCE": "badge-reduce",
    "SELL": "badge-sell",
    "WATCH": "badge-watch",
}
RISK_FLAGS = [
    "position concentration risk",
    "overbought risk",
    "high volatility",
    "large drawdown risk",
    "insufficient cash",
    "stop loss triggered",
]
TEXT_TRANSLATIONS = {
    "close above MA20": "股價站上 MA20",
    "close above MA60": "股價站上 MA60",
    "close above MA120": "股價站上 MA120",
    "positive 20d return": "20 日報酬為正",
    "positive 60d return": "60 日報酬為正",
    "MACD above signal": "MACD 位於訊號線上方",
    "volume ratio meets threshold": "成交量比達標",
    "RSI in healthy range": "RSI 處於健康區間",
    "RSI slightly overbought": "RSI 略偏高",
    "RSI overbought": "RSI 過熱",
    "trend is strong but RSI is overbought": "趨勢強但 RSI 過熱",
    "avoid chasing high": "避免追高",
    "high volatility": "波動度偏高",
    "moderate volatility": "中度波動",
    "low volatility": "波動度偏低",
    "large drawdown risk": "最大回撤風險較高",
    "limited drawdown": "回撤有限",
    "moderate drawdown": "中度回撤",
    "no current position": "目前無持倉",
    "currently profitable": "目前持倉獲利",
    "currently losing": "目前持倉虧損",
    "within max position limit": "持倉權重仍在上限內",
    "position weight high": "持倉權重偏高",
    "high score candidate": "高分候選標的",
    "overbought risk": "過熱風險",
    "position concentration risk": "持股集中風險",
    "insufficient cash": "現金不足",
    "stop loss triggered": "停損條件觸發",
}

PORTFOLIO_COLUMNS = {
    "ticker": "股票代號",
    "display_name": "名稱",
    "market": "市場",
    "shares": "持股數",
    "avg_cost": "平均成本",
    "current_price_native": "原幣現價",
    "current_price_twd": "台幣現價",
    "market_value_twd": "台幣市值",
    "unrealized_pnl_pct": "未實現報酬率",
    "weight": "投資組合權重",
    "action": "建議動作",
}
ACTION_COLUMNS = {
    "ticker": "股票代號",
    "name": "名稱",
    "score": "分數",
    "action": "建議動作",
    "suggested_quantity": "建議股數",
    "suggested_price_range": "建議價格區間",
    "reason": "原因",
    "risk": "風險",
}
NEW_BUY_COLUMNS = {
    "ticker": "股票代號",
    "name": "名稱",
    "market": "市場",
    "score": "分數",
    "suggested_quantity": "建議股數",
    "suggested_price_range": "建議價格區間",
    "reason": "原因",
    "risk": "風險",
}
WATCH_COLUMNS = {
    "ticker": "股票代號",
    "name": "名稱",
    "score": "分數",
    "reason": "原因",
    "risk": "風險",
}
NUMERIC_LABELS = {
    "平均成本",
    "原幣現價",
    "台幣現價",
    "台幣市值",
    "未實現報酬率",
    "投資組合權重",
    "分數",
    "持股數",
    "建議股數",
}
LONG_TEXT_LABELS = {"原因", "風險"}


@dataclass(frozen=True)
class ReportPaths:
    recommendations_path: Path
    screener_result_path: Path
    portfolio_path: Path
    output_dir: Path
    config_dir: Path | None = None


@dataclass(frozen=True)
class ReportResult:
    markdown_path: Path
    html_path: Path


def generate_daily_report(
    settings: dict[str, Any],
    paths: ReportPaths,
    report_date: date | None = None,
) -> ReportResult:
    """Generate daily Markdown and HTML investment helper reports."""

    report_date = report_date or date.today()
    recommendations = _read_csv(paths.recommendations_path)
    screener = _read_csv(paths.screener_result_path)
    portfolio = _read_csv(paths.portfolio_path)
    universe_names = _load_universe_names(paths.config_dir)
    recommendations = apply_display_names(recommendations, portfolio, universe_names)

    paths.output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{report_date:%Y-%m-%d}_daily_report"
    markdown_path = paths.output_dir / f"{stem}.md"
    html_path = paths.output_dir / f"{stem}.html"

    markdown = build_markdown_report(settings, recommendations, screener, portfolio, report_date)
    html = build_html_report(settings, recommendations, screener, portfolio, report_date)

    markdown_path.write_text(markdown, encoding="utf-8")
    html_path.write_text(html, encoding="utf-8")
    return ReportResult(markdown_path=markdown_path, html_path=html_path)


def build_markdown_report(
    settings: dict[str, Any],
    recommendations: pd.DataFrame,
    screener: pd.DataFrame,
    portfolio: pd.DataFrame,
    report_date: date,
) -> str:
    action_counts = _action_counts(recommendations)
    highest = _highest_score(recommendations, screener)
    risks = _risk_summary(recommendations)
    cash_summary = _cash_summary(settings)
    total_assets_twd = _total_assets_twd(recommendations, settings)
    new_buy_candidates = _new_buy_candidates(recommendations)
    add_candidates = _add_candidates(recommendations)

    lines = [
        f"# {REPORT_TITLE}",
        "",
        f"日期：{report_date:%Y-%m-%d}",
        "",
        "## 1. 執行摘要",
        "",
    ]
    lines.extend(f"- {ACTION_LABELS[action]}：{count}" for action, count in action_counts.items())
    lines.extend(
        [
            f"- 最高分標的：{highest}",
            f"- 目前主要風險：{risks if risks else '目前未偵測到重大風險旗標。'}",
            f"- 現金水位摘要：{cash_summary}",
            f"- 總資產估算：{_format_twd(total_assets_twd)}",
            "",
            "## 2. 投資組合摘要",
            "",
            _markdown_table(_portfolio_summary(recommendations)),
            "",
            "## 3. 建議行動",
            "",
        ]
    )

    for action in ACTION_ORDER:
        group = recommendations.loc[recommendations["action"].fillna("") == action]
        lines.extend(
            [
                f"### {ACTION_LABELS[action]}",
                "",
                _markdown_table(_action_table(group)),
                "",
            ]
        )

    lines.extend(
        [
            "## 4. 新增買進候選",
            "",
            _markdown_table(_new_buy_table(new_buy_candidates), empty_message="今日沒有新增買進候選。"),
            "",
            "## 5. 加碼候選",
            "",
            _markdown_table(_action_table(add_candidates), empty_message="今日沒有加碼候選。"),
            "",
            "## 6. 減碼 / 賣出候選",
            "",
            _markdown_table(_action_table(recommendations.loc[recommendations["action"].isin(["REDUCE", "SELL"])])),
            "",
            "## 7. 觀察名單",
            "",
            _markdown_table(_watchlist_table(recommendations.loc[recommendations["action"] == "WATCH"])),
            "",
            "## 8. 風險控制",
            "",
        ]
    )
    lines.extend(_risk_control_lines(recommendations))
    lines.extend(
        [
            "",
            "## 9. 免責聲明",
            "",
            DISCLAIMER,
            "",
        ]
    )
    return "\n".join(lines)


def build_html_report(
    settings: dict[str, Any],
    recommendations: pd.DataFrame,
    screener: pd.DataFrame,
    portfolio: pd.DataFrame,
    report_date: date,
) -> str:
    action_counts = _action_counts(recommendations)
    highest = _highest_score(recommendations, screener)
    risks = _risk_summary(recommendations)
    cash_summary = _cash_summary(settings)
    total_assets_twd = _total_assets_twd(recommendations, settings)
    new_buy_candidates = _new_buy_candidates(recommendations)
    add_candidates = _add_candidates(recommendations)

    action_sections = []
    for action in ACTION_ORDER:
        group = recommendations.loc[recommendations["action"].fillna("") == action]
        action_sections.append(
            f'<section class="card"><h3>{escape(ACTION_LABELS[action])}</h3>{_html_table(_action_table(group))}</section>'
        )

    summary_items = "".join(
        f"<li><strong>{escape(ACTION_LABELS[action])}</strong>：{count}</li>"
        for action, count in action_counts.items()
    )
    risk_lines = "".join(f"<li>{escape(line)}</li>" for line in _risk_control_lines(recommendations))

    return f"""<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="UTF-8">
  <title>{escape(REPORT_TITLE)}</title>
  <style>
    body {{
      margin: 0;
      background: #f5f7fb;
      color: #1f2937;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft JhengHei", "Noto Sans TC", Arial, sans-serif;
      line-height: 1.6;
    }}
    .page {{
      max-width: 1200px;
      margin: 0 auto;
      padding: 32px 24px 48px;
    }}
    header, section.card {{
      background: #ffffff;
      border: 1px solid #e5e7eb;
      border-radius: 8px;
      box-shadow: 0 8px 24px rgba(15, 23, 42, 0.06);
      margin-bottom: 20px;
      padding: 24px;
    }}
    h1, h2, h3 {{
      margin-top: 0;
      color: #111827;
    }}
    h1 {{
      font-size: 28px;
      margin-bottom: 8px;
    }}
    h2 {{
      border-bottom: 1px solid #e5e7eb;
      font-size: 22px;
      padding-bottom: 10px;
    }}
    h3 {{
      font-size: 18px;
    }}
    .table-wrap {{
      overflow-x: auto;
      width: 100%;
    }}
    table {{
      border-collapse: collapse;
      min-width: 100%;
      width: 100%;
    }}
    th, td {{
      border: 1px solid #d1d5db;
      padding: 10px 12px;
      vertical-align: top;
    }}
    th {{
      background: #eef2f7;
      color: #111827;
      font-weight: 700;
      white-space: nowrap;
    }}
    td {{
      background: #ffffff;
      overflow-wrap: anywhere;
      white-space: normal;
    }}
    td.num {{
      font-variant-numeric: tabular-nums;
      text-align: right;
      white-space: nowrap;
    }}
    td.long-text {{
      min-width: 220px;
    }}
    td.long-text ul {{
      margin: 0;
      padding-left: 18px;
    }}
    .badge {{
      border-radius: 999px;
      display: inline-block;
      font-size: 12px;
      font-weight: 700;
      line-height: 1;
      padding: 6px 10px;
      white-space: nowrap;
    }}
    .badge-buy {{ background: #dcfce7; color: #166534; }}
    .badge-add {{ background: #dbeafe; color: #1d4ed8; }}
    .badge-hold {{ background: #e5e7eb; color: #374151; }}
    .badge-watch {{ background: #fef3c7; color: #92400e; }}
    .badge-reduce {{ background: #ffedd5; color: #c2410c; }}
    .badge-sell {{ background: #fee2e2; color: #b91c1c; }}
    .muted {{
      color: #6b7280;
    }}
  </style>
</head>
<body>
  <main class="page">
    <header>
      <h1>{escape(REPORT_TITLE)}</h1>
      <p class="muted">日期：{report_date:%Y-%m-%d}</p>
    </header>

    <section class="card">
      <h2>1. 執行摘要</h2>
      <ul>
        {summary_items}
        <li><strong>最高分標的</strong>：{escape(highest)}</li>
        <li><strong>目前主要風險</strong>：{escape(risks if risks else "目前未偵測到重大風險旗標。")}</li>
        <li><strong>現金水位摘要</strong>：{escape(cash_summary)}</li>
        <li><strong>總資產估算</strong>：{escape(_format_twd(total_assets_twd))}</li>
      </ul>
    </section>

    <section class="card">
      <h2>2. 投資組合摘要</h2>
      {_html_table(_portfolio_summary(recommendations))}
    </section>

    <section class="card">
      <h2>3. 建議行動</h2>
    </section>
    {''.join(action_sections)}

    <section class="card">
      <h2>4. 新增買進候選</h2>
      {_html_table(_new_buy_table(new_buy_candidates), empty_message="今日沒有新增買進候選。")}
    </section>

    <section class="card">
      <h2>5. 加碼候選</h2>
      {_html_table(_action_table(add_candidates), empty_message="今日沒有加碼候選。")}
    </section>

    <section class="card">
      <h2>6. 減碼 / 賣出候選</h2>
      {_html_table(_action_table(recommendations.loc[recommendations["action"].isin(["REDUCE", "SELL"])]))}
    </section>

    <section class="card">
      <h2>7. 觀察名單</h2>
      {_html_table(_watchlist_table(recommendations.loc[recommendations["action"] == "WATCH"]))}
    </section>

    <section class="card">
      <h2>8. 風險控制</h2>
      <ul>{risk_lines}</ul>
    </section>

    <section class="card">
      <h2>9. 免責聲明</h2>
      <p>{escape(DISCLAIMER)}</p>
    </section>
  </main>
</body>
</html>
"""


def _read_csv(path: Path) -> pd.DataFrame:
    data_path = Path(path)
    if not data_path.exists():
        raise FileNotFoundError(f"Required report input not found: {data_path}")
    return pd.read_csv(data_path)


def apply_display_names(
    recommendations: pd.DataFrame,
    portfolio: pd.DataFrame,
    universe_names: dict[str, str],
) -> pd.DataFrame:
    result = recommendations.copy()
    if result.empty:
        result["display_name"] = []
        return result

    portfolio_notes = _portfolio_notes(portfolio)
    display_names = []
    for _, row in result.iterrows():
        ticker = str(row.get("ticker", "")).strip()
        display_names.append(
            get_display_name(
                ticker=ticker,
                recommendation_name=row.get("name", ""),
                portfolio_note=portfolio_notes.get(ticker, ""),
                universe_names=universe_names,
            )
        )
    result["display_name"] = display_names
    result["name"] = result["display_name"]
    return result


def get_display_name(
    ticker: str,
    recommendation_name: Any = "",
    portfolio_note: Any = "",
    universe_names: dict[str, str] | None = None,
) -> str:
    universe_names = universe_names or {}
    for value in (recommendation_name, portfolio_note, universe_names.get(ticker, ""), ticker):
        if pd.isna(value):
            continue
        text = str(value).strip()
        if text:
            return text
    return ticker


def _portfolio_notes(portfolio: pd.DataFrame) -> dict[str, str]:
    if portfolio.empty or "ticker" not in portfolio or "note" not in portfolio:
        return {}
    notes = {}
    for _, row in portfolio.iterrows():
        ticker = str(row.get("ticker", "")).strip()
        note = row.get("note", "")
        if ticker and not pd.isna(note):
            notes[ticker] = str(note).strip()
    return notes


def _load_universe_names(config_dir: Path | None) -> dict[str, str]:
    if config_dir is None:
        return {}

    names = {}
    for filename in ("universe_tw.csv", "universe_us.csv"):
        path = Path(config_dir) / filename
        if not path.exists():
            continue
        data = pd.read_csv(path)
        if "ticker" not in data or "name" not in data:
            continue
        for _, row in data.iterrows():
            ticker = str(row.get("ticker", "")).strip()
            name = row.get("name", "")
            if ticker and not pd.isna(name) and str(name).strip():
                names[ticker] = str(name).strip()
    return names


def _action_counts(recommendations: pd.DataFrame) -> dict[str, int]:
    counts = recommendations["action"].fillna("").value_counts().to_dict() if "action" in recommendations else {}
    return {action: int(counts.get(action, 0)) for action in ACTION_ORDER}


def _highest_score(recommendations: pd.DataFrame, screener: pd.DataFrame) -> str:
    source = recommendations if "score" in recommendations and not recommendations.empty else screener
    if source.empty or "score" not in source:
        return "N/A"
    scored = source.copy()
    scored["score"] = pd.to_numeric(scored["score"], errors="coerce")
    scored = scored.dropna(subset=["score"])
    if scored.empty:
        return "N/A"
    row = scored.sort_values("score", ascending=False).iloc[0]
    return f"{row.get('ticker', '')} {row.get('name', '')}（{int(row['score'])} 分）".strip()


def _portfolio_summary(recommendations: pd.DataFrame) -> pd.DataFrame:
    columns = list(PORTFOLIO_COLUMNS.keys())
    if recommendations.empty:
        return pd.DataFrame(columns=list(PORTFOLIO_COLUMNS.values()))
    data = recommendations.loc[pd.to_numeric(recommendations["shares"], errors="coerce").fillna(0) > 0]
    return _format_table_values(data.reindex(columns=columns), PORTFOLIO_COLUMNS)


def _action_table(data: pd.DataFrame) -> pd.DataFrame:
    return _format_table_values(data.reindex(columns=list(ACTION_COLUMNS.keys())), ACTION_COLUMNS)


def _new_buy_table(data: pd.DataFrame) -> pd.DataFrame:
    return _format_table_values(data.reindex(columns=list(NEW_BUY_COLUMNS.keys())), NEW_BUY_COLUMNS)


def _watchlist_table(data: pd.DataFrame) -> pd.DataFrame:
    return _format_table_values(data.reindex(columns=list(WATCH_COLUMNS.keys())), WATCH_COLUMNS)


def _new_buy_candidates(recommendations: pd.DataFrame) -> pd.DataFrame:
    if recommendations.empty:
        return recommendations
    shares = _numeric_column(recommendations, "shares")
    suggested_quantity = _numeric_column(recommendations, "suggested_quantity")
    reason = _text_column(recommendations, "reason")
    risk = _text_column(recommendations, "risk")
    position_text = (reason + "; " + risk).str.lower()
    no_position = shares == 0
    no_position = (
        no_position
        | position_text.str.contains("no current position", regex=False)
        | position_text.str.contains("currently no position", regex=False)
    )
    return recommendations.loc[
        no_position
        & (recommendations["action"].fillna("") == "BUY")
        & (suggested_quantity > 0)
    ]


def _add_candidates(recommendations: pd.DataFrame) -> pd.DataFrame:
    if recommendations.empty:
        return recommendations
    shares = _numeric_column(recommendations, "shares")
    return recommendations.loc[(shares > 0) & (recommendations["action"].fillna("") == "ADD")]


def _format_table_values(data: pd.DataFrame, labels: dict[str, str]) -> pd.DataFrame:
    result = data.copy()
    for column in result.columns:
        if column in {"unrealized_pnl_pct", "weight"}:
            result[column] = pd.to_numeric(result[column], errors="coerce").map(_format_pct)
        elif column in {"current_price_twd", "market_value_twd"}:
            result[column] = pd.to_numeric(result[column], errors="coerce").map(_format_twd)
        elif column in {"avg_cost", "current_price_native"}:
            result[column] = [
                _format_native_amount(value, market)
                for value, market in zip(
                    pd.to_numeric(result[column], errors="coerce"),
                    _text_column(result, "market"),
                    strict=False,
                )
            ]
        elif column in {"shares", "score", "suggested_quantity"}:
            result[column] = pd.to_numeric(result[column], errors="coerce").map(_format_quantity)
        elif column == "action":
            result[column] = result[column].fillna("").astype(str).map(_format_action_label)
        elif column in {"reason", "risk"}:
            result[column] = result[column].fillna("").astype(str).map(_translate_long_text)
        else:
            result[column] = result[column].fillna("").astype(str)
    return result.rename(columns=labels)


def _markdown_table(data: pd.DataFrame, empty_message: str = "無資料。") -> str:
    if data.empty:
        return empty_message
    headers = list(data.columns)
    rows = data.fillna("").astype(str).values.tolist()
    header_line = "| " + " | ".join(headers) + " |"
    separator_line = "| " + " | ".join("---" for _ in headers) + " |"
    row_lines = ["| " + " | ".join(_escape_markdown_cell(cell) for cell in row) + " |" for row in rows]
    return "\n".join([header_line, separator_line, *row_lines])


def _html_table(data: pd.DataFrame, empty_message: str = "無資料。") -> str:
    if data.empty:
        return f"<p>{escape(empty_message)}</p>"
    headers = "".join(f"<th>{escape(str(column))}</th>" for column in data.columns)
    rows = []
    for _, row in data.fillna("").astype(str).iterrows():
        cells = []
        for column, value in row.items():
            column_name = str(column)
            value_text = str(value)
            classes = []
            if column_name in NUMERIC_LABELS:
                classes.append("num")
            if column_name in LONG_TEXT_LABELS:
                classes.append("long-text")
            class_attr = f' class="{" ".join(classes)}"' if classes else ""
            cells.append(f"<td{class_attr}>{_html_cell(column_name, value_text)}</td>")
        rows.append(f"<tr>{''.join(cells)}</tr>")
    return f'<div class="table-wrap"><table><thead><tr>{headers}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>'


def _html_cell(column: str, value: str) -> str:
    if column == "建議動作":
        action = _action_from_label(value)
        badge_class = ACTION_BADGE_CLASSES.get(action, "badge-hold")
        return f'<span class="badge {badge_class}">{escape(value)}</span>'
    if column in LONG_TEXT_LABELS:
        items = _split_translated_text(value)
        if not items:
            return ""
        return "<ul>" + "".join(f"<li>{escape(item)}</li>" for item in items) + "</ul>"
    return escape(value)


def _risk_control_lines(recommendations: pd.DataFrame) -> list[str]:
    lines = []
    for risk in RISK_FLAGS:
        tickers = _tickers_with_risk(recommendations, risk)
        if tickers:
            lines.append(f"{_translate_phrase(risk)}：{', '.join(tickers)}")
    if not lines:
        return ["目前未偵測到重大風險旗標。"]
    return lines


def _tickers_with_risk(recommendations: pd.DataFrame, risk: str) -> list[str]:
    if recommendations.empty or "risk" not in recommendations:
        return []
    mask = recommendations["risk"].fillna("").str.contains(risk, case=False, regex=False)
    return recommendations.loc[mask, "ticker"].fillna("").astype(str).tolist()


def _risk_summary(recommendations: pd.DataFrame) -> str:
    risks = [_translate_phrase(risk) for risk in RISK_FLAGS if _tickers_with_risk(recommendations, risk)]
    return "、".join(risks)


def _cash_summary(settings: dict[str, Any]) -> str:
    portfolio = settings.get("portfolio", {}) if isinstance(settings, dict) else {}
    fx = settings.get("fx", {}) if isinstance(settings, dict) else {}
    cash_twd = float(portfolio.get("cash_twd", 0.0))
    cash_usd = float(portfolio.get("cash_usd", 0.0))
    usd_twd = float(fx.get("USD_TWD", 1.0))
    return f"台幣現金 {_format_twd(cash_twd)}；美元現金 {_format_usd(cash_usd)}；匯率 USD/TWD {_format_number(usd_twd)}"


def _total_assets_twd(recommendations: pd.DataFrame, settings: dict[str, Any]) -> float:
    portfolio = settings.get("portfolio", {}) if isinstance(settings, dict) else {}
    fx = settings.get("fx", {}) if isinstance(settings, dict) else {}
    cash_twd = float(portfolio.get("cash_twd", 0.0))
    cash_usd = float(portfolio.get("cash_usd", 0.0))
    usd_twd = float(fx.get("USD_TWD", 1.0))
    holdings_twd = pd.to_numeric(
        _numeric_column(recommendations, "market_value_twd"), errors="coerce"
    ).fillna(0).sum()
    return float(holdings_twd + cash_twd + cash_usd * usd_twd)


def _text_column(data: pd.DataFrame, column: str) -> pd.Series:
    if column in data.columns:
        return data[column].fillna("").astype(str)
    return pd.Series([""] * len(data), index=data.index, dtype=str)


def _numeric_column(data: pd.DataFrame, column: str) -> pd.Series:
    if column in data.columns:
        source = data[column]
    else:
        source = pd.Series([0.0] * len(data), index=data.index, dtype=float)
    return pd.to_numeric(source, errors="coerce").fillna(0.0)


def _translate_long_text(value: str) -> str:
    return "；".join(_translate_phrase(item) for item in _split_raw_text(value))


def _translate_phrase(value: str) -> str:
    text = value.strip()
    return TEXT_TRANSLATIONS.get(text, text)


def _split_raw_text(value: str) -> list[str]:
    return [item.strip() for item in str(value).split(";") if item.strip()]


def _split_translated_text(value: str) -> list[str]:
    return [item.strip() for item in str(value).split("；") if item.strip()]


def _format_action_label(action: str) -> str:
    return ACTION_LABELS.get(action, action)


def _action_from_label(label: str) -> str:
    for action, translated in ACTION_LABELS.items():
        if translated == label:
            return action
    return label


def _format_native_amount(value: float, market: str) -> str:
    if pd.isna(value):
        return ""
    if str(market).upper() == "US":
        return _format_usd(value)
    return _format_twd(value)


def _format_twd(value: float) -> str:
    if pd.isna(value):
        return ""
    return f"NT${float(value):,.2f}"


def _format_usd(value: float) -> str:
    if pd.isna(value):
        return ""
    return f"US${float(value):,.2f}"


def _format_number(value: float) -> str:
    if pd.isna(value):
        return ""
    return f"{float(value):,.2f}"


def _format_pct(value: float) -> str:
    if pd.isna(value):
        return ""
    return f"{float(value) * 100:.2f}%"


def _format_quantity(value: float) -> str:
    if pd.isna(value):
        return ""
    if float(value).is_integer():
        return str(int(value))
    return f"{float(value):.2f}"


def _escape_markdown_cell(value: str) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")
