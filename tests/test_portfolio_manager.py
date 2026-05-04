import unittest
from unittest.mock import patch

from config import TECH_UNIVERSE
from execution.portfolio import PortfolioManager


def _positions(default: int = 0, **overrides):
    out = {ticker: default for ticker in TECH_UNIVERSE}
    out.update(overrides)
    return out


def _prices(default: float = 100.0, **overrides):
    out = {ticker: default for ticker in TECH_UNIVERSE}
    out.update(overrides)
    return out


class PortfolioManagerTests(unittest.TestCase):
    def test_rebalance_applies_single_name_limit_and_cash_buffer(self):
        with patch("execution.portfolio.MAX_DAILY_TURNOVER", 1.0):
            orders = PortfolioManager.rebalance(
                cash=1000.0,
                positions=_positions(),
                target_weights={ticker: 0.2 for ticker in TECH_UNIVERSE},
                current_prices=_prices(default=100.0),
            )

        self.assertEqual(len(orders), len(TECH_UNIVERSE))
        self.assertTrue(all(order["action"] == "BUY" for order in orders))
        self.assertLessEqual(sum(order["amount"] for order in orders), 950.0)
        self.assertTrue(all(order["shares"] == 1 for order in orders))

    def test_rebalance_skips_small_changes_inside_deadband(self):
        orders = PortfolioManager.rebalance(
            cash=800.0,
            positions=_positions(AAPL=2),
            target_weights={"AAPL": 0.23},
            current_prices=_prices(default=100.0),
        )

        self.assertEqual(orders, [])

    def test_rebalance_can_liquidate_dust_inside_deadband(self):
        with patch("execution.portfolio.AUTO_LIQUIDATE_DUST", True), patch("execution.portfolio.DUST_MAX_WEIGHT", 0.05):
            orders = PortfolioManager.rebalance(
                cash=970.0,
                positions=_positions(AAPL=1),
                target_weights={"AAPL": 0.0},
                current_prices=_prices(default=30.0),
            )

        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0]["ticker"], "AAPL")
        self.assertEqual(orders[0]["action"], "SELL")
        self.assertEqual(orders[0]["shares"], 1)

    def test_rebalance_scales_down_orders_when_turnover_too_high(self):
        orders = PortfolioManager.rebalance(
            cash=1000.0,
            positions=_positions(),
            target_weights={"AAPL": 0.2, "MSFT": 0.2, "NVDA": 0.2, "GOOGL": 0.2},
            current_prices=_prices(default=10.0),
        )

        self.assertEqual(len(orders), 4)
        self.assertTrue(all(order["shares"] == 7 for order in orders))
        self.assertLessEqual(sum(order["amount"] for order in orders), 300.0)


if __name__ == "__main__":
    unittest.main()
