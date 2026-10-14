#!/usr/bin/env python3
"""
Headless Smoke Test & Verification Suite for MinJ AI Media Studio.
Verifies Python version, package imports, FFmpeg binary, Qt headless GUI initialization,
and theme stylesheet compilation.
"""
import sys
import os
from pathlib import Path

# Add src to pythonpath
root_dir = Path(__file__).resolve().parents[4]
src_dir = root_dir / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

# Enforce offscreen Qt platform for headless CI / testing
os.environ["QT_QPA_PLATFORM"] = "offscreen"


def run_smoke_test() -> int:
    print("=" * 60)
    print("🧪 MinJ AI Media Studio — Headless Smoke Test")
    print("=" * 60)
    failures = []

    # 1. Python Version Check
    py_ver = sys.version_info
    print(f"[*] Python Runtime: {py_ver.major}.{py_ver.minor}.{py_ver.micro}")
    if py_ver < (3, 12):
        failures.append(f"Python 3.12+ required, found {py_ver.major}.{py_ver.minor}")
    else:
        print("    [✓] Python version check passed")

    # 2. FFmpeg Binary Check
    try:
        from jela.core.ffmpeg_tools import ffmpeg_exe
        exe = ffmpeg_exe()
        print(f"[*] FFmpeg Binary: {exe}")
        if not exe or not os.path.exists(exe):
            failures.append(f"FFmpeg binary not found at: {exe}")
        else:
            print("    [✓] FFmpeg executable verified")
    except Exception as e:
        failures.append(f"FFmpeg verification failed: {e}")

    # 3. Core Engine Imports
    core_modules = [
        "jela.constants.theme_constants",
        "jela.constants.ui_constants",
        "jela.utils.config",
        "jela.core.worker",
        "jela.core.media_compat",
        "jela.core.ffmpeg_tools",
        "jela.core.asr_engine",
        "jela.core.tts_engine",
        "jela.core.translate_engine",
        "jela.core.ocr_engine",
        "jela.core.dubbing_engine",
        "jela.core.dub_project",
    ]
    print("[*] Verifying Core Engine Modules...")
    for mod in core_modules:
        try:
            __import__(mod)
            print(f"    [✓] {mod}")
        except Exception as e:
            print(f"    [✗] {mod}: {e}")
            failures.append(f"Failed to import {mod}: {e}")

    # 4. GUI & Stylesheet Verification
    print("[*] Verifying Headless PySide6 & Theme System...")
    try:
        from PySide6.QtWidgets import QApplication
        from jela.gui.styles import build_stylesheet
        from jela.gui.main_window import ToolWindow
        from jela.gui.components.tool_loader import ToolLoaderScreen
        from jela.constants import NAV_ITEMS

        app = QApplication.instance()
        if not app:
            app = QApplication(["jela_smoke_test", "-platform", "offscreen"])

        qss = build_stylesheet()
        print(f"    [✓] Compiled QSS Stylesheet: {len(qss)} characters")
        print(f"    [✓] Navigation Items Registered: {len(NAV_ITEMS)}")

        tool = NAV_ITEMS[0]
        loader = ToolLoaderScreen(tool_data=tool)
        print("    [✓] Instantiated ToolLoaderScreen successfully")
        win = ToolWindow(tool_index=0)
        print("    [✓] Instantiated ToolWindow successfully")
        # Avoid lingering widgets in offscreen smoke runs.
        loader.close()
        win.close()
    except Exception as e:
        failures.append(f"Headless GUI initialization failed: {e}")

    print("-" * 60)
    if failures:
        print(f"❌ Smoke Test FAILED with {len(failures)} issue(s):")
        for f in failures:
            print(f"   - {f}")
        return 1

    print("✅ All Smoke Tests PASSED! Jela environment is fully operational.")
    return 0


if __name__ == "__main__":
    sys.exit(run_smoke_test())
