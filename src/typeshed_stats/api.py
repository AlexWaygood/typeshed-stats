"""Python-level API, for use as a library."""

from __future__ import annotations

import ast
import asyncio
import json
import re
import sys
import urllib.parse
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from enum import Enum
from functools import cache
from operator import attrgetter
from pathlib import Path
from typing import Any, TypeAlias, TypeVar, final

import aiohttp
import attrs
import cattrs
from packaging.specifiers import SpecifierSet
from packaging.version import Version

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

assert sys.version_info >= (3, 10), "Python 3.10+ is required."


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
    "get_stubtest_setting",
    "stats_from_csv",
    "stats_from_json",
    "stats_to_csv",
    "stats_to_html",
    "stats_to_json",
    "stats_to_markdown",
]

PackageName: TypeAlias = str

_CATTRS_CONVERTER = cattrs.Converter()
_cattrs_unstructure = _CATTRS_CONVERTER.unstructure
_cattrs_structure = _CATTRS_CONVERTER.structure

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


_CATTRS_CONVERTER.register_unstructure_hook(_NiceReprEnum, attrgetter("name"))
_CATTRS_CONVERTER.register_structure_hook(_NiceReprEnum, lambda d, t: t[d])  # type: ignore[index,no-any-return]


def _is_Any(annotation: ast.expr) -> bool:
    """Return `True` if an AST node represents `typing.Any`.

    >>> _is_Any(ast.Name(id="Any"))
    True
    >>> _is_Any(ast.Name(id="foo"))
    False
    >>> _is_Any(ast.Attribute(value=ast.Name(id="typing"), attr="Any"))
    True
    >>> _is_Any(ast.Attribute(value=ast.Name(id="typing"), attr="foo"))
    False
    >>> _is_Any(ast.Attribute(value=ast.Name(id="foo"), attr="Any"))
    False
    >>> _is_Any(ast.Module())
    False
    >>> _is_Any(object())
    False
    """
    match annotation:
        case ast.Name("Any"):
            return True
        case ast.Attribute(value=ast.Name("typing"), attr="Any"):
            return True
        case _:
            return False


def _is_Incomplete(annotation: ast.expr) -> bool:
    """Return `True` if an AST node represents `_typeshed.Incomplete`.

    >>> _is_Incomplete(ast.Name(id="Incomplete"))
    True
    >>> _is_Incomplete(ast.Name(id="foo"))
    False
    >>> _is_Incomplete(ast.Attribute(value=ast.Name(id="_typeshed"), attr="Incomplete"))
    True
    >>> _is_Incomplete(ast.Attribute(value=ast.Name(id="_typeshed"), attr="foo"))
    False
    >>> _is_Incomplete(ast.Attribute(value=ast.Name(id="foo"), attr="Incomplete"))
    False
    >>> _is_Incomplete(ast.Module())
    False
    >>> _is_Incomplete(object())
    False
    """
    match annotation:
        case ast.Name("Incomplete"):
            return True
        case ast.Attribute(value=ast.Name("_typeshed"), attr="Incomplete"):
            return True
        case _:
            return False


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


class _AnnotationStatsCollector(ast.NodeVisitor):
    """AST Visitor for collecting stats on a single stub file."""

    def __init__(self) -> None:
        self.stats = AnnotationStats()
        self._class_nesting = 0
        self._function_decorators: frozenset[str] = frozenset()

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
        if _is_Any(node.annotation):
            self.stats.explicit_Any_variables += 1
        elif _is_Incomplete(node.annotation):
            self.stats.explicit_Incomplete_variables += 1
        self.generic_visit(node)

    def visit_arg(self, node: ast.arg) -> None:
        self.generic_visit(node)

        # We don't want self/cls/metacls/mcls arguments to count towards the statistics
        if self.in_class and "staticmethod" not in self._function_decorators:
            if "classmethod" in self._function_decorators:
                if node.arg in {"cls", "metacls", "mcls"}:
                    return
            elif node.arg == "self":
                return

        annotation = node.annotation
        if annotation is None:
            self.stats.unannotated_parameters += 1
        else:
            self.stats.annotated_parameters += 1
            if _is_Any(annotation):
                self.stats.explicit_Any_parameters += 1
            elif _is_Incomplete(annotation):
                self.stats.explicit_Incomplete_parameters += 1

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        returns = node.returns
        if returns is None:
            self.stats.unannotated_returns += 1
        else:
            self.stats.annotated_returns += 1
            if _is_Any(returns):
                self.stats.explicit_Any_returns += 1
            elif _is_Incomplete(returns):
                self.stats.explicit_Incomplete_returns += 1

        old_function_decorators = self._function_decorators
        self._function_decorators = frozenset(
            decorator.id
            for decorator in node.decorator_list
            if isinstance(decorator, ast.Name)
        )
        self.generic_visit(node)
        self._function_decorators = old_function_decorators

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)


