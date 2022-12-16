"""Tools for gathering stats about typeshed packages."""

import ast
import asyncio
import json
import os
import re
import sys
import urllib.parse
from collections import Counter
from collections.abc import Collection, Container, Iterable, Iterator, Mapping, Sequence
from contextlib import AsyncExitStack, contextmanager
from enum import Enum
from functools import lru_cache, partial
from itertools import chain
from operator import attrgetter
from pathlib import Path
from typing import Any, Literal, NewType, TypeAlias, TypeVar, final

import aiohttp
import attrs
from packaging.specifiers import SpecifierSet
from packaging.version import Version

if sys.version_info < (3, 10):
    raise ImportError("Python 3.10+ is required!")

if sys.version_info >= (3, 11):
    import tomllib  # pragma: >=3.11 cover
else:
    import tomli as tomllib  # pragma: <3.11 cover


__all__ = [
    "AnnotationStats",
    "FileInfo",
    "PackageInfo",
    "PackageName",
    "PackageStatus",
    "PyrightSetting",
    "StubtestSetting",
    "UploadStatus",
    "gather_annotation_stats_on_file",
    "gather_annotation_stats_on_package",
    "gather_stats_on_file",
    "gather_stats_on_multiple_packages",
    "gather_stats_on_package",
    "get_number_of_lines_of_file",
    "get_package_extra_description",
    "get_package_size",
    "get_package_status",
    "get_pyright_setting_for_package",
    "get_pyright_setting_for_path",
    "get_stubtest_platforms",
    "get_stubtest_setting",
    "get_upload_status",
    "tmpdir_typeshed",
]

PackageName: TypeAlias = str
_AbsolutePath = NewType("_AbsolutePath", Path)
_PathRelativeToTypeshed: TypeAlias = Path
_NiceReprEnumSelf = TypeVar("_NiceReprEnumSelf", bound="_NiceReprEnum")


class _NiceReprEnum(Enum):
    """Base class for several public-API enums in this package."""

    def __new__(cls: type[_NiceReprEnumSelf], doc: str) -> _NiceReprEnumSelf:
        assert isinstance(doc, str)
        member = object.__new__(cls)
        member._value_ = member.__doc__ = doc
        return member

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}.{self.name}"

    @property
    def formatted_name(self) -> str:
        return " ".join(self.name.split("_")).lower()


@attrs.define
class _SingleAnnotationAnalysis:
    Any_in_annotation: bool = False
    Incomplete_in_annotation: bool = False


class _SingleAnnotationAnalyzer(ast.NodeVisitor):
    def __init__(self) -> None:
        self.analysis = _SingleAnnotationAnalysis()

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(analysis={self.analysis})"

    def visit_Name(self, node: ast.Name) -> None:
        match node.id:
            case "Any":
                self.analysis.Any_in_annotation = True
            case "Incomplete":
                self.analysis.Incomplete_in_annotation = True
            case _:
                pass

    def visit_Attribute(self, node: ast.Attribute) -> None:
        value = node.value
        if isinstance(value, ast.Name):
            match f"{value.id}.{node.attr}":
                case "typing.Any":
                    self.analysis.Any_in_annotation = True
                case "_typeshed.Incomplete":
                    self.analysis.Incomplete_in_annotation = True
                case _:
                    pass
        self.generic_visit(node)


def _analyse_annotation(annotation: ast.AST) -> _SingleAnnotationAnalysis:
    analyser = _SingleAnnotationAnalyzer()
    analyser.visit(annotation)
    return analyser.analysis


@final
@attrs.define
class AnnotationStats:
    """Stats on the annotations for a source file or a directory of source files."""

    annotated_parameters: int = 0
    unannotated_parameters: int = 0
    annotated_returns: int = 0
    unannotated_returns: int = 0
    explicit_Incomplete_parameters: int = 0
    explicit_Incomplete_returns: int = 0
    explicit_Any_parameters: int = 0
    explicit_Any_returns: int = 0
    annotated_variables: int = 0
    explicit_Any_variables: int = 0
    explicit_Incomplete_variables: int = 0


def _node_matches_name(node: ast.expr, name: str, from_: Container[str]) -> bool:
    """Return True if `node` represents `name` from one of the modules in `from_`.

    >>> _is_TypeAlias = partial(_node_matches_name, name="TypeAlias", from_={"typing", "typing_extensions"})
    >>> get_annotation_node = lambda source: ast.parse(source).body[0].annotation
    >>> _is_TypeAlias(get_annotation_node("foo: TypeAlias = int"))
    True
    >>> _is_TypeAlias(get_annotation_node("foo: typing.TypeAlias = int"))
    True
    >>> _is_TypeAlias(get_annotation_node("foo: typing_extensions.TypeAlias = int"))
    True
    >>> _is_TypeAlias(get_annotation_node("foo: int"))
    False
    >>> _is_TypeAlias(get_annotation_node("foo: Final = 5"))
    False
    """
    match node:
        case ast.Name(id):
            return id == name
        case ast.Attribute(ast.Name(module), id):
            return id == name and module in from_
        case _:
            return False


