import argparse
from pathlib import Path

def validate_packages(
    package_names: list[str], typeshed_dir: Path, *, parser: argparse.ArgumentParser
) -> None:
    stubs_dir = typeshed_dir / "stubs"
    for package_name in package_names:
        if package_name != "stdlib":
            package_dir = stubs_dir / package_name
            if not (package_dir.exists() and package_dir.is_dir()):
                parser.error(f"{package_name!r} does not have stubs in typeshed!")


def validate_typeshed_dir(
    typeshed_dir: Path, *, parser: argparse.ArgumentParser
) -> None:
    for folder in typeshed_dir, (typeshed_dir / "stdlib"), (typeshed_dir / "stubs"):
        if not (folder.exists() and folder.is_dir()):
            parser.error(f'"{typeshed_dir}" is not a valid typeshed directory')
