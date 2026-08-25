import tempfile
import unittest
import sys
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[3] / "public" / "tool" / "app" / "http-soc-positioning-helper"
sys.path.insert(0, str(APP_ROOT))

from soc_positioning.manager import RunManager  # noqa: E402
from soc_positioning.portal_client import SocPortalClient  # noqa: E402


class FakeResponse:
    status_code = 200
    headers: dict[str, str] = {}
    text = "<form id='applyFm'><input name='KkTvlApply'></form>"

    def raise_for_status(self):
        return None


class FakeSession:
    def __init__(self):
        self.cookies: dict[str, str] = {}

    def get(self, url, **_kwargs):
        if "soc.jsp" in url:
            response = FakeResponse()
            response.text = "<div id='checkout_soc'>欢迎您，测试用户<a>退出</a></div>"
            return response
        return FakeResponse()

    def close(self):
        return None


class SocManagerTests(unittest.TestCase):
    def test_verification_starts_independent_keepalive(self):
        client = SocPortalClient(session=FakeSession())
        with tempfile.TemporaryDirectory() as directory:
            manager = RunManager(Path(directory), client, keepalive_interval_factory=lambda: 60)
            state = manager.verify("JSESSIONID=session-value")
            self.assertTrue(state["session"]["verified"])
            self.assertEqual(state["session"]["identity"], {"name": "测试用户"})
            self.assertTrue(state["session"]["keepAlive"]["running"])
            self.assertEqual(state["session"]["keepAlive"]["state"], "healthy")
            manager.shutdown()
            self.assertFalse(manager.snapshot()["session"]["keepAlive"]["running"])


if __name__ == "__main__":
    unittest.main()
