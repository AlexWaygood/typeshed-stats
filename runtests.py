"""Convenience script to run all checks locally."""

import subprocess

FILES_TO_CHECK = ("src", "test_typeshed_stats.py", "runtests.py")


def main() -> int:
    """Run the checks."""

    print("Running requirements-txt-fixer...")
    subprocess.run(["requirements-txt-fixer", "requirements-dev.txt"])

    print("\nRunning pycln...")
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
    subprocess.run(["mypy"], check=True)

    print("\nRunning pytest...")
    subprocess.run(["pytest", "-vv"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
