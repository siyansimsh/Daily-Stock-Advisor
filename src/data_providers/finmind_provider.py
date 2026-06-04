"""Placeholder for a future FinMind data provider."""


class FinMindProvider:
    """Future Taiwan market data provider.

    Phase 1 intentionally uses yfinance only. This class exists so the project
    structure is ready for a later FinMind integration without changing imports.
    """

    def fetch_ohlcv(self, *args, **kwargs):
        raise NotImplementedError("FinMind integration is not implemented in Phase 1.")
