"""Resolve bundled read-only UI assets in source and PyInstaller builds."""

import sys
from pathlib import Path


def resource_path(*parts: str) -> str:
    root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))
    return str(root.joinpath(*parts))
