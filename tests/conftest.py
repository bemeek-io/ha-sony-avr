"""Test configuration.

``sony.py``, ``const.py`` and ``ircc_codes.py`` are intentionally free of Home
Assistant imports so the protocol layer can be tested without installing HA.
They use relative imports, though, so they need a package to live in -- and
importing the real ``custom_components.sony_avr`` package would execute its
``__init__``, which does pull in HA.

So we build a synthetic package containing only the HA-free modules.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

_COMPONENT = Path(__file__).parent.parent / "custom_components" / "sony_avr"
_PKG = "sony_avr_protocol"

# HA-free modules, in dependency order.
_MODULES = ("const", "ircc_codes", "sony")


def _install_package() -> None:
    """Expose the HA-free modules under a synthetic package name."""
    if _PKG in sys.modules:
        return

    package = types.ModuleType(_PKG)
    package.__path__ = [str(_COMPONENT)]
    sys.modules[_PKG] = package

    for name in _MODULES:
        qualified = f"{_PKG}.{name}"
        spec = importlib.util.spec_from_file_location(
            qualified, _COMPONENT / f"{name}.py"
        )
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        sys.modules[qualified] = module
        spec.loader.exec_module(module)
        setattr(package, name, module)


_install_package()