_is_staticmethod = partial(_node_matches_name, name="staticmethod", from_={"builtins"})
_is_TypeAlias = partial(
    _node_matches_name, name="TypeAlias", from_={"typing", "typing_extensions"}
)


class _AnnotationStatsCollector(ast.NodeVisitor):
    """AST Visitor for collecting stats on a single stub file."""

    def __init__(self) -> None:
        self.stats = AnnotationStats()
        self._class_nesting = 0

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(stats={self.stats})"

    @property
    def in_class(self) -> bool:
        """Return `True` if we're currently visiting a class definition."""
        return bool(self._class_nesting)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._class_nesting += 1
        self.generic_visit(node)
        self._class_nesting -= 1

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self.generic_visit(node)
        annotation = node.annotation
        if _is_TypeAlias(annotation):
            return
        self.stats.annotated_variables += 1
        analysis = _analyse_annotation(annotation)
        if analysis.Any_in_annotation:
            self.stats.explicit_Any_variables += 1
        if analysis.Incomplete_in_annotation:
            self.stats.explicit_Incomplete_variables += 1

    def _visit_arg(self, node: ast.arg) -> None:
        annotation = node.annotation
        if annotation is None:
            self.stats.unannotated_parameters += 1
        else:
            self.stats.annotated_parameters += 1
            analysis = _analyse_annotation(annotation)
            if analysis.Any_in_annotation:
                self.stats.explicit_Any_parameters += 1
            if analysis.Incomplete_in_annotation:
                self.stats.explicit_Incomplete_parameters += 1

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self.generic_visit(node)
        returns = node.returns
        if returns is None:
            self.stats.unannotated_returns += 1
        else:
            self.stats.annotated_returns += 1
            analysis = _analyse_annotation(returns)
            if analysis.Any_in_annotation:
                self.stats.explicit_Any_returns += 1
            if analysis.Incomplete_in_annotation:
                self.stats.explicit_Incomplete_returns += 1

        args = node.args

        for i, arg_node in enumerate(chain(args.posonlyargs, args.args)):
            if (
                i == 0
                and self.in_class
                and not any(
                    _is_staticmethod(decorator) for decorator in node.decorator_list
                )
            ):
                # We don't want self/cls/metacls/mcls arguments to count towards the statistics
                # Whatever they're called, they can easily be inferred
                continue
            self._visit_arg(arg_node)

        for arg_node in args.kwonlyargs:
            self._visit_arg(arg_node)

        for arg_node in filter(None, (args.vararg, args.kwarg)):
            self._visit_arg(arg_node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)


def gather_annotation_stats_on_file(path: Path | str) -> AnnotationStats:
    """Gather annotation stats on a single typeshed stub file.

    Args:
        path: The location of the file to be analysed.

    Returns:
        An [`AnnotationStats`][typeshed_stats.gather.AnnotationStats] object
            containing data about the annotations in the file.

    Examples:
        >>> from typeshed_stats.gather import tmpdir_typeshed, gather_annotation_stats_on_file
        >>> with tmpdir_typeshed() as typeshed:
        ...     stats_on_functools = gather_annotation_stats_on_file(typeshed / "stdlib" / "functools.pyi")
        ...
        >>> type(stats_on_functools)
        <class 'typeshed_stats.gather.AnnotationStats'>
        >>> stats_on_functools.unannotated_parameters
        0
    """
    visitor = _AnnotationStatsCollector()
    with open(path, encoding="utf-8") as file:
        visitor.visit(ast.parse(file.read()))
    return visitor.stats


@lru_cache
def _get_package_directory(package_name: PackageName, typeshed_dir: Path | str) -> Path:
    if package_name == "stdlib":
        return Path(typeshed_dir, "stdlib")
    return Path(typeshed_dir, "stubs", package_name)


