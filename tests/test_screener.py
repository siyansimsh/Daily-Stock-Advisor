import pandas as pd

from src.screener import score_latest


SETTINGS = {"screener": {"min_volume_ratio": 1.0}}


def make_latest(**overrides):
    values = {
        "Close": 100.0,
        "MA20": 90.0,
        "MA60": 80.0,
        "MA120": 70.0,
        "RSI14": 65.0,
        "MACD": 2.0,
        "MACD_signal": 1.0,
        "Volume_Ratio": 1.5,
        "Return_20D": 0.10,
        "Return_60D": 0.20,
        "Volatility_20D": 0.20,
        "Max_Drawdown": -0.05,
    }
    values.update(overrides)
    return pd.Series(values)


def test_score_is_clamped_to_0_to_100():
    strong_score, _, _ = score_latest(make_latest(), SETTINGS)
    weak_score, _, _ = score_latest(
        make_latest(
            Close=80.0,
            MA20=100.0,
            MA60=110.0,
            MA120=120.0,
            RSI14=85.0,
            MACD=-1.0,
            MACD_signal=0.0,
            Volume_Ratio=0.2,
            Return_20D=-0.10,
            Return_60D=-0.20,
            Volatility_20D=0.80,
            Max_Drawdown=-0.50,
        ),
        SETTINGS,
    )

    assert 0 <= strong_score <= 100
    assert 0 <= weak_score <= 100
    assert strong_score == 100
    assert weak_score == 0


def test_rsi_above_75_cannot_be_buy():
    score, signal, reason = score_latest(make_latest(RSI14=80.0), SETTINGS)

    assert score >= 70
    assert signal != "BUY"
    assert signal == "WATCH"
    assert "RSI overbought" in reason
    assert "trend is strong but RSI is overbought; avoid chasing high" in reason


def test_score_at_least_80_with_rsi_at_or_below_70_can_be_buy():
    score, signal, reason = score_latest(make_latest(RSI14=68.0), SETTINGS)

    assert score >= 80
    assert signal == "BUY"
    assert "RSI in healthy range" in reason


def test_large_max_drawdown_adds_risk_reason():
    _, _, reason = score_latest(make_latest(Max_Drawdown=-0.35), SETTINGS)

    assert "large drawdown risk" in reason
