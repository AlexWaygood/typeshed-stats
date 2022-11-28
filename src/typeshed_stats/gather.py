"""Tools for gathering stats about typeshed packages."""

import ast
import asyncio
import json
import os
import re
import sys
import urllib.parse
from collections import Counter
from collections.abc import Collection, Iterable, Iterator, Mapping, Sequence
from contextlib import AsyncExitStack, contextmanager
from enum import Enum
from functools import cache
from itertools import chain
from operator import attrgetter
from pathlib import Path
from typing import Any, Literal, Protocol, TypeAlias, TypeVar, final

import aiohttp
import attrs
from packaging.specifiers import SpecifierSet
from packaging.version import Version

if sys.version_info < (3, 10):
    raise ImportError("Python 3.10+ is required!")

if sys.version_info >= (3, 11):
    import tomllib  # pragma: no cover
else:
    import tomli as tomllib  # pragma: no cover


__all__ = [
    "AnnotationStats",
    "PackageName",
    "PackageStats",
    "PackageStatus",
    "PyrightSetting",
    "StubtestSetting",
    "gather_annotation_stats_on_file",
    "gather_annotation_stats_on_package",
    "gather_stats",
    "gather_stats_on_package",
    "get_package_size",
    "get_package_status",
    "get_pyright_setting",
    "get_stubtest_setting",
    "tmpdir_typeshed",
]

PackageName: TypeAlias = str
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
class _SingleAnnotationAnalyzer(ast.NodeVisitor):
    Any_in_annotation: bool = False
    Incomplete_in_annotation: bool = False

    def visit_Name(self, node: ast.Name) -> None:
        match node.id:
            case "Any":
                self.Any_in_annotation = True
            case "Incomplete":
                self.Incomplete_in_annotation = True
            case _:
                pass

    def visit_Attribute(self, node: ast.Attribute) -> None:
        value = node.value
        if isinstance(value, ast.Name):
            match f"{value.id}.{node.attr}":
                case "typing.Any":
                    self.Any_in_annotation = True
                case "_typeshed.Incomplete":
                    self.Incomplete_in_annotation = True
                case _:
                    pass
        self.generic_visit(node)


class _SingleAnnotationAnalysis(Protocol):
    Any_in_annotation: bool
    Incomplete_in_annotation: bool


def _analyse_annotation(annotation: ast.AST) -> _SingleAnnotationAnalysis:
    analyser = _SingleAnnotationAnalyzer()
    analyser.visit(annotation)
    return analyser


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


def _is_staticmethod(decorator: ast.expr) -> bool:
    match decorator:
        case ast.Name("staticmethod"):
            return True
        case ast.Attribute(ast.Name("builtins"), "staticmethod"):
            return True
        case _:
            return False


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
        self.stats.annotated_variables += 1
        analysis = _analyse_annotation(node.annotation)
        if analysis.Any_in_annotation:
            self.stats.explicit_Any_variables += 1
        if analysis.Incomplete_in_annotation:
            self.stats.explicit_Incomplete_variables += 1
        self.generic_visit(node)

    def _visit_arg(
        self, arg_number: int, node: ast.arg, *, is_staticmethod: bool
    ) -> None:
        # We don't want self/cls/metacls/mcls arguments to count towards the statistics
        # Whatever they're called, they can easily be inferred
        if self.in_class and (not is_staticmethod) and (not arg_number):
            return

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
        is_decorated_with_staticmethod = any(
            _is_staticmethod(decorator) for decorator in node.decorator_list
        )
        for i, arg_node in enumerate(
            chain(args.posonlyargs, args.args, args.kwonlyargs)
        ):
            self._visit_arg(i, arg_node, is_staticmethod=is_decorated_with_staticmethod)

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


