from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.site_generator import build_site
from src.utils import ensure_directories


def main() -> None:
    ensure_directories()
    build_site()
    print("Static research portal generated in public/")


if __name__ == "__main__":
    main()
