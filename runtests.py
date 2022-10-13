"""Convenience script to run all checks locally"""

import subprocess

FILES_TO_CHECK = ("src", "test_typeshed_stats.py", "runtests.py")


def main() -> int:
    checks = []

    print("Running pycln...")
    checks.append(subprocess.run(["pycln", ".", "--all"]))

    print("\nRunning isort...")
    checks.append(subprocess.run(["isort", *FILES_TO_CHECK]))

    print("\nRunning black...")
    checks.append(subprocess.run(["black", "."]))

    print("\nRunning flake8...")
    checks.append(subprocess.run(["flake8", *FILES_TO_CHECK]))

    print("\nRunning mypy...")
    checks.append(subprocess.run(["mypy"]))

    print("\nRunning pytest...")
    checks.append(subprocess.run(["pytest", "test_typeshed_stats.py", "-vv"]))

    return max(result.returncode for result in checks)


if __name__ == "__main__":
    raise SystemExit(main())