def gather_annotation_stats_on_file(path: Path) -> AnnotationStats:
    """Gather annotation stats on a single typeshed stub file.

    Args:
        path: The location of the file to be analysed.

    Returns:
        An `AnnotationStats` object containing data
        about the annotations in the file.
    """
    visitor = _AnnotationStatsCollector()
    visitor.visit(ast.parse(path.read_text(encoding="utf-8")))
    return visitor.stats


@cache
def _get_package_directory(package_name: PackageName, typeshed_dir: Path) -> Path:
    if package_name == "stdlib":
        return typeshed_dir / "stdlib"
    return typeshed_dir / "stubs" / package_name


def gather_annotation_stats_on_package(
    package_name: PackageName, *, typeshed_dir: Path
) -> AnnotationStats:
    """Aggregate annotation stats on a typeshed stubs package.

    Args:
        package_name: The name of the stubs package to analyze.
        typeshed_dir: A path pointing to the location of a typeshed directory
          in which to find the stubs package source.

    Returns:
        An `AnnotationStats` object containing data
        about the annotations in the package.
    """
    package_directory = _get_package_directory(package_name, typeshed_dir)
    file_results = [
        gather_annotation_stats_on_file(path)
        for path in package_directory.rglob("*.pyi")
    ]
    # Sum all the statistics together, to get the statistics for the package as a whole
    package_stats: Counter[str] = sum(
        [Counter(attrs.asdict(result)) for result in file_results], start=Counter()
    )
    return AnnotationStats(**package_stats)


@cache
def _get_package_metadata(package_directory: Path) -> Mapping[str, Any]:
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


def get_stubtest_setting(package_name: str, *, typeshed_dir: Path) -> StubtestSetting:
    """Get the setting typeshed uses in CI when stubtest is run on a certain package.

    Args:
        package_name: The name of the package to find the stubtest setting for.
        typeshed_dir: A path pointing to a typeshed directory,
          from which to retrieve the stubtest setting.

    Returns:
        A member of the `StubtestSetting` enumeration
        (see the docs on `StubtestSetting` for details).
    """
    if package_name == "stdlib":
        return StubtestSetting.ERROR_ON_MISSING_STUB
    package_directory = _get_package_directory(package_name, typeshed_dir)
    metadata = _get_package_metadata(package_directory)
    stubtest_settings = metadata.get("tool", {}).get("stubtest", {})
    if stubtest_settings.get("skip", False):
        return StubtestSetting.SKIPPED
    ignore_missing_stub_used = stubtest_settings.get("ignore_missing_stub", True)
    return StubtestSetting[
        "MISSING_STUBS_IGNORED" if ignore_missing_stub_used else "ERROR_ON_MISSING_STUB"
    ]


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


async def _get_package_status(
    package_name: str, package_directory: Path, *, session: aiohttp.ClientSession
) -> PackageStatus:
    if package_name == "stdlib":
        # This function isn't really relevant for the stdlib stubs
        return PackageStatus.STDLIB

    if package_name == "gdb":
        return PackageStatus.NOT_ON_PYPI

    metadata = _get_package_metadata(package_directory)

    if "obsolete_since" in metadata:
        return PackageStatus.OBSOLETE

    if metadata.get("no_longer_updated", False):
        return PackageStatus.NO_LONGER_UPDATED

    typeshed_pinned_version = SpecifierSet(f"=={metadata['version']}")
    pypi_root = f"https://pypi.org/pypi/{urllib.parse.quote(package_name)}"
    async with session.get(f"{pypi_root}/json") as response:
        response.raise_for_status()
        pypi_data = await response.json()
    pypi_version = Version(pypi_data["info"]["version"])
    return PackageStatus[
        "UP_TO_DATE" if pypi_version in typeshed_pinned_version else "OUT_OF_DATE"
    ]