def gather_annotation_stats_on_package(
    package_name: PackageName, *, typeshed_dir: Path | str
) -> AnnotationStats:
    """Aggregate annotation stats on a typeshed stubs package.

    Args:
        package_name: The name of the stubs package to analyze.
        typeshed_dir: A path pointing to the location of a typeshed directory
            in which to find the stubs package source.

    Returns:
        An [`AnnotationStats`][typeshed_stats.gather.AnnotationStats] object
            containing data about the annotations in the package.

    Examples:
        >>> from typeshed_stats.gather import tmpdir_typeshed, gather_annotation_stats_on_package
        >>> with tmpdir_typeshed() as typeshed:
        ...     mypy_extensions_stats = gather_annotation_stats_on_package("mypy-extensions", typeshed_dir=typeshed)
        ...
        >>> type(mypy_extensions_stats)
        <class 'typeshed_stats.gather.AnnotationStats'>
        >>> mypy_extensions_stats.unannotated_parameters
        0
    """
    combined: Counter[str] = Counter()
    annot_stats_fields = AnnotationStats.__annotations__
    for path in _get_package_directory(package_name, typeshed_dir).rglob("*.pyi"):
        file_stats = gather_annotation_stats_on_file(path)
        for field in annot_stats_fields:
            combined[field] += getattr(file_stats, field)
    return AnnotationStats(**combined)


@lru_cache
def _get_package_metadata(
    package_name: PackageName, typeshed_dir: Path | str
) -> Mapping[str, Any]:
    package_directory = _get_package_directory(package_name, typeshed_dir)
    with open(package_directory / "METADATA.toml", "rb") as f:
        return tomllib.load(f)


def get_package_extra_description(
    package_name: PackageName, *, typeshed_dir: Path | str
) -> str | None:
    """Get the "extra description" of the package given in the METADATA.toml file.

    Args:
        package_name: The name of the package to find the extra description for.
        typeshed_dir: A path pointing to a typeshed directory,
            from which to retrieve the description.

    Returns:
        The "extra description" of the package given in the METADATA.toml file,
            if one is given, else `None`.

    Examples:
        >>> from typeshed_stats.gather import tmpdir_typeshed, get_package_extra_description
        >>> with tmpdir_typeshed() as typeshed:
        ...     stdlib_description = get_package_extra_description("stdlib", typeshed_dir=typeshed)
        ...     protobuf_description = get_package_extra_description("protobuf", typeshed_dir=typeshed)
        >>> stdlib_description is None
        True
        >>> isinstance(protobuf_description, str)
        True
    """
    if package_name == "stdlib":
        return None
    return _get_package_metadata(package_name, typeshed_dir).get("extra_description")


class StubtestSetting(_NiceReprEnum):
    """Enumeration of the various possible settings typeshed uses for stubtest in CI."""

    SKIPPED = "Stubtest is skipped in CI for this package."
    MISSING_STUBS_IGNORED = (
        "The `--ignore-missing-stub` stubtest setting is used in CI."
    )
    ERROR_ON_MISSING_STUB = (
        "Objects missing from the stub cause stubtest to emit an error in CI."
    )


@lru_cache
def _get_stubtest_config(
    package_name: PackageName, typeshed_dir: Path | str
) -> Mapping[str, object]:
    metadata = _get_package_metadata(package_name, typeshed_dir)
    config = metadata.get("tool", {}).get("stubtest", {})
    assert isinstance(config, dict)
    return config


def get_stubtest_setting(
    package_name: PackageName, *, typeshed_dir: Path | str
) -> StubtestSetting:
    """Get the setting typeshed uses in CI when stubtest is run on a certain package.

    Args:
        package_name: The name of the package to find the stubtest setting for.
        typeshed_dir: A path pointing to a typeshed directory,
            from which to retrieve the stubtest setting.

    Returns:
        A member of the [`StubtestSetting`][typeshed_stats.gather.StubtestSetting]
            enumeration (see the docs on `StubtestSetting` for details).

    Examples:
        >>> from typeshed_stats.gather import tmpdir_typeshed, get_stubtest_setting
        >>> with tmpdir_typeshed() as typeshed:
        ...     stdlib_setting = get_stubtest_setting("stdlib", typeshed_dir=typeshed)
        ...     gdb_setting = get_stubtest_setting("gdb", typeshed_dir=typeshed)
        >>> stdlib_setting
        StubtestSetting.ERROR_ON_MISSING_STUB
        >>> help(_)
        Help on StubtestSetting in module typeshed_stats.gather:
        <BLANKLINE>
        StubtestSetting.ERROR_ON_MISSING_STUB
            Objects missing from the stub cause stubtest to emit an error in CI.
        <BLANKLINE>
        >>> gdb_setting
        StubtestSetting.SKIPPED
    """
    if package_name == "stdlib":
        return StubtestSetting.ERROR_ON_MISSING_STUB
    match _get_stubtest_config(package_name, typeshed_dir):
        case {"skip": True}:
            return StubtestSetting.SKIPPED
        case {"ignore_missing_stub": False}:
            return StubtestSetting.ERROR_ON_MISSING_STUB
        case _:
            return StubtestSetting.MISSING_STUBS_IGNORED


