"""PyInstaller entry script. It must use an absolute import: PyInstaller runs the entry file as a top-level script, where the
relative imports of rdt/launcher.py would fail."""
import sys

from rdt.launcher import main

if __name__ == "__main__":
    sys.exit(main())
