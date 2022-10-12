from __future__ import annotations

import argparse
import ast
import asyncio
import dataclasses
import json
import os
import re
import sys
import urllib.parse
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields
from enum import Enum, auto
from functools import cache, cached_property, partial
from itertools import product
from pathlib import Path
from typing import Any, NamedTuple, TypeVar, get_type_hints
from typing_extensions import Annotated, TypeAlias

import aiohttp
import tomli
from packaging.specifiers import SpecifierSet
from packaging.version import Version

ExitCode: TypeAlias = int
PackageName: TypeAlias = str


class NiceReprEnum(Enum):
    def __repr__(self) -> str:
        return f"{self.__class__.__name__}.{self.name}"


def is_Any(annotation: ast.expr) -> bool:
    match annotation:
        case ast.Name("Any"):
            return True
        case ast.Attribute(value=ast.Name("typing"), attr="Any"):
            return True
        case _:
            return False


def is_Incomplete(annotation: ast.expr) -> bool:
    match annotation:
        case ast.Name("Incomplete"):
            return True
        case ast.Attribute(value=ast.Name("_typeshed"), attr="Incomplete"):
            return True
        case _:
            return False


@dataclass
class AnnotationStats(ast.NodeVisitor):
    """Statistics on the annotations for a source file or a directory of source files"""

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

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self.annotated_variables += 1
        if is_Any(node.annotation):
            self.explicit_Any_variables += 1
        elif is_Incomplete(node.annotation):
            self.explicit_Incomplete_variables += 1

    def visit_arg(self, node: ast.arg) -> None:
        annotation = node.annotation
        if annotation is None:
            self.unannotated_parameters += 1
        else:
            self.annotated_parameters += 1
            if is_Any(annotation):
                self.explicit_Any_parameters += 1
            elif is_Incomplete(annotation):
                self.explicit_Incomplete_parameters += 1
        self.generic_visit(node)

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        returns = node.returns
        if returns is None:
            self.unannotated_returns += 1
        else:
            self.annotated_returns += 1
            if is_Any(returns):
                self.explicit_Any_returns += 1
            elif is_Incomplete(returns):
                self.explicit_Incomplete_returns += 1

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)
        self.generic_visit(node)

    @staticmethod
    def gather_stats_on_file(path: Path) -> AnnotationStats:
        visitor = AnnotationStats()
        visitor.visit(ast.parse(path.read_text(encoding="utf-8")))
        return visitor


def gather_annotation_stats_on_package(package_directory: Path) -> AnnotationStats:
    file_results = [
        AnnotationStats.gather_stats_on_file(path)
        for path in package_directory.rglob("*.pyi")
    ]
    # Sum all the statistics together, to get the statistics for the package as a whole
    package_stats: Counter[str] = sum(
        [Counter(dataclasses.asdict(result)) for result in file_results],
        start=Counter(),
    )
    return AnnotationStats(**package_stats)


@cache
def get_package_metadata(package_directory: Path) -> Mapping[str, Any]:
    with open(package_directory / "METADATA.toml", "rb") as f:
        return tomli.load(f)


class StubtestSetting(NiceReprEnum):
    def __new__(cls, value: int, doc: str) -> StubtestSetting:
        member = object().__new__(cls)
        member._value_ = value
        member.__doc__ = doc
        return member

    SKIPPED = 0, "Stubtest is skipped in CI for this package"
    MISSING_STUBS_IGNORED = 1, "`--ignore-missing-stub` is used in CI"
    ERROR_ON_MISSING_STUB = 2, "Objects missing from the stub cause errors in CI"


def get_stubtest_setting(package_name: str, package_directory: Path) -> StubtestSetting:
    if package_name == "stdlib":
        return StubtestSetting.ERROR_ON_MISSING_STUB
    metadata = get_package_metadata(package_directory)
    stubtest_settings = metadata.get("tool", {}).get("stubtest", {})
    if stubtest_settings.get("skip", False):
        return StubtestSetting.SKIPPED
    ignore_missing_stub_used = stubtest_settings.get("ignore_missing_stub", True)
    return StubtestSetting[
        "MISSING_STUBS_IGNORED" if ignore_missing_stub_used else "ERROR_ON_MISSING_STUB"
    ]


