import logging
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.db import transaction
from django.test import TestCase, override_settings

from internal_notifications import business, logging_handler, transport


def fake_order():
    item = SimpleNamespace(
        cigar=SimpleNamespace(name="<经典款>", english_name="Classic"),
        cigar_id=7,
        sale_unit="box",
        sale_quantity=2,
        box_size=10,
        quantity=20,
        fulfillment_type="in_stock",
    )
    order = SimpleNamespace(
        order_number="SO-000123",
        customer_name="张 & 李",
        customer_id=None,
        amount_due_cny="1234.50",
        payment_status="unpaid",
    )
    operator = SimpleNamespace(get_full_name=lambda: "内部 <操作员>", __str__=lambda self: "operator")
    return order, operator, [item]


@override_settings(
    TELEGRAM_NOTIFICATIONS_ENABLED=True,
    TELEGRAM_BUSINESS_CHAT_ID="-100123",
    INTERNAL_SITE_URL="https://example.test",
)
class BusinessNotificationTest(TestCase):
    def test_order_message_is_scheduled_after_commit_and_escapes_values(self):
        order, operator, items = fake_order()
        with patch("internal_notifications.business.dispatch") as dispatch_mock:
            with self.captureOnCommitCallbacks(execute=True):
                business.schedule_order_notification(
                    "waiting_shipment", order, operator, items=items,
                )
        dispatch_mock.assert_called_once()
        job = dispatch_mock.call_args.args[0]
        with patch("internal_notifications.business.send_text") as send_mock:
            job()
        chat_id, message = send_mock.call_args.args
        self.assertEqual(chat_id, "-100123")
        self.assertIn("待出库提醒", message)
        self.assertIn("张 &amp; 李", message)
        self.assertIn("&lt;经典款&gt;", message)
        self.assertIn("2盒（10支/盒）", message)
        self.assertIn("¥1,234.50", message)
        self.assertIn("https://example.test/sales", message)

    def test_rolled_back_transaction_does_not_dispatch(self):
        order, operator, items = fake_order()
        with patch("internal_notifications.business.dispatch") as dispatch_mock:
            with self.captureOnCommitCallbacks(execute=True):
                try:
                    with transaction.atomic():
                        business.schedule_order_notification(
                            "waiting_shipment", order, operator, items=items,
                        )
                        raise RuntimeError("rollback")
                except RuntimeError:
                    pass
        dispatch_mock.assert_not_called()

    def test_payment_submission_sends_summary_then_every_photo(self):
        order, _operator, _items = fake_order()
        submission = SimpleNamespace(amount_cny="1234.50")
        with patch("internal_notifications.business.dispatch") as dispatch_mock:
            with self.captureOnCommitCallbacks(execute=True):
                business.schedule_payment_submission_notification(
                    submission, order, ["/private/proof-1.png", "/private/proof-2.png"],
                )
        job = dispatch_mock.call_args.args[0]
        with (
            patch("internal_notifications.business.send_text") as text_mock,
            patch("internal_notifications.business.send_evidence_image") as photo_mock,
        ):
            job()
        text_mock.assert_called_once()
        self.assertIn("待核实", text_mock.call_args.args[1])
        self.assertEqual(
            [call.args for call in photo_mock.call_args_list],
            [("-100123", "/private/proof-1.png"), ("-100123", "/private/proof-2.png")],
        )

    def test_long_order_message_uses_valid_compact_summary(self):
        order, operator, items = fake_order()
        order.customer_name = "&" * 200
        items = [
            SimpleNamespace(**{**vars(items[0]), "cigar": SimpleNamespace(name="&" * 200, english_name="")})
            for _ in range(20)
        ]
        snapshot = business._order_snapshot(order, operator, items=items)
        message = business._render_order("waiting_shipment", snapshot)
        self.assertLessEqual(len(message), 4000)
        self.assertIn("商品明细较长，请在网站查看", message)
        self.assertTrue(message.endswith("打开销售页面</a>"))


