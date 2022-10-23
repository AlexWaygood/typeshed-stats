"""Test __all__ in __init__.py and all submodules."""

import builtins
import importlib
import pkgutil
import sys
import types
from typing import Final
from unittest import mock

import pytest

import typeshed_stats

ALL_SUBMODULES: Final = [
    importlib.import_module(f"typeshed_stats.{m.name}")
    for m in pkgutil.iter_modules(typeshed_stats.__path__)
]


@pytest.mark.parametrize("module", ALL_SUBMODULES)
def test_module_has___all__(module: types.ModuleType) -> None:
    assert hasattr(module, "__all__")


@pytest.mark.parametrize("module", ALL_SUBMODULES)
def test_module__all___is_valid(module: types.ModuleType) -> None:
    assert isinstance(module.__all__, list)
    assert all(isinstance(item, str) for item in module.__all__)


@pytest.mark.parametrize("module", ALL_SUBMODULES)
def test___all___alphabetisation(module: types.ModuleType) -> None:
    assert module.__all__ == sorted(module.__all__)


@pytest.mark.parametrize("module", ALL_SUBMODULES)
def test_all_public_names_in___all__(module: types.ModuleType) -> None:
    """Test that all names not in `__all__` are marked as private."""

    def is_from_other_module(obj: object) -> bool:
        return getattr(obj, "__module__", "typeshed_stats") != "typeshed_stats"

    def is_private_or_imported_symbol(name: str, value: object) -> bool:
        return (
            name.startswith("_")
            or isinstance(value, types.ModuleType)
            or is_from_other_module(value)
            or name in vars(builtins)
        )

    public_names_not_in___all__ = {
        name
        for name, value in vars(module).items()
        if (
            name not in module.__all__
            and not is_private_or_imported_symbol(name, value)
        )
    }

    assert (
        not public_names_not_in___all__
    ), f"Public names not in __all__: {public_names_not_in___all__!r}"


# ========================================
# Test the package doesn't import on <3.10
# ========================================


@mock.patch.object(sys, "version_info", new=(3, 9, 8, "final", 0))
@pytest.mark.parametrize("module_name", [mod.__name__ for mod in ALL_SUBMODULES])
def test_import_fails_on_less_than_3_point_10(module_name: str) -> None:
    for module_name in ("typeshed_stats.serialize", "typeshed_stats.gather"):
        if module_name in sys.modules:
            del sys.modules[module_name]
    with pytest.raises(ImportError, match=r"Python 3\.10\+ is required"):
        importlib.import_module(module_name)
