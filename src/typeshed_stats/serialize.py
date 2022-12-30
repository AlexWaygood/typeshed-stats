"""Tools for serializing and deserializing [`PackageInfo`][typeshed_stats.gather.PackageInfo] and [`FileInfo`][typeshed_stats.gather.FileInfo] objects."""

from collections.abc import Sequence
from operator import attrgetter
from pathlib import Path
from typing import overload

import attrs
import cattrs

from typeshed_stats.gather import (
    AnnotationStats,
    FileInfo,
    PackageInfo,
    StubtestSettings,
    StubtestStrictness,
    _NiceReprEnum,
)

__all__ = [
    "file_stats_from_csv",
    "file_stats_from_json",
    "package_stats_from_csv",
    "package_stats_from_json",
    "stats_to_csv",
    "stats_to_json",
    "stats_to_markdown",
]

_CATTRS_CONVERTER = cattrs.Converter()
_unstructure = _CATTRS_CONVERTER.unstructure
_structure = _CATTRS_CONVERTER.structure

_CATTRS_CONVERTER.register_unstructure_hook(_NiceReprEnum, attrgetter("name"))
_CATTRS_CONVERTER.register_unstructure_hook(Path, Path.as_posix)
_CATTRS_CONVERTER.register_structure_hook(_NiceReprEnum, lambda d, t: t[d])  # type: ignore[index,no-any-return]
_CATTRS_CONVERTER.register_structure_hook(
    Path, lambda d, t: Path(d)
)  # pragma: no branch


def stats_to_json(stats: Sequence[PackageInfo | FileInfo]) -> str:
    """Convert stats on multiple stubs packages to JSON format.

    Args:
        stats: The statistics to convert.

    Returns:
        The statistics serialized as JSON.
    """
    import json

    return json.dumps(_unstructure(stats), indent=2) + "\n"


def package_stats_from_json(data: str) -> list[PackageInfo]:
    """Load [`PackageInfo`][typeshed_stats.gather.PackageInfo] objects from JSON format.

    Args:
        data: A JSON string.

    Returns:
        The statistics deserialized into
            [`PackageInfo`][typeshed_stats.gather.PackageInfo] objects.
    """
    import json

    return _structure(json.loads(data), list[PackageInfo])


def file_stats_from_json(data: str) -> list[FileInfo]:
    """Load [`FileInfo`][typeshed_stats.gather.FileInfo] objects from JSON format.

    Args:
        data: A JSON string.

    Returns:
        The statistics deserialized into
            [`FileInfo`][typeshed_stats.gather.FileInfo] objects.
    """
    import json

    return _structure(json.loads(data), list[FileInfo])


def stats_to_csv(stats: Sequence[PackageInfo | FileInfo]) -> str:
    """Convert stats on multiple stubs packages to csv format.

    Args:
        stats: The statistics to convert.

    Returns:
        The statistics serialized as a CSV string.
    """
    import csv
    import io

    converted_stats = _unstructure(stats)
    for info in converted_stats:
        info |= info["annotation_stats"]
        del info["annotation_stats"]

        # This section is specific to PackageInfo objects
        if "stubtest_settings" in info:
            info |= {
                f"stubtest_{key}": val for key, val in info["stubtest_settings"].items()
            }
            del info["stubtest_settings"]
            stubtest_platforms = info["stubtest_platforms"]
            if not stubtest_platforms:
                info["stubtest_platforms"] = "None"
            else:
                info["stubtest_platforms"] = ";".join(stubtest_platforms)
            if info["extra_description"] is None:
                info["extra_description"] = "-"

    fieldnames = converted_stats[0].keys()
    csvfile = io.StringIO(newline="")
    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
    writer.writeheader()
    for info in converted_stats:
        writer.writerow(info)
    return csvfile.getvalue()


@overload
def _stats_from_csv(data: str, cls: type[PackageInfo]) -> list[PackageInfo]:
    ...


@overload
def _stats_from_csv(data: str, cls: type[FileInfo]) -> list[FileInfo]:
    ...


def _stats_from_csv(
    data: str, cls: type[PackageInfo | FileInfo]
) -> list[PackageInfo] | list[FileInfo]:
    import csv
    import io

    csvfile = io.StringIO(data, newline="")
    stats = list(csv.DictReader(csvfile))
    converted_stats = []
    for stat in stats:
        converted_stat, annotation_stats, stubtest_settings = {}, {}, {}
        for key, val in stat.items():
            if key in AnnotationStats.__annotations__:
                annotation_stats[key] = val
            elif key.removeprefix("stubtest_") in StubtestSettings.__annotations__:
                stubtest_settings[key.removeprefix("stubtest_")] = val
            else:
                converted_stat[key] = val
        converted_stat["annotation_stats"] = annotation_stats
        converted_stat["stubtest_settings"] = stubtest_settings
        if cls is PackageInfo:
            stubtest_platforms = stubtest_settings["platforms"]
            if stubtest_platforms == "None":
                stubtest_settings["platforms"] = []
            else:
                stubtest_settings["platforms"] = stubtest_platforms.split(";")
            if converted_stat["extra_description"] == "-":
                converted_stat["extra_description"] = None
        converted_stats.append(converted_stat)
    return _structure(converted_stats, list[cls])  # type: ignore[valid-type]


def package_stats_from_csv(data: str) -> list[PackageInfo]:
    """Load [`PackageInfo`][typeshed_stats.gather.PackageInfo] objects from csv format.

    Args:
        data: A CSV string.

    Returns:
        The statistics deserialized into
            [`PackageInfo`][typeshed_stats.gather.PackageInfo] objects.
    """
    return _stats_from_csv(data, cls=PackageInfo)


def file_stats_from_csv(data: str) -> list[FileInfo]:
    """Load [`FileInfo`][typeshed_stats.gather.FileInfo] objects from csv format.

    Args:
        data: A CSV string.

    Returns:
        The statistics deserialized into
            [`FileInfo`][typeshed_stats.gather.FileInfo] objects.
    """
    return _stats_from_csv(data, cls=FileInfo)


def stats_to_markdown(stats: Sequence[PackageInfo]) -> str:
    """Generate MarkDown describing statistics on multiple stubs packages.

    Args:
        stats: The statistics to convert.

    Returns:
        A markdown page describing the statistics.
    """
    import re

    from jinja2 import Environment, FileSystemLoader

    environment = Environment(loader=FileSystemLoader(Path(__file__).parent))
    template = environment.get_template("markdown_template.md")

    def format_package(package_stats: PackageInfo) -> str:
        kwargs = attrs.asdict(package_stats)

        kwargs["stubtest_is_skipped"] = (
            package_stats.stubtest_settings.strictness is StubtestStrictness.SKIPPED
        )

        kwargs |= kwargs["annotation_stats"]
        del kwargs["annotation_stats"]

        kwargs |= {
            f"stubtest_{key}": val for key, val in kwargs["stubtest_settings"].items()
        }
        del kwargs["stubtest_settings"]

        kwargs = {
            key: ("{:,}".format(val) if type(val) is int else val)
            for key, val in kwargs.items()
        }

        return template.render(**kwargs)

    all_packages = "\n\n<hr>\n\n".join(format_package(info) for info in stats)
    return re.sub(r"\n{3,}", "\n\n", all_packages).strip() + "\n"
