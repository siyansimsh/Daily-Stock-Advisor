import math

import pandas as pd

from src.indicators import add_indicators, max_drawdown, moving_average, period_return, volume_ratio


def test_moving_average_uses_full_window():
    series = pd.Series([1, 2, 3, 4, 5])

    result = moving_average(series, 3)

    assert math.isnan(result.iloc[1])
    assert result.iloc[2] == 2
    assert result.iloc[4] == 4


def test_volume_ratio_and_period_return():
    volume = pd.Series([10, 20, 30, 40, 50])
    close = pd.Series([100, 110, 120, 130, 140])

    ratio = volume_ratio(volume, 3)
    returns = period_return(close, 2)

    assert math.isnan(ratio.iloc[1])
    assert ratio.iloc[4] == 50 / 40
    assert returns.iloc[4] == 140 / 120 - 1


def test_max_drawdown_window_returns_rolling_worst_drawdown():
    close = pd.Series([100, 120, 90, 96, 80])

    result = max_drawdown(close, window=3)

    assert isinstance(result, pd.Series)
    assert result.iloc[2] == 90 / 120 - 1
    assert result.iloc[4] == 80 / 120 - 1


def test_add_indicators_outputs_phase_2_columns():
    rows = 130
    data = pd.DataFrame(
        {
            "Date": pd.date_range("2024-01-01", periods=rows),
            "Open": range(100, 100 + rows),
            "High": range(101, 101 + rows),
            "Low": range(99, 99 + rows),
            "Close": range(100, 100 + rows),
            "Adj Close": range(100, 100 + rows),
            "Volume": range(1000, 1000 + rows),
        }
    )

    result = add_indicators(data)
    latest = result.iloc[-1]

    expected_columns = {
        "MA20",
        "MA60",
        "MA120",
        "RSI14",
        "MACD",
        "MACD_signal",
        "Volume_MA20",
        "Volume_Ratio",
        "Return_20D",
        "Return_60D",
        "Volatility_20D",
        "Max_Drawdown",
    }
    assert expected_columns.issubset(result.columns)
    assert latest["MA20"] == sum(range(210, 230)) / 20
    assert latest["Return_20D"] == 229 / 209 - 1
    assert not pd.isna(latest["RSI14"])
    assert not pd.isna(latest["MACD"])
    assert not pd.isna(latest["Volume_Ratio"])
    assert not pd.isna(latest["Volatility_20D"])
