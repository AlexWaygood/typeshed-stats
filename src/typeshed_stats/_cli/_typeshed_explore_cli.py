"""typeshed-explore CLI"""

import argparse
import webbrowser
from pathlib import Path

from typeshed_stats._cli import validate_packages, validate_typeshed_dir
from typeshed_stats.gather import get_upstream_url

def main(argv: list[str]) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("package", type=str, help="Stubs package to explore")
    parser.add_argument("--view-upstream", "-vu", action="store_true")
    typeshed_options = parser.add_argument_group(title="Typeshed options")
    typeshed_options_group = typeshed_options.add_mutually_exclusive_group()
    typeshed_options_group.add_argument(
        "-t",
        "--typeshed-dir",
        type=Path,
        help=(
            "Path to a local clone of typeshed, "
            "from which to retrieve the upstream URL"
        ),
    )
    typeshed_options_group.add_argument(
        "-d",
        "--download-typeshed",
        action="store_true",
        help=(
            "Download a fresh copy of typeshed into a temporary directory, "
            "and use that to retrieve the upstream URL"
        ),
    )
    


if __name__ == "__main__":
    main()
