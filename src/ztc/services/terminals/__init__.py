"""Abstraccion de backends de terminal: Protocol comun y tipos
canonicos. Cada backend concreto vive en `services/terminals/<kind>.py`."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from ztc.services.colors import CanonicalSlot
from ztc.services.terminals.settings import CanonicalSetting

# Doc opaco que cada backend tipa internamente (TOMLDocument para
# alacritty, lista de lineas para kitty/ghostty).
BackendDoc = Any


@runtime_checkable
class TerminalBackend(Protocol):
    """Interfaz comun a todos los backends de terminal.

    Un backend lee/escribe slots canonicos `(group, name)` y settings
    canonicos mapeandolos a la nomenclatura propia de su archivo de
    config. Expone capacidades runtime para aplicar o explicar la
    recarga post-save, y soporta perfiles intercambiables via
    manifest (`read/write_active_profile`, `convert_to_manifest`,
    `reload_after_profile_*`).
    """

    kind: str
    display_name: str

    def default_config_path(self) -> Path: ...

    def load(self, path: Path) -> BackendDoc: ...

    def save(self, doc: BackendDoc, path: Path) -> Path | None:
        """Devuelve el path del backup creado, o None si no habia
        archivo previo (no hay backup que crear)."""
        ...

    def read_slot(
        self, doc: BackendDoc, slot: CanonicalSlot
    ) -> str | None: ...

    def write_slot(
        self, doc: BackendDoc, slot: CanonicalSlot, value: str
    ) -> None: ...

    def delete_slot(self, doc: BackendDoc, slot: CanonicalSlot) -> bool: ...

    def supported_slots(self) -> list[CanonicalSlot]: ...

    # ---------- settings (padding, opacity, font, cursor shape, ...) ----------

    def read_setting(
        self, doc: BackendDoc, setting: CanonicalSetting
    ) -> object | None:
        """Devuelve el valor actual del setting (tipo segun setting.kind),
        o None si no esta definido en el archivo."""
        ...

    def write_setting(
        self, doc: BackendDoc, setting: CanonicalSetting, value: object
    ) -> None:
        """Escribe value en el archivo con el formato propio del backend.

        Antes de escribir, llama a `validate_setting_value(setting, value)`
        y levanta `ValueError` si el valor no es valido (rango, kind,
        enum). Asi la validacion vive en un solo lugar (el catalogo) y
        no depende solo de la UI — un caller programatico tampoco puede
        meter basura en el archivo.
        """
        ...

    def delete_setting(
        self, doc: BackendDoc, setting: CanonicalSetting
    ) -> bool:
        """Elimina la entrada del archivo. Devuelve True si existia."""
        ...

    def supported_settings(self) -> list[CanonicalSetting]:
        """Lista de settings que este backend soporta."""
        ...

    # ---------- runtime post-save ----------

    def reload_after_save(self, doc: BackendDoc, path: Path) -> bool:
        """Intenta aplicar al terminal en ejecucion el archivo recien
        guardado.

        `doc` y `path` son el documento y la ruta que acaban de pasar
        por `save()`, para que el backend pueda decidir con el estado
        efectivo recien persistido.

        Devuelve True si la recarga funciono o si el backend recarga
        nativamente sin accion extra. Devuelve False si no se pudo
        recargar de forma programatica; el caller puede mostrar
        `manual_reload_hint()`.
        """
        ...

    def manual_reload_hint(self) -> str | None:
        """Instruccion visible al usuario cuando `reload_after_save(...)`
        devuelve False. None si el backend no requiere hint manual."""
        ...

    # ---------- perfiles intercambiables (manifest + profile switching) ----------

    def is_managed_manifest(self, path: Path) -> bool:
        """True si `path` es un manifest gestionado por ztc (tiene el
        marcador propio). Si False, el archivo se trata como config
        standalone — no se hace profile switching sobre el."""
        ...

    def read_active_profile(self, manifest_path: Path) -> Path | None:
        """Si `manifest_path` es un manifest gestionado por ztc, devuelve
        el path absoluto del perfil activo (primer `import` en Alacritty,
        primer `include` en Kitty). Si no es manifest o no tiene perfil
        referenciado, devuelve None."""
        ...

    def write_active_profile(
        self, manifest_path: Path, profile_path: Path
    ) -> None:
        """Reescribe el manifest para que apunte a `profile_path`.
        Preserva el marcador y el resto del archivo (en Kitty: prefs
        runtime `# ztc:{...}` y managed directives)."""
        ...

    def unmanage_manifest(
        self, manifest_path: Path, profile_doc: BackendDoc
    ) -> Path | None:
        """Reverse de `convert_to_manifest`: vuelve `manifest_path` a un
        archivo standalone con el contenido de `profile_doc` adentro.

        Preserva las managed directives (Kitty: `allow_remote_control`,
        `listen_on`, `dynamic_background_opacity`) y las prefs `# ztc:`
        existentes — solo quita la key `managed_manifest`. Si el dict
        `# ztc:` queda vacio tras quitarla, no se escribe la linea.

        Hace backup automatico del manifest antes de reescribir. NO toca
        el archivo del perfil activo en disco (caller decide que hacer
        con el).

        Devuelve el path del backup del manifest. Devuelve `None` si
        `manifest_path` no es manifest gestionado (no hay nada que
        des-hacer)."""
        ...

    def convert_to_manifest(
        self, manifest_path: Path, active_profile: Path
    ) -> Path | None:
        """Convierte `manifest_path` en un manifest gestionado por ztc
        que importa `active_profile`.

        El contenido previo de `manifest_path` se preserva en un backup
        automatico (`make_backup`); NO se duplica en el active_profile.
        Si el caller necesita preservarlo como perfil cargable, debe
        leer el backup despues.

        Detalles por backend:
        - Alacritty: reescribe el archivo como manifest minimal
          (`[ztc] managed_manifest = true` + `[general] import = [...]`).
        - Kitty: el manifest conserva las managed directives
          (`allow_remote_control`, `listen_on`,
          `dynamic_background_opacity`) y la linea `# ztc:{...}` con sus
          prefs runtime, agregando `managed_manifest: true`. El resto
          del contenido (colors, font_size, includes propios) se
          descarta del manifest — vive solo en el backup.

        El caller es responsable de que `active_profile` exista (Load:
        ya existe; Save-as: caller lo escribe con `backend.save`).

        Devuelve el path del backup del archivo original.
        """
        ...

    def reload_after_profile_switch(
        self, manifest_path: Path, new_profile_path: Path
    ) -> bool:
        """Recarga la terminal viva tras un switch de perfil
        (`write_active_profile` recien escribio el manifest). Alacritty
        retorna True directo (live-reload nativo del manifest); Kitty
        invoca `kitty @ load-config` + `set-background-opacity`
        idempotente."""
        ...

    def reload_after_profile_save(
        self,
        profile_doc: BackendDoc,
        profile_path: Path,
        manifest_path: Path,
    ) -> bool:
        """Recarga tras un save al perfil activo (sin cambio de perfil).
        Para Kitty: igual que `reload_after_save` pero leyendo prefs
        runtime (`allow_remote_control`, `listen_on`,
        `remote_control_pending_instance`) del manifest, no del
        `profile_doc`. Para Alacritty: True directo. Usado por el helper
        `save_profile_with_reload`."""
        ...


__all__ = [
    "BackendDoc",
    "CanonicalSetting",
    "CanonicalSlot",
    "TerminalBackend",
]
