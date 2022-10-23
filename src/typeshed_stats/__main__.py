"""Library and command-line tool for getting stats on various typeshed packages."""

import sys

if sys.version_info < (3, 10):
    raise ImportError("Python 3.10+ is required!")

__all__: list[str] = []

if __name__ == "__main__":  # pragma: no cover
    from ._cli import main

    main()