def _get_package_line_number(package_directory: Path) -> int:
    return sum(
        len(stub.read_text(encoding="utf-8").splitlines())
        for stub in package_directory.rglob("*.pyi")
    )


@cache
def _get_pyright_strict_excludelist(typeshed_dir: Path) -> frozenset[Path]:
    # Read pyrightconfig.stricter.json;
    # do some pre-processing so that it can be passed to json.loads()
    with open(typeshed_dir / "pyrightconfig.stricter.json", encoding="utf-8") as file:
        # strip comments from the file
        lines = [line for line in file if not line.strip().startswith("//")]
    # strip trailing commas from the file
    valid_json = re.sub(r",(\s*?[\}\]])", r"\1", "\n".join(lines))
    pyright_config = json.loads(valid_json)
    assert isinstance(pyright_config, dict)
    excludelist = pyright_config.get("exclude", [])
    return frozenset(typeshed_dir / item for item in excludelist)


class PyrightSetting(_NiceReprEnum):
    """The various possible pyright settings typeshed uses in CI."""

    STRICT = "All files are tested with the stricter pyright settings in CI."
    NOT_STRICT = "All files are excluded from the stricter pyright settings in CI."
    STRICT_ON_SOME_FILES = (
        "Some files are tested with the stricter pyright settings in CI;"
        " some are excluded."
    )


def _get_pyright_strictness(
    package_directory: Path, *, typeshed_dir: Path
) -> PyrightSetting:
    excluded_paths = _get_pyright_strict_excludelist(typeshed_dir)
    if package_directory in excluded_paths:
        return PyrightSetting.NOT_STRICT
    if any(
        package_directory in excluded_path.parents for excluded_path in excluded_paths
    ):
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

    def to_dict(self) -> dict[str, Any]:
        """Convert a `PackageStats` object to unstructured data."""
        return _cattrs_unstructure(self)  # type: ignore[no-any-return]

    @staticmethod
    def from_dict(data: dict[str, Any]) -> PackageStats:
        """Coerce unstructured data into a `PackageStats` object."""
        return _cattrs_structure(data, PackageStats)


async def _gather_stats_for_package(
    package_name: PackageName, *, typeshed_dir: Path, session: aiohttp.ClientSession
) -> PackageStats:
    if package_name == "stdlib":
        package_directory = typeshed_dir / "stdlib"
    else:
        package_directory = typeshed_dir / "stubs" / package_name
    return PackageStats(
        package_name=package_name,
        number_of_lines=_get_package_line_number(package_directory),
        package_status=await _get_package_status(
            package_name, package_directory, session=session
        ),
        stubtest_setting=get_stubtest_setting(package_name, typeshed_dir=typeshed_dir),
        pyright_setting=_get_pyright_strictness(
            package_directory, typeshed_dir=typeshed_dir
        ),
        annotation_stats=gather_annotation_stats_on_package(
            package_name, typeshed_dir=typeshed_dir
        ),
    )


async def _gather_stats(
    packages: Iterable[str], *, typeshed_dir: Path
) -> Sequence[PackageStats]:
    conn = aiohttp.TCPConnector(limit_per_host=10)
    async with aiohttp.ClientSession(connector=conn) as session:
        tasks = (
            _gather_stats_for_package(
                package_name, typeshed_dir=typeshed_dir, session=session
            )
            for package_name in packages
        )
        return await asyncio.gather(*tasks)


