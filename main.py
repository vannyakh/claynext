import sys
import os

# Add src to pythonpath
src_dir = os.path.join(os.path.dirname(__file__), "src")
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

# Before Qt loads FFmpeg: hide benign Windows HEVC Media Foundation probe noise.
from claynext.utils.stderr_filter import install_ffmpeg_mf_stderr_filter

install_ffmpeg_mf_stderr_filter()

from claynext.app import main

if __name__ == "__main__":
    main()
