"""Test __all__ in __init__.py and all submodules."""

import builtins
import importlib
import pkgutil
import sys
import types
from typing import Final
from unittest import mock

# Make sure not to import rich or markdown here, since they're optional dependencies
# Some tests assert behaviour that's predicated on these modules not yet being imported
import pytest

import typeshed_stats

ALL_SUBMODULES: Final = [
    importlib.import_module(f"typeshed_stats.{m.name}")
    for m in pkgutil.iter_modules(typeshed_stats.__path__)
    if m.name != "_version"
]


@pytest.fixture(params=ALL_SUBMODULES)
def submodule(request: pytest.FixtureRequest) -> types.ModuleType:
    return request.param  # type: ignore[no-any-return]


def test_submodule_has___all__(submodule: types.ModuleType) -> None:
    assert hasattr(submodule, "__all__")


def test_submodule__all___is_valid(submodule: types.ModuleType) -> None:
    assert isinstance(submodule.__all__, list)
    assert all(isinstance(item, str) for item in submodule.__all__)


def test_all_public_names_in___all__(submodule: types.ModuleType) -> None:
    """Test that all names not in `__all__` are marked as private."""
    submodule_name = submodule.__name__

    def is_from_other_module(obj: object) -> bool:
        return getattr(obj, "__module__", submodule_name) != submodule_name

    def is_private_or_imported_symbol(name: str, value: object) -> bool:
        return (
            name.startswith("_")
            or isinstance(value, types.ModuleType)
            or is_from_other_module(value)
            or name in vars(builtins)
        )

    public_names_not_in___all__ = {
        name
        for name, value in vars(submodule).items()
        if (
            name not in submodule.__all__
            and not is_private_or_imported_symbol(name, value)
        )
    }

    assert not public_names_not_in___all__, (
        f"Public names not in __all__: {public_names_not_in___all__!r}"
    )


# ========================================
# Test the package doesn't import on <3.11
# ========================================


@mock.patch.object(sys, "version_info", new=(3, 9, 8, "final", 0))
@pytest.mark.parametrize("module_name", [mod.__name__ for mod in ALL_SUBMODULES])
def test_import_fails_on_less_than_3_point_11(module_name: str) -> None:
    for submod in ALL_SUBMODULES:
        submod_name = submod.__name__
        if submod_name in sys.modules:
            del sys.modules[submod_name]
    with pytest.raises(ImportError, match=r"Python 3\.11\+ is required"):
        importlib.import_module(module_name)