def get_stubtest_platforms(
    package_name: PackageName, *, typeshed_dir: Path | str
) -> list[str]:
    """Get the list of platforms on which stubtest is run in typeshed's CI.

    Args:
        package_name: The name of the package to find the stubtest setting for.
        typeshed_dir: A path pointing to a typeshed directory,
            from which to retrieve the stubtest configuration.

    Returns:
        A list of strings describing platforms stubtest is run on.

    Examples:
        >>> from typeshed_stats.gather import tmpdir_typeshed, get_stubtest_platforms
        >>> with tmpdir_typeshed() as typeshed:
        ...     pywin_platforms = get_stubtest_platforms("pywin32", typeshed_dir=typeshed)
        >>> pywin_platforms
        ['win32']
    """
    if package_name == "stdlib":
        return ["linux", "darwin", "win32"]
    match _get_stubtest_config(package_name, typeshed_dir):
        case {"skip": True}:
            return []
        case {"platforms": list() as platforms}:
            return platforms
        case _:
            return ["linux"]


class PackageStatus(_NiceReprEnum):
    """The various states of freshness/staleness a stubs package can be in."""

    STDLIB = (
        "These are the stdlib stubs. Typeshed's stdlib stubs are generally fairly"
        " up to date, and tested against all currently supported Python versions"
        " in CI."
    )
    NOT_ON_PYPI = (
        "The upstream for this package doesn't exist on PyPI,"
        " so whether or not these stubs are up to date or not is unknown."
    )
    OBSOLETE = "Upstream has added type hints; these typeshed stubs are now obsolete."
    NO_LONGER_UPDATED = (
        "Upstream has not added type hints,"
        " but these stubs are no longer updated for some other reason."
    )
    OUT_OF_DATE = (
        "These stubs are out of date. In CI, stubtest tests these stubs against an"
        " older version of this package than the latest that's available."
    )
    UP_TO_DATE = (
        "These stubs should be fairly up to date. In CI, stubtest tests these stubs"
        " against the latest version of the package that's available."
    )


async def _get_pypi_data(
    package_name: str, session: aiohttp.ClientSession | None
) -> dict[str, Any]:
    pypi_data_url = f"https://pypi.org/pypi/{urllib.parse.quote(package_name)}/json"
    async with AsyncExitStack() as stack:
        if session is None:
            # see https://github.com/python/mypy/issues/13936
            # for why we need the tmp_var to keep mypy happy
            tmp_var = await stack.enter_async_context(aiohttp.ClientSession())
            session = tmp_var
        async with session.get(pypi_data_url) as response:
            response.raise_for_status()
            response_json = await response.json()
    assert isinstance(response_json, dict)
    return response_json


async def get_package_status(
    package_name: str,
    *,
    typeshed_dir: Path | str,
    session: aiohttp.ClientSession | None = None,
) -> PackageStatus:
    """Retrieve information on how up to date a stubs package is.

    If stubtest tests these stubs against the latest version of the runtime
    in typeshed's CI, it's a fair bet that the stubs are relatively up to date.
    If stubtest tests these stubs against an older version, however,
    the stubs may be out of date.

    This function makes network requests to PyPI in order to determine what the
    latest version of the runtime is, and then compares this against
    the metadata of the stubs package.

    Args:
        package_name: The name of the stubs package to analyze.
        typeshed_dir: A path pointing to a typeshed directory
            in which to find the stubs package.
        session (optional): An `aiohttp.ClientSession` instance, to be used
            for making a network requests, or `None`. If `None` is provided
            for this argument, a new `aiohttp.ClientSession` instance will be
            created to make the network request.

    Returns:
        A member of the [`PackageStatus`][typeshed_stats.gather.PackageStatus]
            enumeration (see the docs on `PackageStatus` for details).

    Examples:
        >>> import asyncio
        >>> from typeshed_stats.gather import tmpdir_typeshed, get_package_status
        >>> with tmpdir_typeshed() as typeshed:
        ...     stdlib_status = asyncio.run(get_package_status("stdlib", typeshed_dir=typeshed))
        ...     gdb_status = asyncio.run(get_package_status("gdb", typeshed_dir=typeshed))
        ...
        >>> stdlib_status
        PackageStatus.STDLIB
        >>> help(_)
        Help on PackageStatus in module typeshed_stats.gather:
        <BLANKLINE>
        PackageStatus.STDLIB
            These are the stdlib stubs. Typeshed's stdlib stubs are generally fairly up to date, and tested against all currently supported Python versions in CI.
        <BLANKLINE>
        >>> gdb_status
        PackageStatus.NOT_ON_PYPI
    """
    match package_name:
        case "stdlib":
            return PackageStatus.STDLIB
        case "gdb":
            return PackageStatus.NOT_ON_PYPI
        case _:
            pass

    match metadata := _get_package_metadata(package_name, typeshed_dir):
        case {"obsolete_since": _}:
            return PackageStatus.OBSOLETE
        case {"no_longer_updated": True}:
            return PackageStatus.NO_LONGER_UPDATED
        case _:
            pass

    typeshed_pinned_version = SpecifierSet(f"=={metadata['version']}")
    pypi_data = await _get_pypi_data(package_name, session)
    pypi_version = Version(pypi_data["info"]["version"])
    status = "UP_TO_DATE" if pypi_version in typeshed_pinned_version else "OUT_OF_DATE"
    return PackageStatus[status]