@cache
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
    package_directory = _get_package_directory(package_name, typeshed_dir)
    file_results = [
        gather_annotation_stats_on_file(path)
        for path in package_directory.rglob("*.pyi")
    ]
    # Sum all the statistics together, to get the statistics for the package as a whole
    #
    # TODO: we're throwing away information here.
    # It might be nice to have a way to get per-file stats, especially for the stdlib.
    package_stats: Counter[str] = sum(
        [Counter(attrs.asdict(result)) for result in file_results], start=Counter()
    )
    return AnnotationStats(**package_stats)


@cache
def _get_package_metadata(
    package_name: PackageName, typeshed_dir: Path | str
) -> Mapping[str, Any]:
    package_directory = _get_package_directory(package_name, typeshed_dir)
    with open(package_directory / "METADATA.toml", "rb") as f:
        return tomllib.load(f)


class StubtestSetting(_NiceReprEnum):
    """Enumeration of the various possible settings typeshed uses for stubtest in CI."""

    SKIPPED = "Stubtest is skipped in CI for this package."
    MISSING_STUBS_IGNORED = (
        "The `--ignore-missing-stub` stubtest setting is used in CI."
    )
    ERROR_ON_MISSING_STUB = (
        "Objects missing from the stub cause stubtest to emit an error in CI."
    )


