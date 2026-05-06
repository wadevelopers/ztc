def test_import_package():
    import term_config_tui

    assert term_config_tui.__version__


def test_import_app():
    from term_config_tui.app import TermConfigApp

    app = TermConfigApp()
    assert app.TITLE == "term-config-tui"


def test_default_paths_point_to_home():
    from term_config_tui.models.config import Paths

    p = Paths.default()
    assert "config.kdl" in str(p.zellij_config)
    assert p.zellij_layouts_dir.name == "layouts"


def test_alacritty_detection_resolves_to_alacritty_backend():
    """Si la deteccion devuelve kind='alacritty', el registry resuelve
    AlacrittyBackend automaticamente (sin necesidad de pasarlo)."""
    from term_config_tui.app import TermConfigApp
    from term_config_tui.services.runtime_detect import TerminalDetection
    from term_config_tui.services.terminals.alacritty import AlacrittyBackend

    detection = TerminalDetection(
        kind="alacritty", via_ssh=False, raw_marker="env:ALACRITTY_WINDOW_ID"
    )
    app = TermConfigApp(detection=detection, zellij_installed=True)
    assert isinstance(app.backend, AlacrittyBackend)
    assert app.backend.kind == "alacritty"
    assert "alacritty.toml" in str(app.backend_path)


def test_unsupported_detection_yields_no_backend():
    """Sin terminal soportada, el backend es None y el menu se desactiva."""
    from term_config_tui.app import TermConfigApp
    from term_config_tui.services.runtime_detect import TerminalDetection

    detection = TerminalDetection(kind="unsupported", via_ssh=False, raw_marker=None)
    app = TermConfigApp(detection=detection, zellij_installed=True)
    assert app.backend is None
    assert app.backend_path is None
