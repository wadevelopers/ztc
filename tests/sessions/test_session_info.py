"""Tests del parser de session-metadata.kdl + session-layout.kdl y del
merge entre ambas fuentes."""

from __future__ import annotations

from pathlib import Path

import pytest

from ztc.sessions.services import session_info


@pytest.fixture
def tmp_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    return tmp_path


def _write_metadata(cache: Path, session_name: str, content: str) -> Path:
    folder = cache / "zellij" / "contract_version_1" / "session_info" / session_name
    folder.mkdir(parents=True, exist_ok=True)
    meta = folder / "session-metadata.kdl"
    meta.write_text(content, encoding="utf-8")
    return meta


def _write_layout(cache: Path, session_name: str, content: str) -> Path:
    folder = cache / "zellij" / "contract_version_1" / "session_info" / session_name
    folder.mkdir(parents=True, exist_ok=True)
    layout = folder / "session-layout.kdl"
    layout.write_text(content, encoding="utf-8")
    return layout


# ---------- casos sin archivos ----------


def test_returns_none_when_no_files(tmp_cache: Path) -> None:
    assert session_info.read_session_details("ghost") is None


# ---------- solo metadata (running sin layout) ----------


def test_metadata_only_extracts_tabs_without_panes(tmp_cache: Path) -> None:
    """Metadata sola: tabs sin paneles (metadata no persiste cmd/cwd)."""
    _write_metadata(
        tmp_cache,
        "main",
        '''name "main"
tabs {
    tab {
        name "system"
        position 0
    }
    tab {
        name "dev"
        position 1
    }
}
''',
    )
    details = session_info.read_session_details("main")
    assert details is not None
    assert details.source == "metadata"
    assert [t.name for t in details.tabs] == ["system", "dev"]
    # Metadata no aporta paneles.
    assert all(t.panes == [] for t in details.tabs)


def test_metadata_finds_tilde_suffix(tmp_cache: Path) -> None:
    _write_metadata(
        tmp_cache,
        "work~",
        '''name "work~"
tabs {
}
''',
    )
    details = session_info.read_session_details("work")
    assert details is not None
    assert details.name == "work"


# ---------- solo layout (exited) ----------


def test_layout_only_extracts_tabs_and_panes(tmp_cache: Path) -> None:
    """Sesion exited: solo hay layout. Tabs + panes con cmd/cwd."""
    _write_layout(
        tmp_cache,
        "old",
        '''layout {
    cwd "/home/martin"
    tab name="system" {
        pane size=1 borderless=true {
            plugin location="zellij:compact-bar"
        }
        pane command="btop" cwd="/home/martin"
    }
    tab name="dev" {
        pane command="vim" cwd="/home/martin/proj"
    }
}
''',
    )
    details = session_info.read_session_details("old")
    assert details is not None
    assert details.source == "layout"
    assert [t.name for t in details.tabs] == ["system", "dev"]

    system = details.tabs[0]
    # El plugin pane (compact-bar) se filtra; queda solo btop.
    assert len(system.panes) == 1
    assert system.panes[0].command == "btop"
    assert system.panes[0].cwd == "/home/martin"

    dev = details.tabs[1]
    assert len(dev.panes) == 1
    assert dev.panes[0].command == "vim"
    assert dev.panes[0].cwd == "/home/martin/proj"


def test_layout_with_tilde_suffix(tmp_cache: Path) -> None:
    _write_layout(
        tmp_cache,
        "old~",
        '''layout {
    tab name="solo" {
    }
}
''',
    )
    details = session_info.read_session_details("old")
    assert details is not None
    assert [t.name for t in details.tabs] == ["solo"]