class UploadStatus(_NiceReprEnum):
    """Whether or not a stubs package is currently uploaded to PyPI."""

    UPLOADED = "These stubs are currently uploaded to PyPI."
    NOT_CURRENTLY_UPLOADED = "These stubs are not currently uploaded to PyPI."


def get_upload_status(
    package_name: PackageName, *, typeshed_dir: Path | str
) -> UploadStatus:
    """Determine whether a certain package is currently uploaded to PyPI.

    Args:
        package_name: The name of the package to find the stubtest setting for.
        typeshed_dir: A path pointing to a typeshed directory,
            from which to retrieve the stubtest setting.

    Returns:
        A member of the [`UploadStatus`][typeshed_stats.gather.UploadStatus]
            enumeration (see the docs on `UploadStatus` for details).

    Examples:
        >>> from typeshed_stats.gather import tmpdir_typeshed, get_upload_status
        >>> with tmpdir_typeshed() as typeshed:
        ...     stdlib_setting = get_upload_status("stdlib", typeshed_dir=typeshed)
        ...     requests_setting = get_upload_status("requests", typeshed_dir=typeshed)
        >>> stdlib_setting
        UploadStatus.NOT_CURRENTLY_UPLOADED
        >>> help(_)
        Help on UploadStatus in module typeshed_stats.gather:
        <BLANKLINE>
        UploadStatus.NOT_CURRENTLY_UPLOADED
            These stubs are not currently uploaded to PyPI.
        <BLANKLINE>
        >>> requests_setting
        UploadStatus.UPLOADED
    """
    if package_name == "stdlib":
        return UploadStatus.NOT_CURRENTLY_UPLOADED
    match _get_package_metadata(package_name, typeshed_dir):
        case {"upload": False}:
            return UploadStatus.NOT_CURRENTLY_UPLOADED
        case _:
            return UploadStatus.UPLOADED


def get_number_of_lines_of_file(file_path: Path | str) -> int:
    """Get the total number of lines of code for a single stubs file in typeshed.

    Args:
        file_path: A path to the file to analyse.

    Returns:
        The number of lines of code the stubs file contains,
            excluding empty lines.
    """
    with open(file_path, encoding="utf-8") as file:
        return sum(1 for line in file if line.strip())


def get_package_size(package_name: PackageName, *, typeshed_dir: Path | str) -> int:
    """Get the total number of lines of code for a stubs package in typeshed.

    Args:
        package_name: The name of the stubs package to find the line number for.
        typeshed_dir: A path pointing to a typeshed directory
            in which to find the stubs package.

    Returns:
        The number of lines of code the stubs package contains,
            excluding empty lines.

    Examples:
        >>> from typeshed_stats.gather import tmpdir_typeshed, get_package_size
        >>> with tmpdir_typeshed() as typeshed:
        ...     mypy_extensions_size = get_package_size("mypy-extensions", typeshed_dir=typeshed)
        ...
        >>> type(mypy_extensions_size) is int and mypy_extensions_size > 0
        True
    """
    return sum(
        get_number_of_lines_of_file(file)
        for file in _get_package_directory(package_name, typeshed_dir).rglob("*.pyi")
    )


@lru_cache
def _get_pyright_excludelist(
    *,
    typeshed_dir: Path | str,
    config_filename: Literal["pyrightconfig.json", "pyrightconfig.stricter.json"],
) -> frozenset[Path]:
    # Read the config file;
    # do some pre-processing so that it can be passed to json.loads()
    config_path = Path(typeshed_dir, config_filename)
    with config_path.open(encoding="utf-8") as file:
        # strip comments from the file
        lines = [line for line in file if not line.strip().startswith("//")]
    # strip trailing commas from the file
    valid_json = re.sub(r",(\s*?[\}\]])", r"\1", "\n".join(lines))
    pyright_config = json.loads(valid_json)
    assert isinstance(pyright_config, dict)
    excludelist = pyright_config.get("exclude", [])
    return frozenset(Path(typeshed_dir, item) for item in excludelist)


