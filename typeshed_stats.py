from typing_extensions import TypeAlias


ExitCode: TypeAlias = int


def main() -> ExitCode:
    ...


if __name__ == "__main__":
    raise SystemExit(main())