class PackageStatus(NiceReprEnum):
    STDLIB = auto()
    OBSOLETE = auto()
    NO_LONGER_UPDATED = auto()
    OUT_OF_DATE = auto()
    UP_TO_DATE = auto()


async def get_package_status(
    package_name: str, package_directory: Path, *, session: aiohttp.ClientSession
) -> PackageStatus:
    if package_name == "stdlib":
        # This function isn't really relevant for the stdlib stubs
        return PackageStatus.STDLIB

    metadata = get_package_metadata(package_directory)

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


def get_package_line_number(package_directory: Path) -> int:
    return sum(
        len(stub.read_text().splitlines()) for stub in package_directory.rglob("*.pyi")
    )


@cache
def get_pyright_strict_excludelist(typeshed_dir: Path) -> frozenset[Path]:
    with open(typeshed_dir / "pyrightconfig.stricter.json", encoding="utf-8") as file:
        # strip comments from the file
        lines = [line for line in file if not line.strip().startswith("//")]
    # strip trailing commas from the file
    valid_json = re.sub(r",(\s*?[\}\]])", r"\1", "\n".join(lines))
    pyright_config = json.loads(valid_json)
    assert isinstance(pyright_config, dict)
    excludelist = pyright_config.get("exclude", [])
    return frozenset(typeshed_dir / item for item in excludelist)


class PyrightSetting(NiceReprEnum):
    STRICT = auto()
    NOT_STRICT = auto()
    STRICT_ON_SOME_FILES = auto()


def get_pyright_strictness(
    package_directory: Path, *, typeshed_dir: Path
) -> PyrightSetting:
    excluded_paths = get_pyright_strict_excludelist(typeshed_dir)
    if package_directory in excluded_paths:
        return PyrightSetting.NOT_STRICT
    if any(
        package_directory in excluded_path.parents for excluded_path in excluded_paths
    ):
        return PyrightSetting.STRICT_ON_SOME_FILES
    return PyrightSetting.STRICT


@dataclass
class PackageStats:
    package_name: PackageName
    number_of_lines: int
    package_status: PackageStatus
    stubtest_setting: StubtestSetting
    pyright_setting: PyrightSetting
    annotation_stats: AnnotationStats


async def gather_stats_for_package(
    package_name: PackageName, *, typeshed_dir: Path, session: aiohttp.ClientSession
) -> PackageStats:
    if package_name == "stdlib":
        package_directory = typeshed_dir / "stdlib"
    else:
        package_directory = typeshed_dir / "stubs" / package_name
    return PackageStats(
        package_name=package_name,
        number_of_lines=get_package_line_number(package_directory),
        package_status=await get_package_status(
            package_name, package_directory, session=session
        ),
        stubtest_setting=get_stubtest_setting(package_name, package_directory),
        pyright_setting=get_pyright_strictness(
            package_directory, typeshed_dir=typeshed_dir
        ),
        annotation_stats=gather_annotation_stats_on_package(package_directory),
    )


async def gather_stats(
    packages: list[str], *, typeshed_dir: Path
) -> Sequence[PackageStats]:
    conn = aiohttp.TCPConnector(limit_per_host=10)
    async with aiohttp.ClientSession(connector=conn) as session:
        tasks = (
            gather_stats_for_package(
                package_name, typeshed_dir=typeshed_dir, session=session
            )
            for package_name in packages
        )
        return await asyncio.gather(*tasks)


class OutputOption(Enum):
    PPRINT = auto()
    JSON = auto()
    CSV = auto()
    MARKDOWN = auto()


class Options(NamedTuple):
    packages: list[str]
    typeshed_dir: Path
    output_option: OutputOption
    writefile: Path | None


def _valid_supplied_path(cmd_arg: str, cmd_option: str, suffix: str) -> Path:
    path = Path(cmd_arg)
    if path.exists():
        raise argparse.ArgumentTypeError(f"Path {cmd_arg!r} already exists!")
    if path.suffix != suffix:
        raise argparse.ArgumentTypeError(
            f"Path supplied to {cmd_option!r} must have a {suffix!r} suffix, got"
            f" {path.suffix!r}"
        )
    return path


