"""macOS Vision helper used by the Rust caption scan. Python only locates the binary."""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys

logger = logging.getLogger("claynext.adapters.vision")

_VISION_SWIFT = r'''
import Foundation
import Vision
import AppKit

let args = CommandLine.arguments
guard args.count >= 2 else { exit(2) }
let path = args[1]
let minConf = args.count >= 3 ? (Float(args[2]) ?? 0.2) : 0.2
var langs = Array(args.dropFirst(3))
if langs.isEmpty { langs = ["zh-Hans", "zh-Hant", "en-US"] }

guard let image = NSImage(contentsOfFile: path),
      let cg = image.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
    exit(3)
}
let request = VNRecognizeTextRequest()
request.recognitionLevel = .accurate
request.usesLanguageCorrection = false
request.recognitionLanguages = langs
try VNImageRequestHandler(cgImage: cg, options: [:]).perform([request])
let lines = (request.results ?? [])
    .sorted { $0.boundingBox.midY > $1.boundingBox.midY }
    .compactMap { obs -> String? in
        guard let hit = obs.topCandidates(1).first, hit.confidence >= minConf else { return nil }
        let text = hit.string.trimmingCharacters(in: .whitespacesAndNewlines)
        return text.isEmpty ? nil : text
    }
print(lines.joined(separator: "\n"))
'''

_cached: str | None = None


def ensure_reader() -> str | None:
    """Compiled on-device reader, or None when this machine cannot build it."""
    global _cached
    if _cached and os.path.isfile(_cached):
        return _cached
    if sys.platform != "darwin":
        return None
    from claynext.utils.paths import CACHE_DIR

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    binary = CACHE_DIR / "claynext-vision-ocr"
    source = CACHE_DIR / "claynext-vision-ocr.swift"
    try:
        current = source.read_text(encoding="utf-8") if source.is_file() else ""
    except Exception:
        current = ""
    if binary.is_file() and current == _VISION_SWIFT:
        _cached = str(binary)
        return _cached
    swift = shutil.which("swiftc") or ""
    if not swift:
        for candidate in ("/usr/bin/swiftc", "/Library/Developer/CommandLineTools/usr/bin/swiftc"):
            if os.path.isfile(candidate):
                swift = candidate
                break
    if not swift:
        return None
    try:
        source.write_text(_VISION_SWIFT, encoding="utf-8")
        subprocess.run(
            [swift, "-O", "-o", str(binary), str(source)],
            check=True,
            capture_output=True,
            timeout=180,
        )
    except Exception as exc:
        logger.warning("Vision OCR compile failed: %s", exc)
        return None
    _cached = str(binary)
    return _cached
