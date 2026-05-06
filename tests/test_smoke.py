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


def test_default_backend_is_alacritty():
    from term_config_tui.app import TermConfigApp
    from term_config_tui.services.terminals.alacritty import AlacrittyBackend

    app = TermConfigApp()
    assert isinstance(app.backend, AlacrittyBackend)
    assert app.backend.kind == "alacritty"
    assert "alacritty.toml" in str(app.backend_path)