class PyrightSetting(_NiceReprEnum):
    """The various possible pyright settings typeshed uses in CI."""

    ENTIRELY_EXCLUDED = "All files are excluded from the pyright check in CI."
    SOME_FILES_EXCLUDED = "Some files are excluded from the pyright check in CI."
    NOT_STRICT = "All files are excluded from the stricter pyright settings in CI."
    STRICT_ON_SOME_FILES = (
        "Some files are tested with the stricter pyright settings in CI;"
        " some are excluded."
    )
    STRICT = "All files are tested with the stricter pyright settings in CI."


def _path_or_path_ancestor_is_listed(path: Path, path_list: Collection[Path]) -> bool:
    return path in path_list or any(
        listed_path in path.parents for listed_path in path_list
    )


def _child_of_path_is_listed(path: Path, path_list: Collection[Path]) -> bool:
    return any(path in listed_path.parents for listed_path in path_list)


def get_pyright_setting_for_path(
    file_path: Path | str, *, typeshed_dir: Path | str
) -> PyrightSetting:
    """Get the settings typeshed uses in CI when pyright is run on a certain path.

    Args:
        file_path: The path to query.
        typeshed_dir: A path pointing to a typeshed directory,
            from which to retrieve the pyright setting.

    Returns:
        A member of the [`PyrightSetting`][typeshed_stats.gather.PyrightSetting]
            enumeration (see the docs on `PyrightSetting` for details).
    """
    entirely_excluded_paths = _get_pyright_excludelist(
        typeshed_dir=typeshed_dir, config_filename="pyrightconfig.json"
    )
    paths_excluded_from_stricter_check = _get_pyright_excludelist(
        typeshed_dir=typeshed_dir, config_filename="pyrightconfig.stricter.json"
    )
    file_path = file_path if isinstance(file_path, Path) else Path(file_path)

    if _path_or_path_ancestor_is_listed(file_path, entirely_excluded_paths):
        return PyrightSetting.ENTIRELY_EXCLUDED
    if _child_of_path_is_listed(file_path, entirely_excluded_paths):
        return PyrightSetting.SOME_FILES_EXCLUDED
    if _path_or_path_ancestor_is_listed(file_path, paths_excluded_from_stricter_check):
        return PyrightSetting.NOT_STRICT
    if _child_of_path_is_listed(file_path, paths_excluded_from_stricter_check):
        return PyrightSetting.STRICT_ON_SOME_FILES
    return PyrightSetting.STRICT


def get_pyright_setting_for_package(
    package_name: PackageName, *, typeshed_dir: Path | str
) -> PyrightSetting:
    """Get the settings typeshed uses in CI when pyright is run on a certain package.

    Args:
        package_name: The name of the package to find the stubtest setting for.
        typeshed_dir: A path pointing to a typeshed directory,
            from which to retrieve the pyright setting.

    Returns:
        A member of the [`PyrightSetting`][typeshed_stats.gather.PyrightSetting]
            enumeration (see the docs on `PyrightSetting` for details).

    Examples:
        >>> from typeshed_stats.gather import tmpdir_typeshed, get_pyright_setting_for_package
        >>> with tmpdir_typeshed() as typeshed:
        ...     stdlib_setting = get_pyright_setting_for_package("stdlib", typeshed_dir=typeshed)
        ...
        >>> stdlib_setting
        PyrightSetting.STRICT_ON_SOME_FILES
        >>> help(_)
        Help on PyrightSetting in module typeshed_stats.gather:
        <BLANKLINE>
        PyrightSetting.STRICT_ON_SOME_FILES
            Some files are tested with the stricter pyright settings in CI; some are excluded.
        <BLANKLINE>
    """
    return get_pyright_setting_for_path(
        file_path=_get_package_directory(package_name, typeshed_dir),
        typeshed_dir=typeshed_dir,
    )


@final
@attrs.define
class PackageInfo:
    """Statistics about a single stubs package in typeshed."""

    package_name: PackageName
    extra_description: str | None
    number_of_lines: int
    package_status: PackageStatus
    upload_status: UploadStatus
    stubtest_setting: StubtestSetting
    stubtest_platforms: list[str]
    pyright_setting: PyrightSetting
    annotation_stats: AnnotationStats


