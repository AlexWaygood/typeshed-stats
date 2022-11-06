"""Convenience script to run all checks locally."""

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Literal, overload

FILES_TO_CHECK = ("src", "tests", "runtests.py", "regenerate_examples.py")


@overload
def run_checks(
    *,
    regenerate_examples: Literal[True],
    typeshed_dir: Path,
    download_typeshed: Literal[False] = ...,
) -> None:
    ...


@overload
def run_checks(
    *,
    regenerate_examples: Literal[True],
    download_typeshed: Literal[True],
    typeshed_dir: None = ...,
) -> None:
    ...


@overload
def run_checks(
    *,
    regenerate_examples: Literal[False],
    download_typeshed: Literal[False] = ...,
    typeshed_dir: None = ...,
) -> None:
    ...


@overload
def run_checks(
    *,
    regenerate_examples: bool = ...,
    typeshed_dir: Path | None = ...,
    download_typeshed: bool = ...,
) -> None:
    ...


def run_checks(
    *,
    regenerate_examples: bool = False,
    typeshed_dir: Path | None = None,
    download_typeshed: bool = False,
) -> None:
    """Run the checks."""
    print("Running requirements-txt-fixer...")
    subprocess.run(["requirements-txt-fixer", "requirements-dev.txt"])

    print("\nRunning pycln...")
    # pycln doesn't seem to pick up the --all argument from pyproject.toml, not sure why
    subprocess.run(["pycln", ".", "--all"])

    print("\nRunning isort...")
    subprocess.run(["isort", *FILES_TO_CHECK])

    print("\nRunning black...")
    black_result = subprocess.run(["black", "."])
    if black_result.returncode == 123:
        print("Exiting early since black failed!")
        raise SystemExit(1)

    print("\nRunning flake8...")
    subprocess.run(["flake8", *FILES_TO_CHECK], check=True)

    print("\nRunning mypy...")
    # Running into weird cache issues locally to do with attrs,
    # so don't run this one with check=True (for now)
    subprocess.run(["mypy"])

    print("\nRunning pytest...")
    pytest_command = [
        "pytest",
        "--cov",
        "tests",
        "--cov",
        "src",
        "--cov-branch",
        "--cov-report",
        "term-missing",
    ]
    subprocess.run(pytest_command, check=True)

    if regenerate_examples:
        args = [sys.executable, "regenerate_examples.py"]
        if download_typeshed:
            args.append("--download-typeshed")
        else:
            assert typeshed_dir is not None
            args.extend(["--typeshed-dir", str(typeshed_dir)])
        subprocess.run(args, check=True)


def main() -> None:
    """Parse command-line args, run the checks."""
    parser = argparse.ArgumentParser("Script to regenerate examples")
    parser.add_argument("-r", "--regen-examples", action="store_true")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("-t", "--typeshed-dir", type=Path)
    group.add_argument("-d", "--download-typeshed", action="store_true")
    args = parser.parse_args()
    if args.regen_examples:
        if not args.typeshed_dir and not args.download_typeshed:
            parser.error(
                "Must specify --typeshed-dir on the command line"
                " if --regen-examples is specified"
            )
    elif args.typeshed_dir:
        parser.error(
            "--typeshed-dir has no meaning if --regen-examples is not specified"
        )
    run_checks(
        regenerate_examples=args.regen_examples,
        typeshed_dir=args.typeshed_dir,
        download_typeshed=args.download_typeshed,
    )


if __name__ == "__main__":
    main()
    raise SystemExit(0)
