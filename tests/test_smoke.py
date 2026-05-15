def test_import_package():
    import ztc

    assert ztc.__version__


def test_import_app():
    from ztc.app import TermConfigApp

    app = TermConfigApp()
    assert app.TITLE.startswith("ztc")


def test_default_paths_point_to_home():
    from ztc.models.config import Paths

    p = Paths.default()
    assert "config.kdl" in str(p.zellij_config)
    assert p.zellij_layouts_dir.name == "layouts"


def test_alacritty_detection_resolves_to_alacritty_backend(tmp_path):
    """Si la deteccion devuelve kind='alacritty', el registry resuelve
    AlacrittyBackend automaticamente (sin necesidad de pasarlo)."""
    from ztc.app import TermConfigApp
    from ztc.services.runtime_detect import TerminalDetection
    from ztc.services.terminals.alacritty import AlacrittyBackend

    detection = TerminalDetection(
        kind="alacritty", via_ssh=False, raw_marker="env:ALACRITTY_WINDOW_ID"
    )
    config_path = tmp_path / "alacritty.toml"
    app = TermConfigApp(
        backend_path=config_path,
        detection=detection,
        zellij_installed=True,
    )
    assert isinstance(app.backend, AlacrittyBackend)
    assert app.backend.kind == "alacritty"
    assert app.backend_path == config_path


def test_unsupported_detection_yields_no_backend():
    """Sin terminal soportada, el backend es None y el menu se desactiva."""
    from ztc.app import TermConfigApp
    from ztc.services.runtime_detect import TerminalDetection

    detection = TerminalDetection(kind="unsupported", via_ssh=False, raw_marker=None)
    app = TermConfigApp(detection=detection, zellij_installed=True)
    assert app.backend is None
    assert app.backend_path is None
