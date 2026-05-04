from datetime import datetime, timezone


class EarningsResearchAgent:
    def __init__(self, days_window: int = 21):
        self.days_window = days_window

    def summarize(self, ticker: str, stock, info: dict) -> str:
        today = datetime.now(timezone.utc).date()

        ts = (
            info.get("earningsTimestamp")
            or info.get("earningsTimestampStart")
            or info.get("earningsTimestampEnd")
        )

        next_earnings = None
        if isinstance(ts, (int, float)) and ts > 0:
            try:
                next_earnings = datetime.fromtimestamp(float(ts), tz=timezone.utc).date()
            except Exception:
                next_earnings = None

        if next_earnings is None:
            try:
                cal = getattr(stock, "calendar", None)
                if cal is not None and not cal.empty:
                    try:
                        v = cal.iloc[0, 0]
                        if hasattr(v, "date"):
                            next_earnings = v.date()
                    except Exception:
                        pass
            except Exception:
                pass

        pieces = []

        if next_earnings is not None:
            d = (next_earnings - today).days
            pieces.append(f"下一次财报 {next_earnings.isoformat()} (D{d:+d})")
            in_window = abs(d) <= self.days_window
        else:
            pieces.append("下一次财报日期未知")
            in_window = False

        if in_window:
            rev_g = info.get("revenueQuarterlyGrowth")
            earn_g = info.get("earningsQuarterlyGrowth")
            margin = info.get("profitMargins")
            eps_t = info.get("trailingEps")
            eps_f = info.get("forwardEps")
            pieces.append(self._fmt_kv("营收QoQ", rev_g))
            pieces.append(self._fmt_kv("盈利QoQ", earn_g))
            pieces.append(self._fmt_kv("利润率", margin))
            pieces.append(self._fmt_kv("EPS(TTM)", eps_t))
            pieces.append(self._fmt_kv("EPS(Fwd)", eps_f))

        pieces = [p for p in pieces if p]
        return f"- {ticker} 财报/指引: " + " | ".join(pieces)

    def _fmt_kv(self, k: str, v) -> str:
        if v is None:
            return ""
        try:
            if isinstance(v, (int, float)):
                if abs(v) < 3:
                    return f"{k} {v*100:.1f}%"
                return f"{k} {v:.2f}"
            return f"{k} {v}"
        except Exception:
            return ""

