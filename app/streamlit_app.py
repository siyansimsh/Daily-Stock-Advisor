"""Local Streamlit dashboard for Daily Stock Advisor."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
import yaml

import sys

# Ensure project root is on sys.path so the `src` package is importable
# when running Streamlit from the `app/` directory.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.report_generator import ACTION_LABELS, TEXT_TRANSLATIONS
DATA_DIR = PROJECT_ROOT / "data"
REPORTS_DIR = PROJECT_ROOT / "reports"
CONFIG_PATH = PROJECT_ROOT / "config" / "settings.yaml"
PORTFOLIO_PATH = DATA_DIR / "portfolio.csv"
RECOMMENDATIONS_PATH = DATA_DIR / "recommendations.csv"
TRANSACTIONS_PATH = DATA_DIR / "transactions.csv"

ACTION_ORDER = ["BUY", "ADD", "HOLD", "REDUCE", "SELL", "WATCH"]
ACTION_BADGE_STYLES = {
    "BUY": ("#166534", "#dcfce7"),
    "ADD": ("#1d4ed8", "#dbeafe"),
    "HOLD": ("#374151", "#e5e7eb"),
    "WATCH": ("#92400e", "#fef3c7"),
    "REDUCE": ("#c2410c", "#ffedd5"),
    "SELL": ("#b91c1c", "#fee2e2"),
}

COLUMN_LABELS = {
    "ticker": "股票代號",
    "market": "市場",
    "name": "名稱",
    "shares": "持股數",
    "avg_cost": "平均成本",
    "current_price": "現價",
    "current_price_native": "原幣現價",
    "current_price_twd": "台幣現價",
    "market_value_native": "原幣市值",
    "market_value_twd": "台幣市值",
    "unrealized_pnl_native": "未實現損益",
    "unrealized_pnl_pct": "未實現報酬率",
    "weight": "投資組合權重",
    "score": "分數",
    "signal": "訊號",
    "action": "建議動作",
    "confidence": "信心分數",
    "suggested_quantity": "建議股數",
    "suggested_price_range": "建議價格區間",
    "reason": "原因",
    "risk": "風險",
    "date": "日期",
    "side": "買賣方向",
    "price": "成交價格",
    "fee": "手續費",
    "tax": "交易稅",
    "currency": "幣別",
    "sector": "產業",
    "note": "備註",
}

WORKFLOW_COMMANDS = """python -m src.main build-portfolio
python -m src.main update-data --force
python -m src.main screen
python -m src.main recommend
python -m src.main generate-report"""


def main() -> None:
    st.set_page_config(page_title="Daily Stock Advisor", layout="wide")
    _inject_css()

    st.title("每日 TW / 美國股票投資儀表板")
    st.caption("本介面僅讀取本機 CSV 與每日報告，用於輔助檢視，不提供下單或券商串接功能。")

    page = render_sidebar()
    settings = load_settings(CONFIG_PATH)
    portfolio = read_csv(PORTFOLIO_PATH)
    recommendations = read_csv(RECOMMENDATIONS_PATH)
    transactions = read_csv(TRANSACTIONS_PATH)

    if page == "Dashboard":
        render_dashboard(settings, recommendations, portfolio)
    elif page == "Portfolio":
        render_portfolio(portfolio, recommendations)
    elif page == "Recommendations":
        render_recommendations(recommendations)
    elif page == "Watchlist":
        render_watchlist(recommendations)
    elif page == "Report":
        render_report()
    elif page == "Transactions":
        render_transactions(transactions)


def render_sidebar() -> str:
    st.sidebar.title("Daily Stock Advisor")
    page = st.sidebar.radio(
        "頁面",
        ["Dashboard", "Portfolio", "Recommendations", "Watchlist", "Report", "Transactions"],
    )
    st.sidebar.divider()
    st.sidebar.subheader("建議每日執行流程")
    st.sidebar.code(WORKFLOW_COMMANDS, language="powershell")
    st.sidebar.info("若畫面資料不存在或過期，請先在終端機執行上方流程。")
    return page


def render_dashboard(settings: dict[str, Any], recommendations: pd.DataFrame, portfolio: pd.DataFrame) -> None:
    st.header("Dashboard")
    if recommendations.empty:
        show_missing_data_notice("data/recommendations.csv")

    cash_twd, cash_usd, usd_twd = cash_settings(settings)
    holding_value_twd = total_holding_value_twd(recommendations, portfolio, usd_twd)
    total_assets_twd = holding_value_twd + cash_twd + cash_usd * usd_twd

    metric_cols = st.columns(4)
    metric_cols[0].metric("總資產估算", format_twd(total_assets_twd))
    metric_cols[1].metric("台幣現金", format_twd(cash_twd))
    metric_cols[2].metric("美元現金", format_usd(cash_usd))
    metric_cols[3].metric("持倉市值", format_twd(holding_value_twd))

    st.subheader("今日建議動作統計")
    counts = action_counts(recommendations)
    action_cols = st.columns(len(ACTION_ORDER))
    for column, action in zip(action_cols, ACTION_ORDER, strict=True):
        column.metric(ACTION_LABELS.get(action, action), counts.get(action, 0))

    st.subheader("主要風險提示")
    risks = risk_summary(recommendations)
    if risks:
        for risk in risks:
            st.warning(risk)
    else:
        st.success("目前沒有重大風險旗標。")


def render_portfolio(portfolio: pd.DataFrame, recommendations: pd.DataFrame) -> None:
    st.header("Portfolio")
    if portfolio.empty:
        show_missing_data_notice("data/portfolio.csv")
    else:
        st.subheader("portfolio.csv")
        st.dataframe(to_display_dataframe(portfolio), use_container_width=True, hide_index=True)

    st.subheader("持倉摘要")
    if recommendations.empty:
        show_missing_data_notice("data/recommendations.csv")
        return

    holdings = recommendations.loc[numeric_column(recommendations, "shares") > 0]
    if holdings.empty:
        st.info("目前 recommendations.csv 中沒有持倉資料。")
        return

    columns = [
        "ticker",
        "name",
        "market",
        "shares",
        "avg_cost",
        "current_price_native",
        "current_price_twd",
        "market_value_twd",
        "unrealized_pnl_pct",
        "weight",
        "action",
        "risk",
    ]
    st.dataframe(to_display_dataframe(holdings, columns), use_container_width=True, hide_index=True)


def render_recommendations(recommendations: pd.DataFrame) -> None:
    st.header("Recommendations")
    if recommendations.empty:
        show_missing_data_notice("data/recommendations.csv")
        return

    for action in ACTION_ORDER:
        group = recommendations.loc[recommendations["action"].fillna("") == action]
        st.markdown(action_badge(action), unsafe_allow_html=True)
        if group.empty:
            st.info(f"目前沒有{ACTION_LABELS.get(action, action)}標的。")
            continue

        columns = [
            "ticker",
            "name",
            "market",
            "score",
            "signal",
            "action",
            "suggested_quantity",
            "suggested_price_range",
            "reason",
            "risk",
        ]
        st.dataframe(to_display_dataframe(group, columns), use_container_width=True, hide_index=True)


def render_watchlist(recommendations: pd.DataFrame) -> None:
    st.header("Watchlist")
    if recommendations.empty:
        show_missing_data_notice("data/recommendations.csv")
        return

    watchlist = recommendations.loc[recommendations["action"].fillna("") == "WATCH"]
    if watchlist.empty:
        st.info("目前沒有觀察名單。")
        return

    columns = ["ticker", "name", "market", "score", "signal", "reason", "risk"]
    st.dataframe(to_display_dataframe(watchlist, columns), use_container_width=True, hide_index=True)

    risky = watchlist.loc[text_column(watchlist, "risk") != ""]
    if not risky.empty:
        st.subheader("觀察名單風險")
        st.dataframe(to_display_dataframe(risky, ["ticker", "name", "risk"]), use_container_width=True, hide_index=True)


def render_report() -> None:
    st.header("Report")
    html_path = latest_file("*_daily_report.html")
    markdown_path = latest_file("*_daily_report.md")

    if html_path:
        st.caption(f"目前顯示：{html_path.name}")
        html = html_path.read_text(encoding="utf-8")
        components.html(html, height=900, scrolling=True)
        return

    if markdown_path:
        st.caption(f"目前顯示：{markdown_path.name}")
        st.markdown(markdown_path.read_text(encoding="utf-8"))
        return

    show_missing_data_notice("reports/YYYY-MM-DD_daily_report.html")


def render_transactions(transactions: pd.DataFrame) -> None:
    st.header("Transactions")
    st.info("目前交易流水帳仍需手動編輯 data/transactions.csv。編輯後請執行 build-portfolio 重新產生 portfolio.csv。")
    st.code("python -m src.main build-portfolio", language="powershell")

    if transactions.empty:
        show_missing_data_notice("data/transactions.csv")
        return

    st.dataframe(to_display_dataframe(transactions), use_container_width=True, hide_index=True)


def load_settings(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()


def latest_file(pattern: str) -> Path | None:
    files = sorted(REPORTS_DIR.glob(pattern), key=lambda path: path.stat().st_mtime, reverse=True)
    return files[0] if files else None


def cash_settings(settings: dict[str, Any]) -> tuple[float, float, float]:
    portfolio = settings.get("portfolio", {}) if isinstance(settings, dict) else {}
    fx = settings.get("fx", {}) if isinstance(settings, dict) else {}
    return (
        float(portfolio.get("cash_twd", 0) or 0),
        float(portfolio.get("cash_usd", 0) or 0),
        float(fx.get("USD_TWD", 1) or 1),
    )


def total_holding_value_twd(recommendations: pd.DataFrame, portfolio: pd.DataFrame, usd_twd: float) -> float:
    if not recommendations.empty and "market_value_twd" in recommendations.columns:
        return float(numeric_column(recommendations, "market_value_twd").sum())
    if portfolio.empty or "shares" not in portfolio.columns or "current_price" not in portfolio.columns:
        return 0.0

    shares = numeric_column(portfolio, "shares")
    prices = numeric_column(portfolio, "current_price")
    markets = text_column(portfolio, "market").str.upper()
    values = shares * prices
    values = values.where(markets != "US", values * usd_twd)
    return float(values.sum())


def action_counts(recommendations: pd.DataFrame) -> dict[str, int]:
    if recommendations.empty or "action" not in recommendations.columns:
        return {action: 0 for action in ACTION_ORDER}
    counts = recommendations["action"].fillna("").value_counts().to_dict()
    return {action: int(counts.get(action, 0)) for action in ACTION_ORDER}


def risk_summary(recommendations: pd.DataFrame) -> list[str]:
    if recommendations.empty or "risk" not in recommendations.columns:
        return []

    risks = []
    risk_text = text_column(recommendations, "risk")
    for phrase in [
        "position concentration risk",
        "overbought risk",
        "high volatility",
        "large drawdown risk",
        "insufficient cash",
        "stop loss triggered",
    ]:
        mask = risk_text.str.contains(phrase, case=False, regex=False)
        tickers = recommendations.loc[mask, "ticker"].fillna("").astype(str).tolist()
        if tickers:
            risks.append(f"{translate_phrase(phrase)}：{', '.join(tickers)}")
    return risks


def to_display_dataframe(data: pd.DataFrame, columns: list[str] | None = None) -> pd.DataFrame:
    if data.empty:
        return pd.DataFrame()
    selected = data.reindex(columns=columns) if columns else data.copy()
    result = selected.copy()
    for column in result.columns:
        if column == "action":
            # Convert value to str before using as dict key to satisfy type checkers
            result[column] = result[column].fillna("").astype(str).map(
                lambda value: ACTION_LABELS.get(str(value)) or str(value)
            )
        elif column in {"reason", "risk"}:
            result[column] = result[column].fillna("").astype(str).map(translate_long_text)
        elif column in {"unrealized_pnl_pct", "weight", "confidence"}:
            result[column] = numeric_column(result, column).map(format_pct)
        elif column in {"current_price_twd", "market_value_twd"}:
            result[column] = numeric_column(result, column).map(format_twd)
        elif column in {"avg_cost", "current_price", "current_price_native", "market_value_native", "unrealized_pnl_native", "price"}:
            result[column] = result[column].map(format_number_cell)
        elif column in {"shares", "score", "suggested_quantity"}:
            result[column] = numeric_column(result, column).map(format_quantity)
        else:
            result[column] = result[column].fillna("").astype(str)
    return result.rename(columns=COLUMN_LABELS)


def translate_long_text(value: str) -> str:
    items = [translate_phrase(item.strip()) for item in str(value).split(";") if item.strip()]
    return "\n".join(items)


def translate_phrase(value: str) -> str:
    return TEXT_TRANSLATIONS.get(value.strip(), value.strip())


def show_missing_data_notice(path_text: str) -> None:
    st.warning(f"找不到或無法讀取 {path_text}。請先執行每日流程產生資料。")
    st.code(WORKFLOW_COMMANDS, language="powershell")


def action_badge(action: str) -> str:
    color, background = ACTION_BADGE_STYLES.get(action, ("#374151", "#e5e7eb"))
    label = ACTION_LABELS.get(action, action)
    return (
        f'<div class="action-heading">'
        f'<span class="action-badge" style="color:{color}; background:{background};">{label}</span>'
        f"</div>"
    )


def text_column(data: pd.DataFrame, column: str) -> pd.Series:
    if column in data.columns:
        return data[column].fillna("").astype(str)
    return pd.Series([""] * len(data), index=data.index, dtype=str)


def numeric_column(data: pd.DataFrame, column: str) -> pd.Series:
    if column in data.columns:
        source = data[column]
    else:
        source = pd.Series([0.0] * len(data), index=data.index, dtype=float)
    return pd.to_numeric(source, errors="coerce").fillna(0.0)


def format_twd(value: float) -> str:
    return f"NT${float(value):,.2f}"


def format_usd(value: float) -> str:
    return f"US${float(value):,.2f}"


def format_pct(value: float) -> str:
    return "" if pd.isna(value) else f"{float(value) * 100:.2f}%"


def format_quantity(value: float) -> str:
    if pd.isna(value):
        return ""
    number = float(value)
    return str(int(number)) if number.is_integer() else f"{number:,.2f}"


def format_number_cell(value: Any) -> str:
    if pd.isna(value) or value == "":
        return ""
    number = float(value)
    return f"{number:,.2f}"


def _inject_css() -> None:
    st.markdown(
        """
        <style>
        .action-heading {
            margin: 1.25rem 0 0.5rem;
        }
        .action-badge {
            border-radius: 999px;
            display: inline-block;
            font-size: 0.9rem;
            font-weight: 700;
            padding: 0.35rem 0.75rem;
        }
        div[data-testid="stMetric"] {
            background: #ffffff;
            border: 1px solid #e5e7eb;
            border-radius: 8px;
            padding: 0.75rem;
            color: #111827; /* 確保文字為深色，與白底有對比 */
        }
        /* 指定 metric 的值與標籤為深色（使用 data-testid 可較穩定選到元素） */
        div[data-testid="stMetric"] [data-testid="stMetricValue"],
        div[data-testid="stMetric"] [data-testid="stMetricLabel"] {
            color: #111827 !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
