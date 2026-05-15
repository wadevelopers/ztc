"""Mixin con la lógica compartida de Load/Save de perfiles entre
`ColorEditorScreen` y `TerminalSettingsScreen`.

Las dos screens editan el mismo archivo de configuración del backend
(`alacritty.toml` / `kitty.conf`) — solo difieren en qué filas
renderizan. La mecánica de carga, guardado, switching de perfil y
conversión a manifest es idéntica. Vive acá para no duplicar 8 métodos
casi línea-por-línea.

Ubicación en `screens/` (no `services/`): el mixin abre modales,
llama a `self.app.push_screen` y `self.app.notify`, maneja `self.dirty`.
Es lógica de pantalla Textual, no service puro.
"""

from __future__ import annotations

from pathlib import Path

from ztc.services.profile_io import resolve_profile_path, validate_profile_path
from ztc.services.save_helper import compose_save_toast, save_profile_with_reload
from ztc.widgets.confirm import (
    ConfirmActionModal,
    PromptModal,
    UnsavedChangesModal,
)


class ProfileEditingMixin:
    """Lógica compartida de Load/Save de perfiles.

    Espera que la screen subclase defina:
      - self.backend         (TerminalBackend)
      - self.backend_path    (Path)
      - self.doc             (BackendDoc)
      - self.dirty           (bool)
      - self._refresh_header()
      - self._rebuild_list()

    Opcional: override `_refresh_profile_view()` para hooks extra (ej.
    refrescar warnings de contraste). El mixin la llama tras Load,
    Save-as, Save-unmanage.
    """

    # ---------- hook ----------

    def _refresh_profile_view(self) -> None:
        """Hook llamado tras cambios de perfil/path/doc. Default:
        refresh header + rebuild list. Subclases pueden override +
        super()._refresh_profile_view().

        En Load y Unmanage el doc se reemplaza; en Save-as solo cambia
        `backend_path` (el doc in-memory queda). El hook se llama en
        los tres casos porque la UI necesita sincronizarse (header,
        posiblemente warnings). El costo de `_rebuild_list` cuando el
        doc no cambió es trivial — no vale la pena dividir en hooks
        distintos."""
        self._refresh_header()
        self._rebuild_list()

    # ---------- Load ----------

    def action_load(self) -> None:
        """Carga un perfil desde archivo y lo deja como activo: escribe
        el manifest apuntando al nuevo perfil y aplica al terminal vivo
        via `set_active_profile`. Si hay cambios sin guardar, pide
        confirmacion antes (descartarlos perderia trabajo)."""
        if self.dirty:
            manifest_path = self.app.backend_manifest_path

            def after_dirty(choice: str | None) -> None:
                if choice == "discard":
                    self._prompt_load_profile()
                elif choice == "save" and manifest_path is not None:
                    # Save in-place al activo: el user ya eligio "save"
                    # en el modal, no abrimos un segundo modal de nombre.
                    self._save_in_place(manifest_path)
                    if not self.dirty:
                        self._prompt_load_profile()

            self.app.push_screen(UnsavedChangesModal(), after_dirty)
            return
        self._prompt_load_profile()

    def _prompt_load_profile(self) -> None:
        manifest_path = self.app.backend_manifest_path
        if manifest_path is None:
            return

        def after(path_str: str | None) -> None:
            if not path_str:
                return
            raw = Path(path_str).expanduser()
            path = raw if raw.is_absolute() else (manifest_path.parent / raw)
            if not path.exists():
                self.app.notify(
                    f"Does not exist: {path}", severity="error", timeout=8
                )
                return
            if path == manifest_path:
                # `include kitty.conf` dentro de `kitty.conf` = recursion
                # infinita al reload. El manifest no es perfil cargable.
                self.app.notify(
                    f"Cannot load the manifest file ({manifest_path.name}) "
                    "as a profile; choose another.",
                    severity="error",
                    timeout=8,
                )
                return
            self._do_load(path, manifest_path)

        self.app.push_screen(
            PromptModal(
                title="Load profile from file",
                placeholder=f"filename (next to {manifest_path.name}) or absolute path",
                confirm_label="Load",
            ),
            after,
        )

    def _do_load(self, path: Path, manifest_path: Path) -> None:
        """Carga `path` como perfil activo. Si el manifest aun no esta
        gestionado, lo convierte primero (silencioso, con backup
        automatico) y luego carga. El backup del estado pre-conversion
        queda cargable directo desde Load con su nombre."""
        convert_backup: Path | None = None
        if not self.backend.is_managed_manifest(manifest_path):
            try:
                convert_backup = self.backend.convert_to_manifest(
                    manifest_path, path
                )
            except Exception as exc:  # noqa: BLE001
                self.app.notify(
                    f"Convert error: {exc}", severity="error", timeout=10
                )
                return
        try:
            new_doc = self.backend.load(path)
        except Exception as exc:  # noqa: BLE001
            self.app.notify(f"Load error: {exc}", severity="error", timeout=10)
            return
        try:
            self.app.set_active_profile(path)
        except Exception as exc:  # noqa: BLE001
            self.app.notify(
                f"Profile switch error: {exc}", severity="error", timeout=10
            )
            return
        self.doc = new_doc
        self.backend_path = path
        self.dirty = False
        self._refresh_profile_view()
        msg = f"Loaded {path.name}"
        if convert_backup is not None:
            msg += f"  (previous setup: {convert_backup.name})"
        self.app.notify(msg, severity="information", timeout=6)

    # ---------- Save ----------

    def action_save(self) -> None:
        """Abre Save modal prellenado con el nombre actual.
        - Enter directo con mismo nombre → save in-place sobre el activo.
        - Nombre = manifest gestionado → unmanage: vuelve a standalone.
        - Nombre nuevo → save-as: crea archivo, set_active_profile, switch.
        Si el archivo destino existe y no es el activo, confirma overwrite.
        Si todavia no hay manifest, dispara conversion silenciosa antes."""
        manifest_path = self.app.backend_manifest_path
        if manifest_path is None:
            return

        def after(name: str | None) -> None:
            if not name:
                return
            new_path = resolve_profile_path(name, manifest_path.parent)
            # Save-in-place sobre el activo: no aplica validacion. Caso
            # standalone (backend_path == manifest_path) cae aca y es OK
            # — es save normal sobre el archivo default sin convertir.
            if new_path == self.backend_path:
                self._save_in_place(manifest_path)
                return
            # Save al manifest gestionado = "unmanage": volver a standalone.
            # En standalone manifest_path == backend_path, asi que ese caso
            # ya cayo en save-in-place arriba; aqui llegamos solo cuando
            # is_managed es True.
            if new_path == manifest_path:
                self._save_unmanage(manifest_path)
                return
            error = validate_profile_path(self.backend, new_path)
            if error:
                self.app.notify(error, severity="error", timeout=8)
                return
            if new_path.exists():
                def after_confirm(confirmed: bool | None) -> None:
                    if confirmed:
                        self._save_as(new_path, manifest_path)
                self.app.push_screen(
                    ConfirmActionModal(
                        title="Overwrite file?",
                        message=f"{new_path} already exists.",
                        confirm_label="Overwrite",
                    ),
                    after_confirm,
                )
                return
            self._save_as(new_path, manifest_path)

        self.app.push_screen(
            PromptModal(
                title="Save profile",
                initial=self.backend_path.name,
                confirm_label="Save",
            ),
            after,
        )

    def _save_in_place(self, manifest_path: Path) -> None:
        """Save al perfil activo. Usa `save_profile_with_reload` para que
        en Kitty el reload IPC lea las prefs runtime del manifest (no del
        perfil)."""
        try:
            result = save_profile_with_reload(
                self.backend, self.doc, self.backend_path, manifest_path
            )
        except Exception as exc:  # noqa: BLE001
            self.app.notify(f"Save error: {exc}", severity="error", timeout=10)
            return
        self.dirty = False
        self._refresh_header()
        self.app.notify(
            compose_save_toast(self.backend_path.name, result),
            severity="information",
            timeout=6,
        )

    def _save_unmanage(self, manifest_path: Path) -> None:
        """Volver a standalone: reescribe el manifest con el contenido
        del doc actual + managed directives preservadas. Quita el marker
        ztc. El perfil que estaba activo en disco NO se borra — caller
        humano decide."""
        try:
            backup = self.backend.unmanage_manifest(manifest_path, self.doc)
        except Exception as exc:  # noqa: BLE001
            self.app.notify(f"Save error: {exc}", severity="error", timeout=10)
            return
        # Recargar doc desde el manifest reescrito: ahora contiene
        # managed directives + el contenido del perfil. Esto mantiene la
        # UI sincronizada para futuras ediciones del archivo.
        self.doc = self.backend.load(manifest_path)
        try:
            self.app.set_active_profile(manifest_path)
        except Exception as exc:  # noqa: BLE001
            self.app.notify(
                f"Profile switch error: {exc}", severity="error", timeout=10
            )
            return
        self.backend_path = manifest_path
        self.dirty = False
        self._refresh_profile_view()
        msg = f"Saved as {manifest_path.name}"
        if backup is not None:
            msg += f"  (previous manifest: {backup.name})"
        self.app.notify(msg, severity="information", timeout=6)

    def _save_as(self, new_path: Path, manifest_path: Path) -> None:
        """Save-as a archivo nuevo. Si el manifest aun no esta gestionado,
        lo convierte silenciosamente primero (backup automatico) y luego
        guarda el doc in-memory al new_path."""
        convert_backup: Path | None = None
        if not self.backend.is_managed_manifest(manifest_path):
            try:
                convert_backup = self.backend.convert_to_manifest(
                    manifest_path, new_path
                )
            except Exception as exc:  # noqa: BLE001
                self.app.notify(
                    f"Convert error: {exc}", severity="error", timeout=10
                )
                return
        try:
            self.backend.save(self.doc, new_path)
        except Exception as exc:  # noqa: BLE001
            self.app.notify(f"Save error: {exc}", severity="error", timeout=10)
            return
        try:
            self.app.set_active_profile(new_path)
        except Exception as exc:  # noqa: BLE001
            self.app.notify(
                f"Profile switch error: {exc}", severity="error", timeout=10
            )
            return
        self.backend_path = new_path
        self.dirty = False
        self._refresh_profile_view()
        msg = f"Saved as {new_path.name}"
        if convert_backup is not None:
            msg += f"  (previous setup: {convert_backup.name})"
        self.app.notify(msg, severity="information", timeout=6)

    # ---------- Back ----------

    def action_back(self) -> None:
        if not self.dirty:
            self.app.pop_screen()
            return
        manifest_path = self.app.backend_manifest_path

        def after(choice: str | None) -> None:
            if choice == "discard":
                self.app.pop_screen()
                return
            if choice == "save" and manifest_path is not None:
                # Save in-place sobre el activo, sin modal de nombre: el
                # user ya eligio "save" para volver.
                self._save_in_place(manifest_path)
                if not self.dirty:
                    self.app.pop_screen()
                return

        self.app.push_screen(UnsavedChangesModal(), after)
