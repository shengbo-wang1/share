import importlib.util
import sys
import unittest
from http.client import RemoteDisconnected
from pathlib import Path
from unittest import mock


try:
    import requests
except ImportError:  # pragma: no cover - local env dependent
    requests = None


def load_bootstrap_module():
    module_path = Path(__file__).resolve().parents[1] / "akshare_bootstrap.py"
    spec = importlib.util.spec_from_file_location("akshare_bootstrap_test_module", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@unittest.skipUnless(requests is not None, "requests is required for HTTP debug tests")
class AkshareBootstrapHttpDebugTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bootstrap = load_bootstrap_module()

    def make_response(self, url: str, status_code: int, body: str, content_type: str = "application/json"):
        response = requests.Response()
        response.status_code = status_code
        response.reason = "TEST"
        response.url = url
        response.headers["Content-Type"] = content_type
        response._content = body.encode("utf-8")
        prepared = requests.PreparedRequest()
        prepared.prepare(method="GET", url=url)
        response.request = prepared
        return response

    def test_remote_disconnected_records_response_missing(self):
        debug_logs = []
        settings = self.bootstrap.HttpDebugSettings(enabled=False, body_max_chars=80)

        def failing_request(session, method, url, **kwargs):
            raise requests.exceptions.ConnectionError(
                "Connection aborted.",
                RemoteDisconnected("Remote end closed connection without response"),
            )

        with mock.patch("requests.sessions.Session.request", new=failing_request):
            with self.assertRaises(requests.exceptions.ConnectionError):
                self.bootstrap.execute_with_http_debug(
                    lambda: requests.get("https://example.com/quote"),
                    request_batch_id="batch-1",
                    dataset="stock_zh_a_hist_raw",
                    symbol="600519",
                    attempt_no=1,
                    max_attempts=1,
                    debug_settings=settings,
                    fetch_debug_logs=debug_logs,
                )

        self.assertEqual(len(debug_logs), 1)
        event = debug_logs[0]
        self.assertTrue(event["response_missing"])
        self.assertEqual(event["exception_type"], "ConnectionError")
        self.assertIn("RemoteDisconnected", " | ".join(event["exception_chain"]))

    def test_http_error_response_keeps_status_and_truncates_body_preview(self):
        debug_logs = []
        settings = self.bootstrap.HttpDebugSettings(enabled=True, body_max_chars=24)
        response = self.make_response(
            "https://example.com/block",
            403,
            "<html>" + ("blocked-" * 20) + "</html>",
            content_type="text/html; charset=utf-8",
        )

        def fake_request(session, method, url, **kwargs):
            return response

        with mock.patch("requests.sessions.Session.request", new=fake_request):
            result = self.bootstrap.execute_with_http_debug(
                lambda: requests.get("https://example.com/block"),
                request_batch_id="batch-2",
                dataset="stock_zh_index_daily_em",
                symbol="sh000001",
                attempt_no=1,
                max_attempts=1,
                debug_settings=settings,
                fetch_debug_logs=debug_logs,
            )

        self.assertIs(result, response)
        self.assertEqual(len(debug_logs), 1)
        event = debug_logs[0]
        self.assertFalse(event["response_missing"])
        self.assertEqual(event["response_status_code"], 403)
        self.assertTrue(event["response_body_preview"].endswith("...(truncated)"))
        self.assertTrue(self.bootstrap.debug_event_has_http_problem(event))

    def test_fetch_with_retry_preserves_success_flow_and_response_missing_flag(self):
        attempt_logs = []
        debug_logs = []
        settings = self.bootstrap.HttpDebugSettings(enabled=False, body_max_chars=80)
        ok_response = self.make_response("https://example.com/ok", 200, '{"ok":true}')

        class FakeFrame:
            empty = False

        def fake_request(session, method, url, **kwargs):
            return ok_response

        def fetch_func():
            requests.get("https://example.com/ok")
            return FakeFrame()

        with mock.patch.object(self.bootstrap, "RETRY_DELAYS_SECONDS", [0]):
            with mock.patch("requests.sessions.Session.request", new=fake_request):
                result = self.bootstrap.fetch_with_retry(
                    dataset="stock_zh_a_hist_raw",
                    symbol="600519",
                    fetch_func=fetch_func,
                    request_batch_id="batch-3",
                    fetch_attempt_logs=attempt_logs,
                    fetch_debug_logs=debug_logs,
                    http_debug_settings=settings,
                    soft_failure=False,
                )

        self.assertTrue(result.success)
        self.assertEqual(len(attempt_logs), 1)
        self.assertFalse(attempt_logs[0]["response_missing"])
        self.assertEqual(len(debug_logs), 1)
        self.assertEqual(debug_logs[0]["response_status_code"], 200)


if __name__ == "__main__":
    unittest.main()
