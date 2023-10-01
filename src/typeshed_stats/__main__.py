"""Library and command-line tool for getting stats on various typeshed packages."""


__all__: list[str] = []

if __name__ == "__main__":
    from ._cli import main

    main()
