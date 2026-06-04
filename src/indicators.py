"""Technical indicator helpers used by screener and recommender phases."""

from __future__ import annotations

import pandas as pd


TRADING_DAYS_PER_YEAR = 252


def moving_average(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window=window, min_periods=window).mean()


def rsi(close: pd.Series, window: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / window, min_periods=window, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / window, min_periods=window, adjust=False).mean()
    rs = avg_gain / avg_loss.mask(avg_loss == 0)
    result = 100 - (100 / (1 + rs))
    result = result.mask((avg_loss == 0) & (avg_gain > 0), 100)
    result = result.mask((avg_loss == 0) & (avg_gain == 0), 50)
    return result


def macd(
    close: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> pd.DataFrame:
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return pd.DataFrame(
        {
            "MACD": macd_line,
            "MACD_signal": signal_line,
            "MACD_hist": histogram,
        }
    )


def volume_average(volume: pd.Series, window: int = 20) -> pd.Series:
    return volume.rolling(window=window, min_periods=window).mean()


def volume_ratio(volume: pd.Series, window: int = 20) -> pd.Series:
    average = volume_average(volume, window)
    return volume / average.mask(average == 0)


def period_return(close: pd.Series, window: int) -> pd.Series:
    return close.pct_change(window)


def annualized_volatility(
    close: pd.Series,
    window: int = 20,
    periods_per_year: int = TRADING_DAYS_PER_YEAR,
) -> pd.Series:
    returns = close.pct_change()
    return returns.rolling(window=window, min_periods=window).std() * (periods_per_year**0.5)


def drawdown(close: pd.Series) -> pd.Series:
    running_max = close.cummax()
    return close / running_max - 1


def max_drawdown(close: pd.Series, window: int | None = None) -> pd.Series | float:
    dd = drawdown(close)
    if window is None:
        return float(dd.min())
    return dd.rolling(window=window, min_periods=1).min()


def add_indicators(data: pd.DataFrame) -> pd.DataFrame:
    """Append Phase 2 rule-based screener indicators to an OHLCV DataFrame."""

    result = data.copy()
    close = pd.to_numeric(result["Close"], errors="coerce")
    volume = pd.to_numeric(result["Volume"], errors="coerce")

    result["MA20"] = moving_average(close, 20)
    result["MA60"] = moving_average(close, 60)
    result["MA120"] = moving_average(close, 120)
    result["RSI14"] = rsi(close, 14)
    result = pd.concat([result, macd(close)], axis=1)
    result["Volume_MA20"] = volume_average(volume, 20)
    result["Volume_Ratio"] = volume_ratio(volume, 20)
    result["Return_20D"] = period_return(close, 20)
    result["Return_60D"] = period_return(close, 60)
    result["Volatility_20D"] = annualized_volatility(close, 20)
    result["Max_Drawdown"] = max_drawdown(close, 20)
    return result
