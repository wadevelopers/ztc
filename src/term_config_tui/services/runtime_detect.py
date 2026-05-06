"""Deteccion de la terminal en la que corre el TUI y de la presencia de
Zellij. Pensado para llamar una sola vez al arranque (`__init__` de la
app) y guardar el resultado para `compose()` y `on_mount()`.

Reglas de deteccion (en orden):

1. Override por env var `TERM_CONFIG_TUI_BACKEND`:
   - None / "" / "auto" -> ignorar override, continuar con autodetect.
   - "alacritty" / "kitty" -> usar ese kind directo, saltea autodetect.
   - cualquier otro valor -> `kind="unsupported"` con
     `invalid_override_value=<valor>` para que el boot dispare un toast.

2. Markers distintivos por env var (sobreviven multiplexores):
   - `ALACRITTY_WINDOW_ID` o `ALACRITTY_SOCKET` -> alacritty.
   - `KITTY_PID` o `KITTY_WINDOW_ID` -> kitty.

3. Fallback secundario:
   - `TERM_PROGRAM` (e.g. "iTerm.app") — informativo, no habilita
     soporte (ninguno de esos esta soportado en Fase B).
   - `TERM` ("xterm-kitty", "xterm-256color", etc.) — idem, salvo
     `xterm-kitty` que es senal fuerte de kitty.

4. Si nada matchea -> `kind="unsupported"`.

`via_ssh` es independiente: True si `SSH_CONNECTION` esta seteado.
La UI usa este flag para deshabilitar la edicion de colores aunque
la terminal sea soportada.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from typing import Literal

TerminalKind = Literal["alacritty", "kitty", "unsupported"]

VALID_OVERRIDE_KINDS: tuple[TerminalKind, ...] = ("alacritty", "kitty")


@dataclass(frozen=True)
class TerminalDetection:
    kind: TerminalKind
    via_ssh: bool
    raw_marker: str | None
    """Indica como se detecto. Util para debug/tooltips. Ejemplos:
    `env:ALACRITTY_WINDOW_ID`, `override:kitty`, `TERM=xterm-kitty`,
    `TERM_PROGRAM=iTerm.app`, None si no hay senal."""

    invalid_override_value: str | None = None
    """Setea solo si TERM_CONFIG_TUI_BACKEND tenia un valor invalido.
    Cuando esta seteado, kind = 'unsupported' y la app debe disparar
    un toast de override invalido al boot."""


def detect_terminal(env: dict[str, str] | None = None) -> TerminalDetection:
    """Detecta la terminal en la que corre el TUI.

    `env` permite inyectar un mapa de env vars en tests; por defecto
    se usa `os.environ`.
    """
    e = os.environ if env is None else env
    via_ssh = bool(e.get("SSH_CONNECTION"))

    # 1. Override por env var.
    override = e.get("TERM_CONFIG_TUI_BACKEND")
    if override and override.strip() and override.strip() != "auto":
        value = override.strip()
        if value in VALID_OVERRIDE_KINDS:
            return TerminalDetection(
                kind=value,  # type: ignore[arg-type]
                via_ssh=via_ssh,
                raw_marker=f"override:{value}",
            )
        return TerminalDetection(
            kind="unsupported",
            via_ssh=via_ssh,
            raw_marker=f"override:{value}",
            invalid_override_value=value,
        )

    # 2. Markers distintivos.
    if e.get("ALACRITTY_WINDOW_ID") or e.get("ALACRITTY_SOCKET"):
        marker = "ALACRITTY_WINDOW_ID" if e.get("ALACRITTY_WINDOW_ID") else "ALACRITTY_SOCKET"
        return TerminalDetection(
            kind="alacritty", via_ssh=via_ssh, raw_marker=f"env:{marker}"
        )
    if e.get("KITTY_PID") or e.get("KITTY_WINDOW_ID"):
        marker = "KITTY_PID" if e.get("KITTY_PID") else "KITTY_WINDOW_ID"
        return TerminalDetection(
            kind="kitty", via_ssh=via_ssh, raw_marker=f"env:{marker}"
        )

    # 3. Fallback: TERM, TERM_PROGRAM. Solo xterm-kitty es senal fuerte.
    term = e.get("TERM", "")
    if term == "xterm-kitty":
        return TerminalDetection(
            kind="kitty", via_ssh=via_ssh, raw_marker=f"TERM={term}"
        )

    term_program = e.get("TERM_PROGRAM", "")
    if term_program:
        # Ningun TERM_PROGRAM conocido mapea a alacritty/kitty fuera de
        # los markers ya chequeados. Lo registramos para debug pero
        # devolvemos unsupported.
        return TerminalDetection(
            kind="unsupported",
            via_ssh=via_ssh,
            raw_marker=f"TERM_PROGRAM={term_program}",
        )

    # 4. Nada matchea.
    return TerminalDetection(
        kind="unsupported",
        via_ssh=via_ssh,
        raw_marker=f"TERM={term}" if term else None,
    )


def detect_zellij_installed() -> bool:
    """True si el binario `zellij` esta en PATH."""
    return shutil.which("zellij") is not None
