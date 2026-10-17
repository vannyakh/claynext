"""Test headless startup and model integrity for Claynext Studio."""
import unittest


class TestAppStartup(unittest.TestCase):
    def test_package_import(self):
        import claynext
        self.assertIsNotNone(claynext.__file__)

    def test_models_import(self):
        from claynext.models.project import Project, ProjectSettings
        from claynext.models.timeline import TimelineClip, TimelineTrack
        from claynext.models.media import MediaMetadata

        settings = ProjectSettings()
        proj = Project(name="Test", settings=settings)
        self.assertEqual(proj.name, "Test")
        self.assertEqual(proj.settings.width, 1920)

    def test_adapters_import(self):
        from claynext.adapters import (
            get_rust_engine,
            get_media_adapter,
            get_timeline_adapter,
            get_rendering_adapter,
            get_hardware_codecs,
        )
        engine = get_rust_engine()
        self.assertIsNotNone(engine)

    def test_rust_ai_adapter(self):
        from claynext.adapters.rust_bridge import RustAiAdapter

        # Test rate limit parsing via Rust AI binary
        limited, retry_after = RustAiAdapter.parse_retry_after(429, header="35", body="Rate limited")
        self.assertTrue(limited)
        self.assertGreaterEqual(retry_after, 20.0)

        # Test expression tags parsing
        tags = RustAiAdapter.parse_expression_tags("Hello! [pause: 0.5s] [excited] Wow!")
        self.assertGreaterEqual(len(tags), 2)

    def test_llm_keys_pool(self):
        from claynext.models.llm_keys import parse_retry_after, is_rate_limit

        self.assertTrue(is_rate_limit(429))
        self.assertTrue(is_rate_limit(200, "RESOURCE_EXHAUSTED"))
        self.assertFalse(is_rate_limit(200, "success"))
        self.assertGreaterEqual(parse_retry_after(headers={"Retry-After": "45"}), 20.0)


if __name__ == "__main__":
    unittest.main()

