from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.database import DB_PATH, initialize_database, upsert_watchlist
from src.utils import ensure_directories, read_watchlist


def main() -> None:
    ensure_directories()
    initialize_database(DB_PATH)
    upsert_watchlist(DB_PATH, read_watchlist())
    print(f"Initialized {DB_PATH}")


if __name__ == "__main__":
    main()
