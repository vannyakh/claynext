"""Test Python-to-Rust bridge command execution."""
import unittest
from claynext.adapters.rust_engine import get_rust_engine


class TestRustBridge(unittest.TestCase):
    def test_rust_engine_project_creation(self):
        engine = get_rust_engine()
        if not engine.is_available():
            self.skipTest("claynext-engine binary not available")

        res = engine.create_project("IntegrationTest", width=1920, height=1080)
        self.assertEqual(res.get("status"), "ok")
        data = res.get("data")
        self.assertIsNotNone(data)
        self.assertEqual(data["name"], "IntegrationTest")
        self.assertEqual(data["canvas_width"], 1920)


if __name__ == "__main__":
    unittest.main()
