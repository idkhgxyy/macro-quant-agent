"""Unit tests for IBKRBroker: connection, get_account_summary, submit_orders, timeout, and edge cases."""
from unittest import TestCase
from unittest.mock import patch, MagicMock
from execution.broker import IBKRBroker


def _make_account_value(tag: str, currency: str, value: str):
    """Helper to create a mock accountValues entry."""
    m = MagicMock()
    m.tag = tag
    m.currency = currency
    m.value = value
    return m


def _make_portfolio_item(symbol: str, position: int):
    """Helper to create a mock portfolio entry."""
    contract = MagicMock()
    contract.symbol = symbol
    item = MagicMock()
    item.contract = contract
    item.position = position
    return item


def _make_trade(status: str = "Filled", filled: int = 200, avg_fill_price: float = 100.0, order_id: int = 1):
    """Helper to create a mock trade with orderStatus."""
    order_status = MagicMock()
    order_status.status = status
    order_status.filled = filled
    order_status.avgFillPrice = avg_fill_price
    order = MagicMock()
    order.orderId = order_id
    trade = MagicMock()
    trade.orderStatus = order_status
    trade.order = order
    trade.fills = []
    return trade


class TestIBKRBrokerConnect(TestCase):
    def setUp(self):
        self.ib_patcher = patch("execution.broker.IB")
        self.mock_ib_cls = self.ib_patcher.start()
        self.mock_ib_instance = MagicMock()
        self.mock_ib_cls.return_value = self.mock_ib_instance

    def tearDown(self):
        self.ib_patcher.stop()

    def test_init_creates_ib_instance(self):
        broker = IBKRBroker(host="127.0.0.1", port=7497, client_id=2)
        self.assertEqual(broker.host, "127.0.0.1")
        self.assertEqual(broker.port, 7497)
        self.assertEqual(broker.client_id, 2)
        self.mock_ib_cls.assert_called_once()

    def test_init_uses_defaults(self):
        broker = IBKRBroker()
        self.assertEqual(broker.host, "127.0.0.1")
        self.assertEqual(broker.port, 7497)
        self.assertEqual(broker.client_id, 1)


class TestIBKRBrokerGetAccountSummary(TestCase):
    def setUp(self):
        self.ib_patcher = patch("execution.broker.IB")
        self.mock_ib_cls = self.ib_patcher.start()
        self.mock_ib = MagicMock()
        self.mock_ib_cls.return_value = self.mock_ib
        self.broker = IBKRBroker()
        self.broker._connect = MagicMock()
        self.broker._disconnect = MagicMock()

    def tearDown(self):
        self.ib_patcher.stop()

    def test_get_account_summary_success(self):
        self.mock_ib.accountValues.return_value = [
            _make_account_value("TotalCashValue", "USD", "50000.00"),
        ]
        self.mock_ib.portfolio.return_value = [
            _make_portfolio_item("AAPL", 100),
        ]

        cash, positions = self.broker.get_account_summary()

        self.assertAlmostEqual(cash, 50000.00)
        self.assertEqual(positions.get("AAPL"), 100)
        self.assertEqual(positions.get("MSFT"), 0)
        self.broker._connect.assert_called_once()
        self.broker._disconnect.assert_called_once()

    def test_get_account_summary_zero_cash_falls_back(self):
        self.mock_ib.accountValues.return_value = [
            _make_account_value("TotalCashValue", "EUR", "10000.00"),
        ]
        self.mock_ib.portfolio.return_value = []

        cash, positions = self.broker.get_account_summary()

        self.assertAlmostEqual(cash, 0.0)
        self.broker._disconnect.assert_called_once()

    def test_get_account_summary_raises_on_api_error(self):
        self.mock_ib.accountValues.side_effect = RuntimeError("connection lost")

        with self.assertRaises(RuntimeError):
            self.broker.get_account_summary()

        self.broker._disconnect.assert_called_once()

    def test_get_account_summary_ignores_unknown_tickers(self):
        self.mock_ib.accountValues.return_value = [
            _make_account_value("TotalCashValue", "USD", "100000.00"),
        ]
        self.mock_ib.portfolio.return_value = [
            _make_portfolio_item("AAPL", 50),
            _make_portfolio_item("ZZZZ", 999),
        ]

        _, positions = self.broker.get_account_summary()

        self.assertEqual(positions.get("AAPL"), 50)
        self.assertNotIn("ZZZZ", positions)