def gather_stats(
    packages: Iterable[str], *, typeshed_dir: Path | str
) -> Sequence[PackageStats]:
    """Concurrently gather statistics on multiple packages.

    Note: this function calls `asyncio.run()` to start an asyncio event loop.
    It is therefore not suitable to be called from inside functions
    that are themselves called as part of an asyncio event loop.

    Args:
        packages: An iterable of package names to be analysed.
        typeshed_dir: The path to a local clone of typeshed.

    Returns:
        A sequence of `PackageStats` objects. Each `PackageStats` object
        contains information representing an analysis of a certain stubs package
        in typeshed.
    """
    if isinstance(typeshed_dir, str):
        typeshed_dir = Path(typeshed_dir)
    return asyncio.run(_gather_stats(packages, typeshed_dir=typeshed_dir))


def stats_to_json(stats: Sequence[PackageStats]) -> str:
    """Convert stats on multiple stubs packages to JSON format."""
    return json.dumps(_cattrs_unstructure(stats), indent=2)


def stats_from_json(data: str) -> list[PackageStats]:
    """Load `PackageStats` objects from JSON format."""
    return _cattrs_structure(json.loads(data), list[PackageStats])


def stats_to_csv(stats: Sequence[PackageStats]) -> str:
    """Convert stats on multiple stubs packages to csv format."""
    import csv
    import io

    converted_stats = _cattrs_unstructure(stats)
    for info in converted_stats:
        info |= info["annotation_stats"]
        del info["annotation_stats"]
    fieldnames = converted_stats[0].keys()
    csvfile = io.StringIO(newline="")
    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
    writer.writeheader()
    for info in converted_stats:
        writer.writerow(info)
    return csvfile.getvalue()


@cache
def _annotation_stats_fields() -> tuple[str, ...]:
    return tuple(f.name for f in attrs.fields(AnnotationStats))


def stats_from_csv(data: str) -> list[PackageStats]:
    """Load `PackageStats` objects from csv format."""
    import csv
    import io

    csvfile = io.StringIO(data, newline="")
    stats = list(csv.DictReader(csvfile))
    annotation_stats_fields = _annotation_stats_fields()
    converted_stats = []
    for stat in stats:
        converted_stat, annotation_stats = {}, {}
        for key, val in stat.items():
            if key in annotation_stats_fields:
                annotation_stats[key] = val
            else:
                converted_stat[key] = val
        converted_stat["annotation_stats"] = annotation_stats
        converted_stats.append(converted_stat)
    return _cattrs_structure(converted_stats, list[PackageStats])


def stats_to_markdown(stats: Sequence[PackageStats]) -> str:
    """Generate MarkDown describing statistics on multiple stubs packages."""
    import textwrap

    def format_enum_member(enum_member: Enum) -> str:
        return " ".join(enum_member.name.split("_")).lower()

    template = textwrap.dedent(
        """
        ## Stats on typeshed's stubs for {package_name}

        ### Number of lines
        {number_of_lines}

        ### Package status: {package_status.formatted_name}
        {package_status.value}

        ### Stubtest settings in CI: {stubtest_setting.formatted_name}
        {stubtest_setting.value}

        ### Pyright settings in CI: {pyright_setting.formatted_name}
        {pyright_setting.value}

        ### Statistics on the annotations in typeshed's stubs for {package_name}
        {annotation_stats}
        """
    )

    def format_annotation_stats(annotation_stats: dict[str, int]) -> str:
        def format_key(key: str) -> str:
            return " ".join(key.split("_")).capitalize()

        return "- " + "\n- ".join(
            f"{format_key(key)}: {val}" for key, val in annotation_stats.items()
        )

    def format_package(package_stats: PackageStats) -> str:
        package_as_dict = attrs.asdict(package_stats)
        package_as_dict["annotation_stats"] = format_annotation_stats(
            package_as_dict["annotation_stats"]
        )
        return template.format(**package_as_dict)

    markdown_page = "# Stats on typeshed's stubs for various packages\n<br>\n"
    markdown_page += "\n<br>\n".join(format_package(info) for info in stats)
    return markdown_page


def stats_to_html(stats: Sequence[PackageStats]) -> str:
    """Generate HTML describing statistics on multiple stubs packages."""
    import markdown

    return markdown.markdown(stats_to_markdown(stats))
