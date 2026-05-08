"""Persistencia mínima de zsm: solo `last_layout` (para pre-seleccionar el
layout en el modal). Vive en `~/.cache/zsm/state.json`."""

from __future__ import annotations

import json
import os
from pathlib import Path


def state_path() -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "zsm" / "state.json"


def read_state() -> dict:
    p = state_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def write_state(state: dict) -> None:
    p = state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, indent=2), encoding="utf-8")


def get_last_layout() -> str | None:
    value = read_state().get("last_layout")
    return value if isinstance(value, str) and value else None


def set_last_layout(name: str) -> None:
    state = read_state()
    state["last_layout"] = name
    write_state(state)
