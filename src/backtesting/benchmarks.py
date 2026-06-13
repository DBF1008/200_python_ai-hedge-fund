from __future__ import annotations

from typing import Sequence

import pandas as pd

from src.tools.api import get_price_data


class BenchmarkCalculator:
    def get_return_pct(self, ticker: str, start_date: str, end_date: str, api_key: str | None = None) -> float | None:
        """Compute simple buy-and-hold return % for ticker from start_date to end_date.

        Return is (last_close / first_close - 1) * 100, or None if unavailable.
        """
        try:
            df = get_price_data(ticker, start_date, end_date, api_key=api_key)
            if df.empty:
                return None
            first_close = df.iloc[0]["close"]
            last_close = df.iloc[-1]["close"]
            if first_close is None or pd.isna(first_close):
                return None
            if last_close is None or pd.isna(last_close):
                # Try last valid close
                last_valid = df["close"].dropna()
                if last_valid.empty:
                    return None
                last_close = float(last_valid.iloc[-1])
            return (float(last_close) / float(first_close) - 1.0) * 100.0
        except Exception:
            return None

    def get_value_series(
        self,
        ticker: str,
        start_date: str,
        end_date: str,
        base_value: float,
        dates: Sequence,
        api_key: str | None = None,
    ) -> dict[str, float | None]:
        """Buy-and-hold value of ``base_value`` invested in ``ticker``, sampled at each date.

        The series is normalized so that the first valid close maps to ``base_value``
        (i.e. value[d] = base_value * close.asof(d) / first_close). For each requested
        date the most recent close at or before that date is used (forward fill). Dates
        without an available close (e.g. before the first quote) map to ``None``.

        Returns a mapping of ``"YYYY-MM-DD" -> value | None`` for every date in ``dates``.
        """
        result: dict[str, float | None] = {}
        try:
            df = get_price_data(ticker, start_date, end_date, api_key=api_key)
        except Exception:
            df = pd.DataFrame()

        close = df["close"].dropna() if (not df.empty and "close" in df.columns) else pd.Series(dtype="float64")
        first_close = float(close.iloc[0]) if not close.empty else None

        for d in dates:
            ts = pd.Timestamp(d)
            key = ts.strftime("%Y-%m-%d")
            value: float | None = None
            if first_close and first_close != 0 and not close.empty:
                sampled = close.asof(ts)
                if sampled is not None and not pd.isna(sampled):
                    value = base_value * (float(sampled) / first_close)
            result[key] = value
        return result


