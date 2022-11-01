"""Tools for serializing and deserializing `PackageStats` objects."""

from collections.abc import Sequence
from functools import cache
from operator import attrgetter

import attrs
import cattrs

from typeshed_stats.gather import AnnotationStats, PackageStats, _NiceReprEnum

__all__ = [
    "stats_from_csv",
    "stats_from_json",
    "stats_to_csv",
    "stats_to_html",
    "stats_to_json",
    "stats_to_markdown",
]

_CATTRS_CONVERTER = cattrs.Converter()
_unstructure = _CATTRS_CONVERTER.unstructure
_structure = _CATTRS_CONVERTER.structure

_CATTRS_CONVERTER.register_unstructure_hook(_NiceReprEnum, attrgetter("name"))
_CATTRS_CONVERTER.register_structure_hook(_NiceReprEnum, lambda d, t: t[d])  # type: ignore[index,no-any-return]


def stats_to_json(stats: Sequence[PackageStats]) -> str:
    """Convert stats on multiple stubs packages to JSON format."""
    import json

    return json.dumps(_unstructure(stats), indent=2)


def stats_from_json(data: str) -> list[PackageStats]:
    """Load `PackageStats` objects from JSON format."""
    import json

    return _structure(json.loads(data), list[PackageStats])


def stats_to_csv(stats: Sequence[PackageStats]) -> str:
    """Convert stats on multiple stubs packages to csv format."""
    import csv
    import io

    converted_stats = _unstructure(stats)
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
    return _structure(converted_stats, list[PackageStats])


def stats_to_markdown(stats: Sequence[PackageStats]) -> str:
    """Generate MarkDown describing statistics on multiple stubs packages."""
    import textwrap

    template = textwrap.dedent(
        """
        ## Stats on typeshed's stubs for `{package_name}`

        ### Number of lines
        {number_of_lines}

        ### Package status: *{package_status.formatted_name}*
        {package_status.value}

        ### Stubtest settings in CI: *{stubtest_setting.formatted_name}*
        {stubtest_setting.value}

        ### Pyright settings in CI: *{pyright_setting.formatted_name}*
        {pyright_setting.value}

        ### Statistics on the annotations in typeshed's stubs for `{package_name}`
        - Parameters (excluding `self`, `cls`, `metacls` and `mcls`):
            - Annotated parameters: {annotated_parameters}
            - Unannotated parameters: {unannotated_parameters}
            - Explicit `Any` parameters: {explicit_Any_parameters}
            - Explicitly `Incomplete` (or partially `Incomplete`) parameters: {explicit_Incomplete_parameters}
        - Returns:
            - Annotated returns: {annotated_returns}
            - Unannotated returns: {unannotated_returns}
            - Explicit `Any` returns: {explicit_Any_returns}
            - Explicitly `Incomplete` (or partially `Incomplete`) returns: {explicit_Incomplete_returns}
        - Variables:
            - Annotated variables: {annotated_variables}
            - Explicit `Any` variables: {explicit_Any_variables}
            - Explicitly `Incomplete` (or partially `Incomplete`) variables: {explicit_Incomplete_variables}
        """
    )

    def format_package(package_stats: PackageStats) -> str:
        package_as_dict = attrs.asdict(package_stats)
        kwargs = package_as_dict | package_as_dict["annotation_stats"]
        del kwargs["annotation_stats"]
        return template.format(**kwargs)

    markdown_page = "# Stats on typeshed's stubs for various packages\n<br>\n"
    markdown_page += "\n<br>\n".join(format_package(info) for info in stats)
    return markdown_page


def stats_to_html(stats: Sequence[PackageStats]) -> str:
    """Generate HTML describing statistics on multiple stubs packages."""
    import markdown

    return markdown.markdown(stats_to_markdown(stats))
