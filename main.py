import sys
import os

# Add src to pythonpath
src_dir = os.path.join(os.path.dirname(__file__), "src")
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

from jela.app import main

if __name__ == "__main__":
    main()
