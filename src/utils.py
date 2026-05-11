from __future__ import annotations

import csv
import json
import os
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def today_string() -> str:
    return date.today().isoformat()


def ensure_directories() -> None:
    for path in ["data/reports", "outputs", "reports/companies", "public/assets", "public/companies", "public/data", "public/history"]:
        Path(path).mkdir(parents=True, exist_ok=True)


def load_env_file(path: Path | str = ".env") -> None:
    env_path = Path(path)
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def read_watchlist(path: Path | str = "data/watchlist.csv") -> list[dict[str, Any]]:
    with Path(path).open("r", encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))
    return [
        {
            "ticker": row.get("ticker", "").strip().upper(),
            "company": (row.get("company") or row.get("company_name") or "").strip(),
            "commodity": (row.get("commodity") or row.get("sector") or "").strip(),
            "exchange": row.get("exchange", "").strip(),
            "jurisdiction": row.get("jurisdiction", "").strip(),
            "official_url": row.get("official_url", "").strip(),
        }
        for row in rows
        if row.get("ticker")
    ]


def write_json(path: Path | str, data: Any) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def write_csv(path: Path | str, rows: list[dict[str, Any]]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        Path(path).write_text("", encoding="utf-8")
        return
    with Path(path).open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def money(value: Any) -> str:
    if value in (None, ""):
        return "n/a"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if abs(number) >= 1_000_000_000:
        return f"${number / 1_000_000_000:.1f}B"
    if abs(number) >= 1_000_000:
        return f"${number / 1_000_000:.1f}M"
    return f"${number:,.0f}"


def pct(value: Any) -> str:
    if value in (None, ""):
        return "n/a"
    try:
        return f"{float(value):.1f}%"
    except (TypeError, ValueError):
        return str(value)


def neutralize_investment_language(text: str) -> str:
    for old, new in {"buy": "positive", "Buy": "Positive", "sell": "negative", "Sell": "Negative", "you should invest": "it may warrant further research", "You should invest": "It may warrant further research"}.items():
        text = text.replace(old, new)
    return text
