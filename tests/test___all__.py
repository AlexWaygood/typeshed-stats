"""Test __all__ in __init__.py and all submodules."""

import builtins
import importlib
import pkgutil
import types
from itertools import chain
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


@pytest.mark.parametrize("module", ALL_MODULES)
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

    if public_names_not_in___all__:
        pytest.fail(f"Public names not in __all__: {public_names_not_in___all__!r}")


def test___init___imports_everything_public_from_submodules() -> None:
    submodule_alls_combined = chain.from_iterable(mod.__all__ for mod in ALL_MODULES)
    names_not_imported_in___init__ = {
        name for name in submodule_alls_combined if name not in typeshed_stats.__all__
    }
    if names_not_imported_in___init__:
        pytest.fail(
            f"Names not imported in __init__.py: {names_not_imported_in___init__!r}"
        )