class TestIBKRBrokerConnectReal(TestCase):
    def setUp(self):
        self.ib_patcher = patch("execution.broker.IB")
        self.mock_ib_cls = self.ib_patcher.start()
        self.mock_ib = MagicMock()
        self.mock_ib_cls.return_value = self.mock_ib
        self.mock_ib.isConnected.return_value = False
        self.broker = IBKRBroker()

    def tearDown(self):
        self.ib_patcher.stop()

    def test_connect_when_not_connected_calls_ib_connect(self):
        self.broker._connect()
        self.mock_ib.connect.assert_called_once_with(
            "127.0.0.1", 7497, clientId=1
        )

    def test_connect_when_already_connected_skips(self):
        self.mock_ib.isConnected.return_value = True
        self.broker._connect()
        self.mock_ib.connect.assert_not_called()

    def test_connect_raises_on_failure(self):
        self.mock_ib.connect.side_effect = RuntimeError("TWS not running")
        with self.assertRaises(RuntimeError):
            self.broker._connect()

    def test_disconnect_when_connected_calls_ib_disconnect(self):
        self.mock_ib.isConnected.return_value = True
        self.broker._disconnect()
        self.mock_ib.disconnect.assert_called_once()

    def test_disconnect_when_not_connected_skips(self):
        self.mock_ib.isConnected.return_value = False
        self.broker._disconnect()
        self.mock_ib.disconnect.assert_not_called()