def get_options() -> Options:
    parser = argparse.ArgumentParser(description="Script to gather stats on typeshed")
    parser.add_argument(
        "packages",
        type=str,
        nargs="*",
        action="extend",
        help=(
            "Packages to gather stats on (defaults to all third-party packages, plus"
            " the stdlib)"
        ),
    )
    parser.add_argument(
        "-t",
        "--typeshed-dir",
        type=Path,
        required=True,
        help="Path to the typeshed directory",
    )

    output_options = parser.add_mutually_exclusive_group()
    output_options.add_argument(
        "--pprint",
        action="store_true",
        help=(
            "Pretty-print Python representations of the data straight to the terminal"
            " (default output)"
        ),
    )
    output_options.add_argument(
        "--to-json",
        action="store_true",
        help="Convert the data to JSON and print it to the terminal",
    )
    output_options.add_argument(
        "--to-csv-file",
        type=partial(_valid_supplied_path, cmd_option="--to-csv", suffix=".csv"),
        help="Save output to a .csv file",
    )
    output_options.add_argument(
        "--to-markdown",
        type=partial(_valid_supplied_path, cmd_option="--to-markdown", suffix=".md"),
        help="Save output to a formatted MarkDown file",
    )

    args = parser.parse_args()

    writefile: Path | None
    if args.to_json:
        output_option = OutputOption.JSON
        writefile = None
    elif args.to_csv_file:
        output_option = OutputOption.CSV
        writefile = args.to_csv_file
    elif args.to_markdown:
        output_option = OutputOption.MARKDOWN
        writefile = args.to_markdown
    else:
        # --pprint is the default if no option in this group was specified
        writefile = None
        output_option = OutputOption.PPRINT

    typeshed_dir = args.typeshed_dir
    packages = args.packages or os.listdir(typeshed_dir) + ["stdlib"]
    stdlib = typeshed_dir / "stdlib"
    if not (
        typeshed_dir.exists()
        and typeshed_dir.is_dir()
        and stdlib.exists()
        and stdlib.is_dir()
    ):
        raise TypeError(f'"{typeshed_dir}" is not a valid typeshed directory')
    return Options(packages, typeshed_dir, output_option, writefile)


def pprint_stats(stats: Sequence[PackageStats]) -> None:
    from pprint import pprint

    pprint({info_bundle.package_name: info_bundle for info_bundle in stats})


def jsonify_stats(stats: Sequence[PackageStats]) -> None:
    class EnumAwareEncoder(json.JSONEncoder):
        def default(self, obj: object) -> Any:
            if isinstance(obj, NiceReprEnum):
                return obj.name
            return super().default(obj)

    dictified_stats = {info.package_name: dataclasses.asdict(info) for info in stats}
    print(json.dumps(dictified_stats, indent=2, cls=EnumAwareEncoder))


def save_stats_to_csv(stats: Sequence[PackageStats], writefile: Path) -> None:
    import csv

    # First, dictify
    converted_stats = [dataclasses.asdict(info) for info in stats]

    # Then, flatten the data, and stringify the enums
    enum_fields = [
        key
        for key, val in get_type_hints(PackageStats).items()
        if issubclass(val, Enum)
    ]
    for info in converted_stats:
        info |= info["annotation_stats"]
        del info["annotation_stats"]
        for field in enum_fields:
            info[field] = info[field].name

    # Now, write to csv
    fieldnames = converted_stats[0].keys()
    with open(writefile, "w", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for info in converted_stats:
            writer.writerow(info)


def do_something_with_the_stats(
    stats: Sequence[PackageStats], output_option: OutputOption, writefile: Path | None
) -> None:
    if output_option is OutputOption.PPRINT:
        pprint_stats(stats)
    elif output_option is OutputOption.JSON:
        jsonify_stats(stats)
    elif output_option is OutputOption.CSV:
        assert writefile is not None
        save_stats_to_csv(stats, writefile)
    else:
        raise NotImplementedError(f"{OutputOption!r} has not yet been implemented!")


async def main() -> None:
    packages, typeshed_dir, output_option, writefile = get_options()
    stats = await gather_stats(packages, typeshed_dir=typeshed_dir)
    do_something_with_the_stats(stats, output_option, writefile)


if __name__ == "__main__":
    assert sys.version_info >= (3, 10), "Python 3.10+ is required to run this script."
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Interrupted!")
        code = 1
    else:
        code = 0
    raise SystemExit(code)
