"""Library and command-line tool for getting stats on various typeshed packages."""

from .api import (
    AnnotationStats,
    PackageName,
    PackageStats,
    PackageStatus,
    PyrightSetting,
    StubtestSetting,
    gather_annotation_stats_on_file,
    gather_annotation_stats_on_package,
    gather_stats,
    get_package_line_number,
    get_stubtest_setting,
    stats_from_csv,
    stats_from_json,
    stats_to_csv,
    stats_to_html,
    stats_to_json,
    stats_to_markdown,
)
from .cli import SUPPORTED_EXTENSIONS, OutputOption, main

__all__ = [
    "AnnotationStats",
    "OutputOption",
    "PackageName",
    "PackageStats",
    "PackageStatus",
    "PyrightSetting",
    "SUPPORTED_EXTENSIONS",
    "StubtestSetting",
    "gather_annotation_stats_on_file",
    "gather_annotation_stats_on_package",
    "gather_stats",
    "get_package_line_number",
    "get_stubtest_setting",
    "main",
    "stats_from_csv",
    "stats_from_json",
    "stats_to_csv",
    "stats_to_html",
    "stats_to_json",
    "stats_to_markdown",
]

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Interrupted!")
        code = 1
    else:
        code = 0
    raise SystemExit(code)