class TestIBKRBrokerSubmitOrders(TestCase):
    def setUp(self):
        self.ib_patcher = patch("execution.broker.IB")
        self.mock_ib_cls = self.ib_patcher.start()
        self.mock_ib = MagicMock()
        self.mock_ib_cls.return_value = self.mock_ib
        self.broker = IBKRBroker()
        self.broker._connect = MagicMock()
        self.broker._disconnect = MagicMock()
        self.orders = [
            {"ticker": "AAPL", "action": "BUY", "shares": 200, "price": 100.0},
        ]

    def tearDown(self):
        self.ib_patcher.stop()

    def test_submit_orders_empty_list(self):
        result = self.broker.submit_orders([])
        self.assertEqual(result, [])
        self.broker._connect.assert_not_called()
        self.broker._disconnect.assert_not_called()

    def test_submit_orders_skips_zero_shares(self):
        orders = [{"ticker": "AAPL", "action": "BUY", "shares": 0, "price": 100.0}]
        result = self.broker.submit_orders(orders)
        self.assertEqual(result, [])
        self.broker._connect.assert_called_once()
        self.broker._disconnect.assert_called_once()

    def test_submit_orders_all_filled(self):
        trade = _make_trade(status="Filled", filled=200, avg_fill_price=100.0)
        self.mock_ib.placeOrder.return_value = trade

        result = self.broker.submit_orders(self.orders)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["ticker"], "AAPL")
        self.assertEqual(result[0]["action"], "BUY")
        self.assertEqual(result[0]["filled"], 200)
        self.assertEqual(result[0]["status"], "Filled")
        self.assertEqual(result[0]["order_id"], 1)
        self.broker._connect.assert_called_once()
        self.broker._disconnect.assert_called_once()
        self.mock_ib.qualifyContracts.assert_called_once()
        self.mock_ib.placeOrder.assert_called_once()

    def test_submit_orders_cancelled_before_fill(self):
        trade = _make_trade(status="Cancelled", filled=0)
        self.mock_ib.placeOrder.return_value = trade

        result = self.broker.submit_orders(self.orders)

        self.assertEqual(result[0]["status"], "Cancelled")
        self.assertEqual(result[0]["filled"], 0)
        self.assertEqual(result[0]["status_detail"], "cancelled_before_fill")

    def test_submit_orders_partial_then_cancelled(self):
        trade = _make_trade(status="Cancelled", filled=100, avg_fill_price=100.0)
        self.mock_ib.placeOrder.return_value = trade

        result = self.broker.submit_orders(self.orders)

        self.assertEqual(result[0]["status"], "Cancelled")
        self.assertEqual(result[0]["filled"], 100)
        self.assertEqual(result[0]["status_detail"], "partial_then_cancelled")

    def test_submit_orders_inactive_rejected(self):
        trade = _make_trade(status="Inactive", filled=0)
        self.mock_ib.placeOrder.return_value = trade

        result = self.broker.submit_orders(self.orders)

        self.assertEqual(result[0]["status"], "Inactive")
        self.assertEqual(result[0]["status_detail"], "inactive_rejected")

    def test_submit_orders_api_error_raises(self):
        self.mock_ib.placeOrder.side_effect = RuntimeError("placeOrder failed")

        with self.assertRaises(RuntimeError):
            self.broker.submit_orders(self.orders)

        self.broker._disconnect.assert_called_once()

    def test_submit_orders_timeout_cancels_orders(self):
        trade = _make_trade(status="Submitted", filled=0)
        self.mock_ib.placeOrder.return_value = trade
        self.mock_ib.sleep.side_effect = None

        with patch("execution.broker.time") as mock_time, patch("execution.broker.ALLOW_OUTSIDE_RTH", False), \
             patch.dict("os.environ", {"IBKR_ORDER_TIMEOUT_S": "10"}):
            # perf_counter: submitted_mono, then elapsed_sec in finalization
            mock_time.perf_counter.return_value = 100.0
            # time.time: start=100, then loop iterations until timeout
            call_count = [0]
            def time_side_effect():
                call_count[0] += 1
                if call_count[0] == 1:
                    return 100.0  # start
                return 111.0  # > 100 + 10, triggers timeout
            mock_time.time.side_effect = time_side_effect
            result = self.broker.submit_orders(self.orders)

        self.assertEqual(result[0]["timeout_cancel_requested"], True)
        self.mock_ib.cancelOrder.assert_called_once()

    def test_submit_orders_commission_extracted(self):
        trade = _make_trade(status="Filled", filled=200, avg_fill_price=100.0)
        fill = MagicMock()
        commission_report = MagicMock()
        commission_report.commission = 1.50
        fill.commissionReport = commission_report
        trade.fills = [fill]
        self.mock_ib.placeOrder.return_value = trade

        result = self.broker.submit_orders(self.orders)

        self.assertAlmostEqual(result[0]["commission"], 1.50)


class TestIBKRBrokerStatusDetail(TestCase):
    def setUp(self):
        self.broker = IBKRBroker()

    def test_filled_returns_filled_complete(self):
        result = self.broker._status_detail("Filled", 200, 200, timeout_cancel_requested=False)
        self.assertEqual(result, "filled_complete")

    def test_cancelled_before_fill(self):
        result = self.broker._status_detail("Cancelled", 0, 200, timeout_cancel_requested=False)
        self.assertEqual(result, "cancelled_before_fill")

    def test_timeout_cancelled(self):
        result = self.broker._status_detail("Cancelled", 0, 200, timeout_cancel_requested=True)
        self.assertEqual(result, "timeout_cancelled")

    def test_partial_then_cancelled(self):
        result = self.broker._status_detail("Cancelled", 50, 200, timeout_cancel_requested=False)
        self.assertEqual(result, "partial_then_cancelled")

    def test_inactive_rejected(self):
        result = self.broker._status_detail("Inactive", 0, 200, timeout_cancel_requested=False)
        self.assertEqual(result, "inactive_rejected")

    def test_partial_open(self):
        result = self.broker._status_detail("Submitted", 50, 200, timeout_cancel_requested=False)
        self.assertEqual(result, "partial_open")

    def test_submitted_no_fill(self):
        result = self.broker._status_detail("Submitted", 0, 200, timeout_cancel_requested=False)
        self.assertEqual(result, "submitted_pending_rth")

    def test_unknown_status_falls_to_submitted_no_fill(self):
        result = self.broker._status_detail("MagicStatus", 0, 200, timeout_cancel_requested=False)
        self.assertEqual(result, "submitted_no_fill")