async def gather_stats_on_package(
    package_name: PackageName,
    *,
    typeshed_dir: Path | str,
    session: aiohttp.ClientSession | None = None,
) -> PackageInfo:
    """Gather miscellaneous statistics about a single stubs package in typeshed.

    This function calls
    [`get_package_status()`][typeshed_stats.gather.get_package_status],
    which makes network requests to PyPI.
    See the docs on `get_package_status()` for details.

    Args:
        package_name: The name of the package to gather statistics on.
        typeshed_dir: A path pointing to a typeshed directory,
            in which the source code for the stubs package can be found.
        session (optional): An `aiohttp.ClientSession` instance, to be used
            for making a network requests, or `None`. If `None` is provided
            for this argument, a new `aiohttp.ClientSession` instance will be
            created to make the network request.

    Returns:
        An instance of the [`PackageInfo`][typeshed_stats.gather.PackageInfo] class.

    Examples:
        >>> import asyncio
        >>> from typeshed_stats.gather import tmpdir_typeshed, gather_stats_on_package
        >>> with tmpdir_typeshed() as typeshed:
        ...     stdlib_info = asyncio.run(gather_stats_on_package("stdlib", typeshed_dir=typeshed))
        ...
        >>> stdlib_info.package_name
        'stdlib'
        >>> stdlib_info.stubtest_setting
        StubtestSetting.ERROR_ON_MISSING_STUB
        >>> type(stdlib_info.number_of_lines) is int and stdlib_info.number_of_lines > 0
        True
    """
    return PackageInfo(
        package_name=package_name,
        extra_description=get_package_extra_description(
            package_name, typeshed_dir=typeshed_dir
        ),
        number_of_lines=get_package_size(package_name, typeshed_dir=typeshed_dir),
        package_status=await get_package_status(
            package_name, typeshed_dir=typeshed_dir, session=session
        ),
        upload_status=get_upload_status(package_name, typeshed_dir=typeshed_dir),
        stubtest_setting=get_stubtest_setting(package_name, typeshed_dir=typeshed_dir),
        stubtest_platforms=get_stubtest_platforms(
            package_name, typeshed_dir=typeshed_dir
        ),
        pyright_setting=get_pyright_setting_for_package(
            package_name, typeshed_dir=typeshed_dir
        ),
        annotation_stats=gather_annotation_stats_on_package(
            package_name, typeshed_dir=typeshed_dir
        ),
    )


@final
@attrs.define
class FileInfo:
    """Statistics about a single .pyi file in typeshed."""

    file_path: _PathRelativeToTypeshed
    parent_package: PackageName
    number_of_lines: int
    pyright_setting: PyrightSetting
    annotation_stats: AnnotationStats


@lru_cache
def _normalize_typeshed_dir(typeshed_dir: Path | str) -> _AbsolutePath:
    if isinstance(typeshed_dir, str):
        typeshed_dir = Path(typeshed_dir)
    elif not isinstance(typeshed_dir, Path):
        raise TypeError(
            "Expected str or Path argument for typeshed_dir, got"
            f" {typeshed_dir.__class__.__name__!r}"
        )
    if not typeshed_dir.exists():
        raise ValueError(f"{typeshed_dir} does not exist!")
    if not typeshed_dir.is_dir():
        raise ValueError(f"{typeshed_dir} is not a directory!")
    return _AbsolutePath(typeshed_dir.absolute())


@lru_cache
def _normalize_file_path(
    file_path: Path | str, typeshed_dir: _AbsolutePath
) -> _AbsolutePath:
    orig_file_path = file_path
    if isinstance(file_path, str):
        file_path = Path(file_path)
    elif not isinstance(file_path, Path):
        raise TypeError(
            "Expected str or Path argument for file_path, got"
            f" {file_path.__class__.__name__!r}"
        )
    if typeshed_dir in file_path.absolute().parents:
        file_path = _AbsolutePath(file_path.absolute())
    else:
        file_path = _AbsolutePath(typeshed_dir / file_path)
    if not file_path.exists():
        raise ValueError(
            f"'{orig_file_path}' does not exist as an absolute path or as a path"
            " relative to typeshed"
        )
    if not file_path.is_file():
        raise ValueError(f"'{orig_file_path}' exists, but does not point to a file")
    file_path_suffix = file_path.suffix
    if file_path_suffix != ".pyi":
        raise ValueError(
            f"Expected a path pointing to a .pyi file, got a {file_path_suffix!r} file"
        )
    return file_path


def _get_parent_package(
    file_path: _AbsolutePath, typeshed_dir: _AbsolutePath
) -> PackageName:
    if (typeshed_dir / "stdlib") in file_path.parents:
        return "stdlib"
    parent_path = next(  # pragma: no branch
        path for path in (typeshed_dir / "stubs").iterdir() if path in file_path.parents
    )
    return parent_path.parts[-1]


