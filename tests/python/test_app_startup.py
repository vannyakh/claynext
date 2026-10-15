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


if __name__ == "__main__":
    unittest.main()
