from __future__ import annotations

import shutil

import pytest

from ztc.services import zellij_config


@pytest.mark.skipif(shutil.which("zellij") is None, reason="zellij no instalado")
def test_zellij_setup_check_returns_tuple() -> None:
    ok, output = zellij_config.zellij_setup_check()
    assert isinstance(ok, bool)
    assert isinstance(output, str)
