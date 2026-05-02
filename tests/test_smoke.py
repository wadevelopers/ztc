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
    assert "alacritty.toml" in str(p.alacritty_config)
    assert "config.kdl" in str(p.zellij_config)
    assert p.zellij_layouts_dir.name == "layouts"
