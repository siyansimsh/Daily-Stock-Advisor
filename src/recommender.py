"""Personalized recommendation engine for Phase 3."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from src.portfolio import calculate_portfolio_metrics, convert_price_to_twd, load_portfolio


RECOMMENDATION_COLUMNS = [
    "ticker",
    "market",
    "name",
    "shares",
    "avg_cost",
    "current_price_native",
    "current_price_twd",
    "market_value_native",
    "market_value_twd",
    "unrealized_pnl_native",
    "unrealized_pnl_pct",
    "weight",
    "score",
    "signal",
    "action",
    "confidence",
    "suggested_quantity",
    "suggested_price_range",
    "reason",
    "risk",
]


@dataclass(frozen=True)
class RecommendationPaths:
    portfolio_path: Path
    screener_result_path: Path
    output_path: Path


@dataclass(frozen=True)
class PortfolioSettings:
    max_position_weight: float
    stop_loss_pct: float
    usd_twd: float
    cash_twd: float
    cash_usd: float
    tw_lot_size: int
    us_lot_size: int


def generate_recommendations(
    settings: dict[str, Any],
    paths: RecommendationPaths,
) -> pd.DataFrame:
    """Create personalized recommendations and write them to CSV."""

    portfolio_settings = _portfolio_settings(settings)
    portfolio = load_portfolio(paths.portfolio_path)
    portfolio_metrics = calculate_portfolio_metrics(
        portfolio,
        max_position_weight=portfolio_settings.max_position_weight,
        usd_twd=portfolio_settings.usd_twd,
        cash_twd=portfolio_settings.cash_twd,
        cash_usd=portfolio_settings.cash_usd,
    )
    screener = load_screener_results(paths.screener_result_path)
    screener_records = _dataframe_records(screener)
    screener_by_ticker = {str(row.get("ticker", "")).strip(): row for row in screener_records}

    total_portfolio_value_twd = _total_portfolio_value_twd(portfolio_metrics, portfolio_settings)
    rows = []
    held_tickers = set()
    for holding in _dataframe_records(portfolio_metrics):
        ticker = str(holding["ticker"]).strip()
        held_tickers.add(ticker)
        rows.append(
            recommend_holding(
                holding=holding,
                screener_row=screener_by_ticker.get(ticker),
                total_portfolio_value_twd=total_portfolio_value_twd,
                settings=portfolio_settings,
            )
        )

    for candidate in screener_records:
        ticker = str(candidate["ticker"]).strip()
        if ticker in held_tickers:
            continue
        recommendation = recommend_candidate(
            screener_row=candidate,
            total_portfolio_value_twd=total_portfolio_value_twd,
            settings=portfolio_settings,
        )
        if recommendation is not None:
            rows.append(recommendation)

    result = pd.DataFrame(rows, columns=RECOMMENDATION_COLUMNS)
    paths.output_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(paths.output_path, index=False)
    return result


def _dataframe_records(data: pd.DataFrame) -> list[dict[str, Any]]:
    return [{str(key): value for key, value in record.items()} for record in data.to_dict("records")]


def load_screener_results(path: str | Path) -> pd.DataFrame:
    screener_path = Path(path)
    if not screener_path.exists():
        raise FileNotFoundError(f"Screener result file not found: {screener_path}")

    data = pd.read_csv(screener_path)
    required = {"ticker", "market", "name", "close", "score", "signal", "reason"}
    missing = required - set(data.columns)
    if missing:
        raise ValueError(f"Screener result is missing columns: {sorted(missing)}")

    result = data.copy()
    result["ticker"] = result["ticker"].astype(str).str.strip()
    result["market"] = result["market"].astype(str).str.strip()
    result["score"] = pd.to_numeric(result["score"], errors="coerce").fillna(0).clip(0, 100)
    result["close"] = pd.to_numeric(result["close"], errors="coerce")
    result["reason"] = result["reason"].fillna("")
    return result.loc[result["ticker"] != ""]


def recommend_holding(
    holding: dict[str, Any],
    screener_row: dict[str, Any] | None,
    total_portfolio_value_twd: float,
    settings: PortfolioSettings,
) -> dict[str, Any]:
    score = _score(screener_row)
    signal = _text(screener_row, "signal")
    screener_reason = _text(screener_row, "reason") or "missing screener result"
    market = _market(holding.get("market") or _text(screener_row, "market"))
    current_price_native = _first_number(holding.get("current_price_native"), holding.get("current_price"), _value(screener_row, "close"))
    current_price_twd = _first_number(
        holding.get("current_price_twd"),
        convert_price_to_twd(current_price_native, market, settings.usd_twd),
    )
    shares = _number(holding.get("shares"), default=0.0)
    avg_cost = _number(holding.get("avg_cost"), default=0.0)
    market_value_native = shares * current_price_native
    market_value_twd = shares * current_price_twd
    cost_basis_native = shares * avg_cost
    unrealized_pnl_native = market_value_native - cost_basis_native
    unrealized_pnl_pct = unrealized_pnl_native / cost_basis_native if cost_basis_native else math.nan
    weight = market_value_twd / total_portfolio_value_twd if total_portfolio_value_twd > 0 else 0.0

    stop_loss_triggered = _not_nan(unrealized_pnl_pct) and unrealized_pnl_pct <= settings.stop_loss_pct
    action = _holding_action(
        score=score,
        signal=signal,
        unrealized_pnl_pct=unrealized_pnl_pct,
        weight=weight,
        max_position_weight=settings.max_position_weight,
        stop_loss_triggered=stop_loss_triggered,
    )
    suggested_quantity, insufficient_cash = _suggested_quantity(
        action=action,
        market=market,
        shares=shares,
        current_price_native=current_price_native,
        current_price_twd=current_price_twd,
        market_value_twd=market_value_twd,
        total_portfolio_value_twd=total_portfolio_value_twd,
        settings=settings,
    )

    reasons = [screener_reason]
    if _not_nan(unrealized_pnl_pct) and unrealized_pnl_pct > 0:
        reasons.append("currently profitable")
    elif _not_nan(unrealized_pnl_pct) and unrealized_pnl_pct < 0:
        reasons.append("currently losing")
    if weight > settings.max_position_weight:
        reasons.append("position weight high")
    else:
        reasons.append("within max position limit")

    risks = _risk_reasons(screener_reason)
    if stop_loss_triggered:
        risks.append("stop loss triggered")
    if weight > settings.max_position_weight:
        risks.append("position concentration risk")
    if insufficient_cash:
        risks.append("insufficient cash")

    return _recommendation_row(
        ticker=holding["ticker"],
        market=market,
        name=_text(screener_row, "name"),
        shares=shares,
        avg_cost=avg_cost,
        current_price_native=current_price_native,
        current_price_twd=current_price_twd,
        market_value_native=market_value_native,
        market_value_twd=market_value_twd,
        unrealized_pnl_native=unrealized_pnl_native,
        unrealized_pnl_pct=unrealized_pnl_pct,
        weight=weight,
        score=score,
        signal=signal,
        action=action,
        confidence=_confidence(score, action, stop_loss_triggered),
        suggested_quantity=suggested_quantity,
        suggested_price_range=_suggested_price_range(action, current_price_native),
        reason=_join_unique(reasons),
        risk=_join_unique(risks),
    )


def recommend_candidate(
    screener_row: dict[str, Any],
    total_portfolio_value_twd: float,
    settings: PortfolioSettings,
) -> dict[str, Any] | None:
    score = _score(screener_row)
    signal = _text(screener_row, "signal")
    screener_reason = _text(screener_row, "reason")
    market = _market(screener_row.get("market", ""))
    current_price_native = _number(screener_row.get("close"), default=math.nan)
    current_price_twd = convert_price_to_twd(current_price_native, market, settings.usd_twd)

    if score >= 85 and signal == "BUY":
        action = "BUY"
        reason = _join_unique([screener_reason, "no current position", "high score candidate"])
    elif score >= 65:
        action = "WATCH"
        reason = _join_unique([screener_reason, "no current position"])
    else:
        return None

    suggested_quantity, insufficient_cash = _suggested_quantity(
        action=action,
        market=market,
        shares=0.0,
        current_price_native=current_price_native,
        current_price_twd=current_price_twd,
        market_value_twd=0.0,
        total_portfolio_value_twd=total_portfolio_value_twd,
        settings=settings,
    )

    risks = _risk_reasons(screener_reason)
    risks.append("no current position")
    if insufficient_cash:
        risks.append("insufficient cash")

    return _recommendation_row(
        ticker=screener_row["ticker"],
        market=market,
        name=screener_row.get("name", ""),
        shares=0.0,
        avg_cost=0.0,
        current_price_native=current_price_native,
        current_price_twd=current_price_twd,
        market_value_native=0.0,
        market_value_twd=0.0,
        unrealized_pnl_native=0.0,
        unrealized_pnl_pct=math.nan,
        weight=0.0,
        score=score,
        signal=signal,
        action=action,
        confidence=_confidence(score, action, stop_loss_triggered=False),
        suggested_quantity=suggested_quantity,
        suggested_price_range=_suggested_price_range(action, current_price_native),
        reason=reason,
        risk=_join_unique(risks),
    )


def _portfolio_settings(settings: dict[str, Any]) -> PortfolioSettings:
    user_settings = settings.get("user", {}) if isinstance(settings, dict) else {}
    portfolio_settings = settings.get("portfolio", {}) if isinstance(settings, dict) else {}
    fx_settings = settings.get("fx", {}) if isinstance(settings, dict) else {}
    return PortfolioSettings(
        max_position_weight=float(user_settings.get("max_position_weight", 0.25)),
        stop_loss_pct=float(user_settings.get("stop_loss_pct", -0.10)),
        usd_twd=float(fx_settings.get("USD_TWD", 1.0)),
        cash_twd=float(portfolio_settings.get("cash_twd", 0.0)),
        cash_usd=float(portfolio_settings.get("cash_usd", 0.0)),
        tw_lot_size=max(1, int(portfolio_settings.get("default_tw_lot_size", 1))),
        us_lot_size=max(1, int(portfolio_settings.get("default_us_lot_size", 1))),
    )


def _total_portfolio_value_twd(portfolio_metrics: pd.DataFrame, settings: PortfolioSettings) -> float:
    return float(
        portfolio_metrics["market_value_twd"].sum()
        + settings.cash_twd
        + settings.cash_usd * settings.usd_twd
    )


def _holding_action(
    score: int,
    signal: str,
    unrealized_pnl_pct: float,
    weight: float,
    max_position_weight: float,
    stop_loss_triggered: bool,
) -> str:
    if stop_loss_triggered:
        return "SELL"
    if weight > max_position_weight:
        return "REDUCE"
    if score >= 80 and signal == "BUY" and _not_nan(unrealized_pnl_pct) and unrealized_pnl_pct > 0:
        if weight < max_position_weight:
            return "ADD"
    if score >= 60 and signal in {"BUY", "WATCH"}:
        return "HOLD"
    if score < 40 and _not_nan(unrealized_pnl_pct) and unrealized_pnl_pct < 0:
        return "SELL"
    if score < 50:
        return "REDUCE"
    return "HOLD"


def _suggested_quantity(
    action: str,
    market: str,
    shares: float,
    current_price_native: float,
    current_price_twd: float,
    market_value_twd: float,
    total_portfolio_value_twd: float,
    settings: PortfolioSettings,
) -> tuple[int | float, bool]:
    if action in {"BUY", "ADD"}:
        if total_portfolio_value_twd <= 0 or not _valid_price(current_price_native) or not _valid_price(current_price_twd):
            return 0, False
        cash_available, cash_price = _cash_limit(market, current_price_native, current_price_twd, settings)
        target_value_twd = total_portfolio_value_twd * settings.max_position_weight
        value_room_twd = max(0.0, target_value_twd - market_value_twd)
        quantity_by_weight = math.floor(value_room_twd / current_price_twd)
        quantity_by_cash = math.floor(cash_available / cash_price) if _valid_price(cash_price) else 0
        lot_size = _lot_size(market, settings)
        quantity = _floor_to_lot(min(quantity_by_weight, quantity_by_cash), lot_size)
        return quantity, quantity == 0 and quantity_by_cash < lot_size
    if action == "REDUCE":
        if shares <= 0:
            return 0, False
        return max(1, int(math.floor(shares * 0.25))), False
    if action == "SELL":
        return shares, False
    return 0, False


def _cash_limit(
    market: str,
    current_price_native: float,
    current_price_twd: float,
    settings: PortfolioSettings,
) -> tuple[float, float]:
    if _market(market) == "US":
        return settings.cash_usd, current_price_native
    return settings.cash_twd, current_price_twd


def _lot_size(market: str, settings: PortfolioSettings) -> int:
    if _market(market) == "US":
        return settings.us_lot_size
    return settings.tw_lot_size


def _floor_to_lot(quantity: int, lot_size: int) -> int:
    if quantity < lot_size:
        return 0
    return int(quantity // lot_size * lot_size)


def _suggested_price_range(action: str, current_price_native: float) -> str:
    if not _valid_price(current_price_native):
        return ""
    if action in {"BUY", "ADD"}:
        return f"{current_price_native * 0.98:.2f} - {current_price_native * 1.01:.2f}"
    if action in {"REDUCE", "SELL"}:
        return f"around {current_price_native:.2f}"
    return ""


def _confidence(score: int, action: str, stop_loss_triggered: bool) -> float:
    confidence = max(0.0, min(1.0, score / 100))
    if action == "SELL" and stop_loss_triggered:
        confidence = max(confidence, 0.8)
    return round(confidence, 4)


def _risk_reasons(reason: str) -> list[str]:
    lower_reason = reason.lower()
    risks = []
    if "overbought" in lower_reason:
        risks.append("overbought risk")
    if "high volatility" in lower_reason:
        risks.append("high volatility")
    if "large drawdown risk" in lower_reason:
        risks.append("large drawdown risk")
    return risks


def _recommendation_row(**values: Any) -> dict[str, Any]:
    return {column: values.get(column, "") for column in RECOMMENDATION_COLUMNS}


def _score(row: dict[str, Any] | None) -> int:
    if row is None:
        return 0
    value = _number(row.get("score"), default=0.0)
    return int(max(0, min(100, value)))


def _text(row: dict[str, Any] | None, key: str) -> str:
    if row is None:
        return ""
    value = row.get(key, "")
    if pd.isna(value):
        return ""
    return str(value)


def _value(row: dict[str, Any] | None, key: str) -> Any:
    if row is None:
        return math.nan
    return row.get(key, math.nan)


def _market(value: Any) -> str:
    return str(value).strip().upper()


def _first_number(*values: Any) -> float:
    for value in values:
        number = _number(value, default=math.nan)
        if _not_nan(number):
            return number
    return math.nan


def _number(value: Any, default: float) -> float:
    if pd.isna(value):
        return default
    return float(value)


def _not_nan(value: float) -> bool:
    return not math.isnan(value)


def _valid_price(value: float) -> bool:
    return _not_nan(value) and value > 0


def _join_unique(items: list[str]) -> str:
    result = []
    for item in items:
        if not item:
            continue
        if item not in result:
            result.append(item)
    return "; ".join(result)