def test_layout_with_nested_panes(tmp_cache: Path) -> None:
    """Splits anidados: panes dentro de panes. Se preservan en
    `children` para que el rendering pueda mostrar el nesting."""
    _write_layout(
        tmp_cache,
        "old",
        '''layout {
    tab name="dev" {
        pane {
            pane command="server" cwd="/srv"
            pane {
                pane command="client" cwd="/cli"
            }
        }
    }
}
''',
    )
    details = session_info.read_session_details("old")
    assert details is not None
    tab = details.tabs[0]
    # Top-level pane sin cmd/cwd, pero con hijos.
    assert len(tab.panes) == 1
    outer = tab.panes[0]
    assert outer.command is None
    assert outer.cwd is None
    # Tiene 2 hijos: server y un wrapper que contiene client.
    assert len(outer.children) == 2
    assert outer.children[0].command == "server"
    assert outer.children[0].cwd == "/srv"
    assert outer.children[1].command is None
    assert len(outer.children[1].children) == 1
    assert outer.children[1].children[0].command == "client"


def test_layout_filters_chrome_plugins(tmp_cache: Path) -> None:
    """compact-bar, status-bar y similares (zellij:* plugins) se omiten:
    son chrome de Zellij, no comandos del usuario."""
    _write_layout(
        tmp_cache,
        "old",
        '''layout {
    tab name="t" {
        pane size=1 borderless=true {
            plugin location="zellij:compact-bar"
        }
        pane command="real-cmd"
        pane size=2 borderless=true {
            plugin location="zellij:status-bar"
        }
    }
}
''',
    )
    details = session_info.read_session_details("old")
    assert details is not None
    panes = details.tabs[0].panes
    assert len(panes) == 1
    assert panes[0].command == "real-cmd"


# ---------- merge metadata + layout (sesion viva con datos de paneles) ----------


def test_merge_uses_metadata_tabs_and_layout_panes(tmp_cache: Path) -> None:
    """Sesion viva con ambos archivos: tabs y mtime de metadata
    (estado actual), panes de layout (datos de cmd/cwd)."""
    _write_metadata(
        tmp_cache,
        "main",
        '''name "main"
tabs {
    tab {
        name "system"
        position 0
    }
    tab {
        name "dev"
        position 1
    }
}
''',
    )
    _write_layout(
        tmp_cache,
        "main",
        '''layout {
    tab name="system" {
        pane command="btop" cwd="/home/martin"
    }
    tab name="dev" {
        pane command="vim" cwd="/home/martin/proj"
    }
}
''',
    )
    details = session_info.read_session_details("main")
    assert details is not None
    assert details.source == "merged"
    assert [t.name for t in details.tabs] == ["system", "dev"]
    assert details.tabs[0].panes[0].command == "btop"
    assert details.tabs[1].panes[0].command == "vim"


def test_merge_metadata_tabs_take_precedence_over_layout(tmp_cache: Path) -> None:
    """Si layout tiene un tab que metadata ya no tiene (ej. el usuario
    lo cerro vivo), no aparece. Y si metadata tiene un tab nuevo que
    layout no tiene, aparece sin paneles."""
    _write_metadata(
        tmp_cache,
        "main",
        '''name "main"
tabs {
    tab {
        name "live-only"
    }
    tab {
        name "system"
    }
}
''',
    )
    _write_layout(
        tmp_cache,
        "main",
        '''layout {
    tab name="system" {
        pane command="btop"
    }
    tab name="layout-only" {
        pane command="ghost"
    }
}
''',
    )
    details = session_info.read_session_details("main")
    assert details is not None
    names = [t.name for t in details.tabs]
    assert names == ["live-only", "system"]  # solo lo que dice metadata
    # live-only sin paneles (no esta en layout).
    assert details.tabs[0].panes == []
    # system con su pane de layout.
    assert details.tabs[1].panes[0].command == "btop"


def test_merge_uses_metadata_mtime(tmp_cache: Path) -> None:
    """El mtime sale de metadata (mas reciente, refleja actividad)."""
    import os
    import time

    _write_layout(tmp_cache, "main", 'layout {\n    tab name="t" {}\n}\n')
    time.sleep(0.05)
    meta = _write_metadata(
        tmp_cache,
        "main",
        '''name "main"
tabs {
    tab {
        name "t"
    }
}
''',
    )
    details = session_info.read_session_details("main")
    assert details is not None
    assert details.source == "merged"
    assert details.mtime == os.path.getmtime(meta)