def gather_stats_on_file(
    file_path: Path | str, *, typeshed_dir: Path | str
) -> FileInfo:
    """Gather stats on a single `.pyi` file in typeshed.

    Args:
        file_path: A path pointing to the file on which to gather stats.
            This can be an absolute path,
            or a path relative to the `typeshed_dir` argument.
        typeshed_dir: A path pointing to the overall typeshed directory.
            This can be an absolute or relative path.

    Returns:
        An instance of the [`FileInfo`][typeshed_stats.gather.FileInfo] class.

    Examples:
        >>> from typeshed_stats.gather import tmpdir_typeshed, gather_stats_on_file
        >>> with tmpdir_typeshed() as typeshed:
        ...     # Paths can be relative to typeshed_dir
        ...     functools_info = gather_stats_on_file(
        ...         "stdlib/functools.pyi", typeshed_dir=typeshed
        ...     )
        ...     # Absolute paths are also fine
        ...     stubs_dir = typeshed / "stubs"
        ...     requests_api_info = gather_stats_on_file(
        ...         stubs_dir / "requests/requests/api.pyi", typeshed_dir=typeshed
        ...     )
        ...     # Gather per-file stats on a directory
        ...     markdown_per_file_stats = [
        ...         gather_stats_on_file(module, typeshed_dir=typeshed)
        ...         for module in (stubs_dir / "Markdown").rglob("*.pyi")
        ...     ]
        >>> type(functools_info)
        <class 'typeshed_stats.gather.FileInfo'>
        >>> functools_info.parent_package
        'stdlib'
        >>> functools_info.file_path.as_posix()
        'stdlib/functools.pyi'
        >>> requests_api_info.parent_package
        'requests'
        >>> requests_api_info.file_path.as_posix()
        'stubs/requests/requests/api.pyi'
    """
    typeshed_dir = _normalize_typeshed_dir(typeshed_dir)
    file_path = _normalize_file_path(file_path, typeshed_dir)
    return FileInfo(
        file_path=Path(file_path).relative_to(typeshed_dir),
        parent_package=_get_parent_package(file_path, typeshed_dir),
        number_of_lines=get_number_of_lines_of_file(file_path),
        pyright_setting=get_pyright_setting_for_path(
            file_path, typeshed_dir=typeshed_dir
        ),
        annotation_stats=gather_annotation_stats_on_file(file_path),
    )


async def _gather_stats_on_multiple_packages(
    packages: Iterable[str], *, typeshed_dir: Path | str
) -> Sequence[PackageInfo]:
    conn = aiohttp.TCPConnector(limit_per_host=10)
    async with aiohttp.ClientSession(connector=conn) as session:
        tasks = (
            gather_stats_on_package(
                package_name, typeshed_dir=typeshed_dir, session=session
            )
            for package_name in packages
        )
        return await asyncio.gather(*tasks, return_exceptions=True)


def gather_stats_on_multiple_packages(
    packages: Iterable[str] | None = None, *, typeshed_dir: Path | str
) -> Sequence[PackageInfo]:
    """Concurrently gather statistics on multiple packages.

    Note: this function calls `asyncio.run()` to start an asyncio event loop.
    It is therefore not suitable to be called from inside functions
    that are themselves called as part of an asyncio event loop.

    Args:
        packages: An iterable of package names to be analysed, or None.
            If `None`, defaults to all third-party stubs, plus the stubs for the stdlib.
        typeshed_dir: The path to a local clone of typeshed.

    Returns:
        A sequence of [`PackageInfo`][typeshed_stats.gather.PackageInfo] objects.
            Each `PackageInfo` object contains information representing an analysis
            of a certain stubs package in typeshed.

    Examples:
        >>> from typeshed_stats.gather import PackageInfo, tmpdir_typeshed, gather_stats_on_multiple_packages
        >>> with tmpdir_typeshed() as typeshed:
        ...     infos = gather_stats_on_multiple_packages(
        ...         ["stdlib", "aiofiles", "boto"], typeshed_dir=typeshed
        ...     )
        ...
        >>> [info.package_name for info in infos]
        ['aiofiles', 'boto', 'stdlib']
        >>> all(type(info) is PackageInfo for info in infos)
        True
    """
    if packages is None:
        packages = os.listdir(Path(typeshed_dir, "stubs")) + ["stdlib"]
    results = asyncio.run(
        _gather_stats_on_multiple_packages(packages, typeshed_dir=typeshed_dir)
    )
    for result in results:
        if isinstance(result, BaseException):
            raise result
    return sorted(results, key=attrgetter("package_name"))


@contextmanager
def tmpdir_typeshed() -> Iterator[Path]:
    """Clone typeshed into a tempdir, then yield a `pathlib.Path` pointing to it.

    A context manager.
    """
    import subprocess
    from tempfile import TemporaryDirectory

    args = [
        "git",
        "clone",
        "https://github.com/python/typeshed",
        "--depth",
        "1",
        "--quiet",
    ]

    with TemporaryDirectory() as td:
        args.append(td)
        subprocess.run(args, check=True)
        yield Path(td)
