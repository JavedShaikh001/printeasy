"""Entry point used by the installers (PyInstaller needs a plain script)."""
import sys

from printeasy.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
