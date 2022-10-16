"""Library and command-line tool for getting stats on various typeshed packages."""

import sys

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
    "main",
    "stats_from_csv",
    "stats_from_json",
    "stats_to_csv",
    "stats_to_html",
    "stats_to_json",
    "stats_to_markdown",
]

assert sys.version_info >= (3, 10), "Python 3.10+ is required."

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Interrupted!")
        code = 1
    else:
        code = 0
    raise SystemExit(code)
