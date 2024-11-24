"""Library and command-line tool for getting stats on various typeshed packages."""

import sys

if sys.version_info < (3, 11):  # noqa: UP036
    raise ImportError("Python 3.11+ is required!")

__all__: list[str] = []

if __name__ == "__main__":
    from ._cli import main

    main()