@override_settings(
    TELEGRAM_NOTIFICATIONS_ENABLED=True,
    TELEGRAM_BOT_TOKEN="test-token",
    TELEGRAM_NOTIFICATION_MAX_ATTEMPTS=3,
    TELEGRAM_NOTIFICATION_CONNECT_TIMEOUT=1,
    TELEGRAM_NOTIFICATION_READ_TIMEOUT=1,
)
class TelegramTransportTest(TestCase):
    @patch("internal_notifications.transport.time.sleep")
    @patch("internal_notifications.transport.requests.post")
    def test_send_text_retries_and_does_not_log_token(self, post_mock, _sleep_mock):
        success = Mock(status_code=200, content=b"{}", ok=True)
        success.json.return_value = {"ok": True}
        post_mock.side_effect = [OSError("offline"), success]
        self.assertTrue(transport.send_text("123", "hello"))
        self.assertEqual(post_mock.call_count, 2)

    @patch("internal_notifications.transport.time.sleep")
    @patch("internal_notifications.transport.requests.post", side_effect=OSError("offline"))
    def test_final_failure_is_logged_without_secret_url(self, post_mock, _sleep_mock):
        with self.assertLogs("internal_notifications.transport", level="ERROR") as captured:
            self.assertFalse(transport.send_text("123", "hello"))
        self.assertEqual(post_mock.call_count, 3)
        output = " ".join(captured.output)
        self.assertNotIn("test-token", output)
        self.assertIn("after 3 attempts", output)

    @patch("internal_notifications.transport._request", return_value=True)
    def test_webp_evidence_is_sent_as_document(self, request_mock):
        self.assertTrue(transport.send_evidence_image("123", "/private/proof.webp"))
        request_mock.assert_called_once_with(
            "sendDocument", chat_id="123", file_path="/private/proof.webp",
        )


class TelegramMissingConfigurationTest(TestCase):
    @override_settings(TELEGRAM_NOTIFICATIONS_ENABLED=True, TELEGRAM_BOT_TOKEN="")
    def test_missing_configuration_is_logged_only_once(self):
        transport._configuration_warnings.clear()
        with patch.object(transport.logger, "warning") as warning_mock:
            self.assertFalse(transport.dispatch(lambda: None, chat_id="123"))
            self.assertFalse(transport.dispatch(lambda: None, chat_id="123"))
        warning_mock.assert_called_once()


@override_settings(
    TELEGRAM_NOTIFICATIONS_ENABLED=True,
    TELEGRAM_ERROR_CHAT_ID="987",
    TELEGRAM_ERROR_COOLDOWN_SECONDS=300,
)
class TelegramErrorHandlerTest(TestCase):
    def setUp(self):
        logging_handler._seen.clear()

    def _record(self):
        try:
            raise ValueError("bad")
        except ValueError:
            import sys
            exc_info = sys.exc_info()
        record = logging.LogRecord(
            name="django.request", level=logging.ERROR, pathname=__file__,
            lineno=100, msg="request token=super-secret failed", args=(),
            exc_info=exc_info,
        )
        record.request = SimpleNamespace(method="POST", path="/api/orders/7/")
        return record

    def test_error_summary_is_redacted_and_rate_limited(self):
        handler = logging_handler.TelegramErrorHandler()
        with (
            patch("internal_notifications.logging_handler.time.monotonic", side_effect=[100.0, 101.0]),
            patch("internal_notifications.logging_handler.dispatch") as dispatch_mock,
        ):
            handler.emit(self._record())
            handler.emit(self._record())
        dispatch_mock.assert_called_once()
        job = dispatch_mock.call_args.args[0]
        with patch("internal_notifications.logging_handler.send_text") as send_mock:
            job()
        chat_id, message = send_mock.call_args.args
        self.assertEqual(chat_id, "987")
        self.assertIn("ValueError", message)
        self.assertIn("POST /api/orders/7/", message)
        self.assertIn("token=[redacted]", message)
        self.assertNotIn("super-secret", message)

    def test_notification_transport_errors_do_not_recurse(self):
        record = logging.LogRecord(
            name="internal_notifications.transport", level=logging.ERROR,
            pathname=__file__, lineno=1, msg="send failed", args=(), exc_info=None,
        )
        with patch("internal_notifications.logging_handler.dispatch") as dispatch_mock:
            logging_handler.TelegramErrorHandler().emit(record)
        dispatch_mock.assert_not_called()

    def test_django_security_scanner_noise_is_not_sent(self):
        record = logging.LogRecord(
            name="django.security.DisallowedHost", level=logging.ERROR,
            pathname=__file__, lineno=1, msg="Invalid HTTP_HOST header",
            args=(), exc_info=None,
        )
        with patch("internal_notifications.logging_handler.dispatch") as dispatch_mock:
            logging_handler.TelegramErrorHandler().emit(record)
        dispatch_mock.assert_not_called()


@override_settings(TELEGRAM_NOTIFICATIONS_ENABLED=False)
class TelegramDisabledTest(TestCase):
    def test_error_handler_and_transport_do_not_dispatch_in_tests(self):
        record = logging.LogRecord(
            name="django.request", level=logging.ERROR, pathname=__file__,
            lineno=1, msg="expected test error", args=(), exc_info=None,
        )
        with patch("internal_notifications.logging_handler.dispatch") as dispatch_mock:
            logging_handler.TelegramErrorHandler().emit(record)
        dispatch_mock.assert_not_called()

        with patch("internal_notifications.transport.requests.post") as post_mock:
            self.assertFalse(transport.send_text("real-chat-id", "must stay local"))
        post_mock.assert_not_called()
