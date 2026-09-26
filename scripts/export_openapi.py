#!/usr/bin/env python3
"""Dump the backend OpenAPI schema into the public docs folder.

Runs without Postgres, ML service or NDTP telemetry: it only imports the
FastAPI app and serialises the generated schema.
"""

from __future__ import annotations

import json
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
DOCS_DIR = REPO_ROOT / "docs" / "public"

sys.path.insert(0, str(BACKEND_DIR))

from app.main import app  # noqa: E402


def main() -> None:
    """Write ``openapi.json`` and a ReDoc viewer into ``docs/public``."""
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    schema = app.openapi()
    target = DOCS_DIR / "openapi.json"
    target.write_text(
        json.dumps(schema, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        f"Wrote {target.relative_to(REPO_ROOT)} "
        f"({len(schema['paths'])} paths, "
        f"{len(schema.get('components', {}).get('schemas', {}))} schemas)"
    )


if __name__ == "__main__":
    main()
