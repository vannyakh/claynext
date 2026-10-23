"""The development-environment install command keeps every optional extra."""
import unittest


class TestDevEnvironmentCommand(unittest.TestCase):
    def test_sync_command_lists_every_declared_extra(self):
        from claynext.models.features import (
            dev_environment_extras,
            dev_environment_sync_command,
        )

        extras = dev_environment_extras()
        for name in ("whisperx", "demucs", "demucs-mlx", "voxcpm", "omnivoice", "gender"):
            self.assertIn(name, extras)
        cmd = dev_environment_sync_command()
        self.assertTrue(cmd.startswith("uv sync --inexact "))
        self.assertNotEqual(cmd, "uv sync --extra whisperx")
        self.assertNotIn("uv sync --extra whisperx", cmd)
        for name in extras:
            self.assertIn(f"--extra {name}", cmd)
        self.assertGreater(cmd.count("--extra"), 1)

    def test_gap_install_command_is_the_full_environment(self):
        from claynext.models.env_preflight import primary_install_command
        from claynext.models.features import dev_environment_sync_command

        gaps = [
            {
                "id": "whisperx",
                "kind": "package",
                "command": "uv sync --extra whisperx",
                "blocking": False,
            }
        ]
        cmd = primary_install_command(gaps)
        self.assertEqual(cmd, dev_environment_sync_command())
        self.assertIn("--inexact", cmd)
        self.assertIn("--extra whisperx", cmd)
        self.assertIn("--extra demucs-mlx", cmd)
        self.assertIn("--extra omnivoice", cmd)
        from claynext.models.env_preflight import format_gaps_message

        text = format_gaps_message([
            {
                "label": "WhisperX",
                "kind": "package",
                "command": cmd,
                "detail": "Prefer WhisperX is on, but WhisperX is not installed.",
                "blocking": False,
            },
            {
                "label": "Demucs stem bed",
                "kind": "package",
                "command": cmd,
                "detail": "Stem separation needs Demucs.",
                "blocking": True,
            },
        ])
        self.assertEqual(text.count(cmd), 1)
        self.assertNotIn("uv sync --extra whisperx", text)

    def test_full_environment_leaves_opt_in_flags_alone(self):
        from claynext.models.features import (
            dev_environment_extras,
            dev_environment_preference_keys,
        )

        plan = dev_environment_preference_keys()
        self.assertNotIn("transcript_ocr", plan)
        self.assertNotIn("prefer_voxcpm", plan)
        if "whisperx" in dev_environment_extras():
            self.assertEqual(plan.get("prefer_whisperx"), "1")


if __name__ == "__main__":
    unittest.main()
