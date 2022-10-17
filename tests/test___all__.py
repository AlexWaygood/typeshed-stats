"""Test __all__ in __init__.py and all submodules."""

import builtins
import importlib
import pkgutil
import types
from typing import Final

import pytest

import typeshed_stats

ALL_MODULES: Final = [typeshed_stats] + [
    importlib.import_module(f"typeshed_stats.{m.name}")
    for m in pkgutil.iter_modules(typeshed_stats.__path__)
]


@pytest.mark.parametrize("module", ALL_MODULES)
def test___all___alphabetisation(module: types.ModuleType) -> None:
    assert module.__all__ == sorted(module.__all__)


def _is_from_other_module(obj: object) -> bool:
    return getattr(obj, "__module__", "typeshed_stats") != "typeshed_stats"


@pytest.mark.parametrize("module", ALL_MODULES)
def test_all_public_names_in___all__(module: types.ModuleType) -> None:
    """Test that all names not in `__all__` are marked as private."""
    assert set(module.__all__) >= {
        name
        for name, value in vars(module).items()
        if not (
            name.startswith("_")
            or isinstance(value, types.ModuleType)
            or _is_from_other_module(value)
            or name in vars(builtins)
        )
    }


def test___init___imports_everything_public_from_submodules() -> None:
    all_as_set = set(typeshed_stats.__all__)
    submodule_alls_combined = set(sum((mod.__all__ for mod in ALL_MODULES), start=[]))
    assert (
        all_as_set >= submodule_alls_combined
    ), f"Missing names: {submodule_alls_combined - all_as_set!r}"
