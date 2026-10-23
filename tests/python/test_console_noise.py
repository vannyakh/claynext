"""Console noise and library progress stay off the raw tqdm bar.

Run:
    PYTHONPATH=src .venv/bin/python tests/python/test_console_noise.py
"""
from __future__ import annotations

import os
import unittest


class ConsoleNoiseTests(unittest.TestCase):
    def test_drops_malloc_stack_line_and_keeps_real_errors(self):
        from claynext.utils.console_noise import sanitize_console_text

        noise = (
            "python(93753) MallocStackLogging: can't turn off malloc stack logging "
            "because it was not enabled.\n"
        )
        self.assertEqual(sanitize_console_text(noise), "")
        kept = sanitize_console_text("RuntimeError: transcription failed\n")
        self.assertIn("RuntimeError: transcription failed", kept)
        mixed = (
            "RuntimeError: MallocStackLogging: can't turn off malloc stack logging "
            "because it was not enabled.\n"
        )
        self.assertIn("RuntimeError", sanitize_console_text(mixed))
        glued = (
            "\r  0%|          | 0/346 [00:00<?, ?it/s]"
            "python(93753) MallocStackLogging: can't turn off malloc stack logging "
            "because it was not enabled.\n"
        )
        self.assertEqual(sanitize_console_text(glued), "")

    def test_drops_tqdm_bar_and_keeps_status_text(self):
        from claynext.utils.console_noise import sanitize_console_text

        bar = "  0%|          | 0/346 [00:00<?, ?it/s]\n"
        self.assertEqual(sanitize_console_text(bar), "")
        described = "segments:   3%|▎         | 12/346 [00:02<01:00,  5.2seg/s]\n"
        self.assertEqual(sanitize_console_text(described), "")
        self.assertIn("Extracting audio", sanitize_console_text("Extracting audio…\n"))
        self.assertIn("16%", sanitize_console_text("[  16%] Transcribing speech…\n"))

    def test_status_log_skips_count_ticks(self):
        from claynext.utils.console_noise import status_worth_logging

        first = "第003集.mp4 · Speaking 0/346"
        nxt = "第003集.mp4 · Speaking 12/346"
        stage = "第003集.mp4 · Transcribing speech…"
        self.assertTrue(status_worth_logging("", first))
        self.assertFalse(status_worth_logging(first, nxt))
        self.assertTrue(status_worth_logging(first, stage))

    def test_scrub_removes_malloc_vars_from_child_env(self):
        from claynext.utils.process_env import child_environ, scrub_malloc_stack_logging

        base = {
            "PATH": "/usr/bin",
            "MallocStackLogging": "1",
            "MallocStackLoggingNoCompact": "1",
        }
        env = child_environ(base)
        self.assertEqual(env["PATH"], "/usr/bin")
        self.assertNotIn("MallocStackLogging", env)
        self.assertNotIn("MallocStackLoggingNoCompact", env)
        self.assertEqual(base["MallocStackLogging"], "1")
        scrub_malloc_stack_logging(base)
        self.assertNotIn("MallocStackLogging", base)

    def test_tqdm_reports_count_without_drawing_a_bar(self):
        from tqdm import tqdm

        from claynext.utils.library_progress import (
            bind_job_progress,
            install_quiet_tqdm,
            library_stage,
        )

        install_quiet_tqdm()
        seen: list[tuple[object, object]] = []

        def record(pct, msg=""):
            seen.append((pct, msg))

        with bind_job_progress(record) as wrapped:
            wrapped(16, "Transcribing speech…")
            with library_stage("Transcribing"):
                for _ in tqdm(range(4)):
                    pass
        messages = [msg for _pct, msg in seen]
        self.assertIn("Transcribing speech…", messages)
        self.assertTrue(any(str(msg).startswith("Transcribing ") and "/4" in str(msg) for msg in messages))
        self.assertTrue(all("%|" not in str(msg) for msg in messages))
        # The opening frame is 0/N, then the loop advances. The job percent stays put.
        counted = [(pct, msg) for pct, msg in seen if "/4" in str(msg)]
        self.assertTrue(counted)
        self.assertTrue(all(pct == 16 for pct, _msg in counted))


class ScrubProcessTests(unittest.TestCase):
    def test_current_process_scrub_is_reversible(self):
        from claynext.utils.process_env import scrub_malloc_stack_logging

        key = "MallocStackLogging"
        previous = os.environ.get(key)
        os.environ[key] = "1"
        try:
            scrub_malloc_stack_logging()
            self.assertNotIn(key, os.environ)
        finally:
            if previous is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = previous


if __name__ == "__main__":
    unittest.main()
