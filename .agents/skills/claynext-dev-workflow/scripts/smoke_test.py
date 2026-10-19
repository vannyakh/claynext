#!/usr/bin/env python3
"""
Headless Smoke Test & Verification Suite for Claynext Studio.
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
    print("============================================================")
    print("[*] Claynext Studio - Headless Smoke Test")
    print("============================================================")
    failures = []

    # 1. Python Version Check
    py_ver = sys.version_info
    print(f"[*] Python Runtime: {py_ver.major}.{py_ver.minor}.{py_ver.micro}")
    if py_ver < (3, 12):
        failures.append(f"Python 3.12+ required, found {py_ver.major}.{py_ver.minor}")
    else:
        print("    [+] Python version check passed")

    # 2. FFmpeg Binary Check
    try:
        from claynext.adapters.ffmpeg_service import ffmpeg_exe
        exe = ffmpeg_exe()
        print(f"[*] FFmpeg Binary: {exe}")
        if not exe or not os.path.exists(exe):
            failures.append(f"FFmpeg binary not found at: {exe}")
        else:
            print("    [+] FFmpeg executable verified")
    except Exception as e:
        failures.append(f"FFmpeg verification failed: {e}")

    # 3. Core Engine & Service Imports
    core_modules = [
        "claynext.constants.theme_constants",
        "claynext.constants.ui_constants",
        "claynext.utils.config",
        "claynext.gui.worker",
        "claynext.adapters.media",
        "claynext.adapters.ffmpeg_service",
        "claynext.adapters.rust_bridge",
        "claynext.adapters.rust_engine",
        "claynext.models.asr_service",
        "claynext.models.tts_service",
        "claynext.models.translate_service",
        "claynext.models.ocr_service",
        "claynext.models.dubbing_service",
        "claynext.models.dub_project",
    ]
    print("[*] Verifying Core Engine Modules...")
    for mod in core_modules:
        try:
            __import__(mod)
            print(f"    [+] {mod}")
        except Exception as e:
            print(f"    [-] {mod}: {e}")
            failures.append(f"Failed to import {mod}: {e}")

    # 4. GUI & Stylesheet Verification
    print("[*] Verifying Headless PySide6 & Theme System...")
    try:
        from PySide6.QtWidgets import QApplication
        from claynext.gui.styles import build_stylesheet
        from claynext.gui.main_window import ToolWindow
        from claynext.gui.components.shell.loader import ToolLoaderScreen
        from claynext.constants import NAV_ITEMS

        app = QApplication.instance()
        if not app:
            app = QApplication(["claynext_smoke_test", "-platform", "offscreen"])

        qss = build_stylesheet()
        print(f"    [+] Compiled QSS Stylesheet: {len(qss)} characters")
        print(f"    [+] Navigation Items Registered: {len(NAV_ITEMS)}")

        tool = NAV_ITEMS[0]
        loader = ToolLoaderScreen(tool_data=tool)
        print("    [+] Instantiated ToolLoaderScreen successfully")
        win = ToolWindow(tool_index=0)
        print("    [+] Instantiated ToolWindow successfully")
        # Avoid lingering widgets in offscreen smoke runs.
        loader.close()
        win.close()
    except Exception as e:
        failures.append(f"Headless GUI initialization failed: {e}")

    print("-" * 60)
    if failures:
        print(f"[FAIL] Smoke Test FAILED with {len(failures)} issue(s):")
        for f in failures:
            print(f"   - {f}")
        return 1

    print("[SUCCESS] All Smoke Tests PASSED! Claynext environment is fully operational.")
    return 0


if __name__ == "__main__":
    sys.exit(run_smoke_test())