def get_stubtest_setting(
    package_name: str, *, typeshed_dir: Path | str
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
    metadata = _get_package_metadata(package_name, typeshed_dir)
    match metadata.get("tool", {}).get("stubtest", {}):
        case {"skip": True}:
            return StubtestSetting.SKIPPED
        case {"ignore_missing_stub": False}:
            return StubtestSetting.ERROR_ON_MISSING_STUB
        case _:
            return StubtestSetting.MISSING_STUBS_IGNORED


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


def get_package_size(package_name: str, *, typeshed_dir: Path | str) -> int:
    """Get the total number of lines of code for a stubs package in typeshed.

    Args:
        package_name: The name of the stubs package to find the line number for.
        typeshed_dir: A path pointing to a typeshed directory
            in which to find the stubs package.

    Returns:
        The number of lines of code the stubs package contains.

    Examples:
        >>> from typeshed_stats.gather import tmpdir_typeshed, get_package_size
        >>> with tmpdir_typeshed() as typeshed:
        ...     mypy_extensions_size = get_package_size("mypy-extensions", typeshed_dir=typeshed)
        ...
        >>> type(mypy_extensions_size) is int and mypy_extensions_size > 0
        True
    """
    return sum(
        len(stub.read_text(encoding="utf-8").splitlines())
        for stub in _get_package_directory(package_name, typeshed_dir).rglob("*.pyi")
    )


@cache
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


def get_pyright_setting(
    package_name: PackageName, *, typeshed_dir: Path | str
) -> PyrightSetting:
    """Get the setting typeshed uses in CI when pyright is run on a certain package.

    Args:
        package_name: The name of the package to find the stubtest setting for.
        typeshed_dir: A path pointing to a typeshed directory,
            from which to retrieve the stubtest setting.

    Returns:
        A member of the [`PyrightSetting`][typeshed_stats.gather.PyrightSetting]
            enumeration (see the docs on `PyrightSetting` for details).

    Examples:
        >>> from typeshed_stats.gather import tmpdir_typeshed, get_pyright_setting
        >>> with tmpdir_typeshed() as typeshed:
        ...     stdlib_setting = get_pyright_setting("stdlib", typeshed_dir=typeshed)
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
    package_directory = _get_package_directory(package_name, typeshed_dir)
    entirely_excluded_paths = _get_pyright_excludelist(
        typeshed_dir=typeshed_dir, config_filename="pyrightconfig.json"
    )
    paths_excluded_from_stricter_check = _get_pyright_excludelist(
        typeshed_dir=typeshed_dir, config_filename="pyrightconfig.stricter.json"
    )

    if _path_or_path_ancestor_is_listed(package_directory, entirely_excluded_paths):
        return PyrightSetting.ENTIRELY_EXCLUDED
    if _child_of_path_is_listed(package_directory, entirely_excluded_paths):
        return PyrightSetting.SOME_FILES_EXCLUDED
    if _path_or_path_ancestor_is_listed(
        package_directory, paths_excluded_from_stricter_check
    ):
        return PyrightSetting.NOT_STRICT
    if _child_of_path_is_listed(package_directory, paths_excluded_from_stricter_check):
        return PyrightSetting.STRICT_ON_SOME_FILES
    return PyrightSetting.STRICT


@final
@attrs.define
class PackageStats:
    """Statistics about a single stubs package in typeshed."""

    package_name: PackageName
    number_of_lines: int
    package_status: PackageStatus
    stubtest_setting: StubtestSetting
    pyright_setting: PyrightSetting
    annotation_stats: AnnotationStats


async def gather_stats_on_package(
    package_name: PackageName,
    *,
    typeshed_dir: Path | str,
    session: aiohttp.ClientSession | None = None,
) -> PackageStats:
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
        An instance of the [`PackageStats`][typeshed_stats.gather.PackageStats] class.

    Examples:
        >>> import asyncio
        >>> from typeshed_stats.gather import tmpdir_typeshed, gather_stats_on_package
        >>> with tmpdir_typeshed() as typeshed:
        ...     stdlib_stats = asyncio.run(gather_stats_on_package("stdlib", typeshed_dir=typeshed))
        ...
        >>> stdlib_stats.package_name
        'stdlib'
        >>> stdlib_stats.stubtest_setting
        StubtestSetting.ERROR_ON_MISSING_STUB
        >>> type(stdlib_stats.number_of_lines) is int and stdlib_stats.number_of_lines > 0
        True
    """
    return PackageStats(
        package_name=package_name,
        number_of_lines=get_package_size(package_name, typeshed_dir=typeshed_dir),
        package_status=await get_package_status(
            package_name, typeshed_dir=typeshed_dir, session=session
        ),
        stubtest_setting=get_stubtest_setting(package_name, typeshed_dir=typeshed_dir),
        pyright_setting=get_pyright_setting(package_name, typeshed_dir=typeshed_dir),
        annotation_stats=gather_annotation_stats_on_package(
            package_name, typeshed_dir=typeshed_dir
        ),
    )


async def _gather_stats(
    packages: Iterable[str], *, typeshed_dir: Path | str
) -> Sequence[PackageStats]:
    conn = aiohttp.TCPConnector(limit_per_host=10)
    async with aiohttp.ClientSession(connector=conn) as session:
        tasks = (
            gather_stats_on_package(
                package_name, typeshed_dir=typeshed_dir, session=session
            )
            for package_name in packages
        )
        return await asyncio.gather(*tasks, return_exceptions=True)


def gather_stats(
    packages: Iterable[str] | None = None, *, typeshed_dir: Path | str
) -> Sequence[PackageStats]:
    """Concurrently gather statistics on multiple packages.

    Note: this function calls `asyncio.run()` to start an asyncio event loop.
    It is therefore not suitable to be called from inside functions
    that are themselves called as part of an asyncio event loop.

    Args:
        packages: An iterable of package names to be analysed, or None.
            If `None`, defaults to all third-party stubs, plus the stubs for the stdlib.
        typeshed_dir: The path to a local clone of typeshed.

    Returns:
        A sequence of [`PackageStats`][typeshed_stats.gather.PackageStats] objects.
            Each `PackageStats` object contains information representing an analysis
            of a certain stubs package in typeshed.

    Examples:
        >>> from typeshed_stats.gather import PackageStats, tmpdir_typeshed, gather_stats
        >>> with tmpdir_typeshed() as typeshed:
        ...     stats = gather_stats(["stdlib", "aiofiles", "boto"], typeshed_dir=typeshed)
        ...
        >>> [s.package_name for s in stats]
        ['aiofiles', 'boto', 'stdlib']
        >>> all(type(s) is PackageStats for s in stats)
        True
    """
    if packages is None:
        packages = os.listdir(Path(typeshed_dir, "stubs")) + ["stdlib"]
    results = asyncio.run(_gather_stats(packages, typeshed_dir=typeshed_dir))
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
