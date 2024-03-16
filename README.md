<div align=center>

# typeshed-stats

<img src="https://user-images.githubusercontent.com/66076021/202873196-3af493e6-bca0-4c1a-8853-73635b5c1ca8.png" width="500" alt="A Python in a field of wheat with a shed behind it, golden-red sunset in the background">

<br>

---

## A CLI tool and library to gather stats on [typeshed](https://github.com/python/typeshed)

<br>

[![website](https://img.shields.io/website?down_color=red&down_message=Offline&style=for-the-badge&up_color=green&up_message=Running&url=https%3A%2F%2Falexwaygood.github.io%2Ftypeshed-stats%2F)](https://alexwaygood.github.io/typeshed-stats/)[![build status](https://img.shields.io/github/actions/workflow/status/AlexWaygood/typeshed-stats/test.yml?branch=main&label=Tests&style=for-the-badge)](https://github.com/AlexWaygood/typeshed-stats/actions/workflows/test.yml)
<br>
[![Checked with mypy](https://img.shields.io/badge/mypy-checked-blue?style=for-the-badge)](http://mypy-lang.org/)[![Code style: Ruff](https://img.shields.io/badge/Code_style-Ruff-D7FF64?style=for-the-badge&logo=data:image/svg%2bxml;base64,PHN2ZyB3aWR0aD0iNTEwIiBoZWlnaHQ9IjYyMiIgdmlld0JveD0iMCAwIDUxMCA2MjIiIGZpbGw9Im5vbmUiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+PHBhdGggZmlsbC1ydWxlPSJldmVub2RkIiBjbGlwLXJ1bGU9ImV2ZW5vZGQiIGQ9Ik0yMDYuNzAxIDBDMjAwLjk2NCAwIDE5Ni4zMTQgNC42NDEzMSAxOTYuMzE0IDEwLjM2NjdWNDEuNDY2N0MxOTYuMzE0IDQ3LjE5MiAxOTEuNjYzIDUxLjgzMzMgMTg1LjkyNyA1MS44MzMzSDE1Ni44NDNDMTUxLjEwNyA1MS44MzMzIDE0Ni40NTYgNTYuNDc0NiAxNDYuNDU2IDYyLjJWMTQ1LjEzM0MxNDYuNDU2IDE1MC44NTkgMTQxLjgwNiAxNTUuNSAxMzYuMDY5IDE1NS41SDEwNi45ODZDMTAxLjI0OSAxNTUuNSA5Ni41OTg4IDE2MC4xNDEgOTYuNTk4OCAxNjUuODY3VjIyMi44ODNDOTYuNTk4OCAyMjguNjA5IDkxLjk0ODQgMjMzLjI1IDg2LjIxMTggMjMzLjI1SDU3LjEyODNDNTEuMzkxNyAyMzMuMjUgNDYuNzQxMyAyMzcuODkxIDQ2Ljc0MTMgMjQzLjYxN1YzMDAuNjMzQzQ2Ljc0MTMgMzA2LjM1OSA0Mi4wOTA5IDMxMSAzNi4zNTQ0IDMxMUgxMC4zODdDNC42NTA0IDMxMSAwIDMxNS42NDEgMCAzMjEuMzY3VjM1Mi40NjdDMCAzNTguMTkyIDQuNjUwNCAzNjIuODMzIDEwLjM4NyAzNjIuODMzSDE0NS40MThDMTUxLjE1NCAzNjIuODMzIDE1NS44MDQgMzY3LjQ3NSAxNTUuODA0IDM3My4yVjQzMC4yMTdDMTU1LjgwNCA0MzUuOTQyIDE1MS4xNTQgNDQwLjU4MyAxNDUuNDE4IDQ0MC41ODNIMTE2LjMzNEMxMTAuNTk3IDQ0MC41ODMgMTA1Ljk0NyA0NDUuMjI1IDEwNS45NDcgNDUwLjk1VjUwNy45NjdDMTA1Ljk0NyA1MTMuNjkyIDEwMS4yOTcgNTE4LjMzMyA5NS41NjAxIDUxOC4zMzNINjYuNDc2NkM2MC43NCA1MTguMzMzIDU2LjA4OTYgNTIyLjk3NSA1Ni4wODk2IDUyOC43VjYxMS42MzNDNTYuMDg5NiA2MTcuMzU5IDYwLjc0IDYyMiA2Ni40NzY2IDYyMkgxNDkuNTcyQzE1NS4zMDkgNjIyIDE1OS45NTkgNjE3LjM1OSAxNTkuOTU5IDYxMS42MzNWNTcwLjE2N0gyMDEuNTA3QzIwNy4yNDQgNTcwLjE2NyAyMTEuODk0IDU2NS41MjUgMjExLjg5NCA1NTkuOFY1MjguN0MyMTEuODk0IDUyMi45NzUgMjE2LjU0NCA1MTguMzMzIDIyMi4yODEgNTE4LjMzM0gyNTEuMzY1QzI1Ny4xMDEgNTE4LjMzMyAyNjEuNzUyIDUxMy42OTIgMjYxLjc1MiA1MDcuOTY3VjQ3Ni44NjdDMjYxLjc1MiA0NzEuMTQxIDI2Ni40MDIgNDY2LjUgMjcyLjEzOCA0NjYuNUgzMDEuMjIyQzMwNi45NTkgNDY2LjUgMzExLjYwOSA0NjEuODU5IDMxMS42MDkgNDU2LjEzM1Y0MjUuMDMzQzMxMS42MDkgNDE5LjMwOCAzMTYuMjU5IDQxNC42NjcgMzIxLjk5NiA0MTQuNjY3SDM1MS4wNzlDMzU2LjgxNiA0MTQuNjY3IDM2MS40NjYgNDEwLjAyNSAzNjEuNDY2IDQwNC4zVjM3My4yQzM2MS40NjYgMzY3LjQ3NSAzNjYuMTE3IDM2Mi44MzMgMzcxLjg1MyAzNjIuODMzSDQwMC45MzdDNDA2LjY3MyAzNjIuODMzIDQxMS4zMjQgMzU4LjE5MiA0MTEuMzI0IDM1Mi40NjdWMzIxLjM2N0M0MTEuMzI0IDMxNS42NDEgNDE1Ljk3NCAzMTEgNDIxLjcxMSAzMTFINDUwLjc5NEM0NTYuNTMxIDMxMSA0NjEuMTgxIDMwNi4zNTkgNDYxLjE4MSAzMDAuNjMzVjIxNy43QzQ2MS4xODEgMjExLjk3NSA0NTYuNTMxIDIwNy4zMzMgNDUwLjc5NCAyMDcuMzMzSDQyMC42NzJDNDE0LjkzNiAyMDcuMzMzIDQxMC4yODUgMjAyLjY5MiA0MTAuMjg1IDE5Ni45NjdWMTY1Ljg2N0M0MTAuMjg1IDE2MC4xNDEgNDE0LjkzNiAxNTUuNSA0MjAuNjcyIDE1NS41SDQ0OS43NTZDNDU1LjQ5MiAxNTUuNSA0NjAuMTQzIDE1MC44NTkgNDYwLjE0MyAxNDUuMTMzVjExNC4wMzNDNDYwLjE0MyAxMDguMzA4IDQ2NC43OTMgMTAzLjY2NyA0NzAuNTMgMTAzLjY2N0g0OTkuNjEzQzUwNS4zNSAxMDMuNjY3IDUxMCA5OS4wMjUzIDUxMCA5My4zVjEwLjM2NjdDNTEwIDQuNjQxMzIgNTA1LjM1IDAgNDk5LjYxMyAwSDIwNi43MDFaTTE2OC4yNjkgNDQwLjU4M0MxNjIuNTMyIDQ0MC41ODMgMTU3Ljg4MiA0NDUuMjI1IDE1Ny44ODIgNDUwLjk1VjUwNy45NjdDMTU3Ljg4MiA1MTMuNjkyIDE1My4yMzEgNTE4LjMzMyAxNDcuNDk1IDUxOC4zMzNIMTE4LjQxMUMxMTIuNjc1IDUxOC4zMzMgMTA4LjAyNCA1MjIuOTc1IDEwOC4wMjQgNTI4LjdWNTU5LjhDMTA4LjAyNCA1NjUuNTI1IDExMi42NzUgNTcwLjE2NyAxMTguNDExIDU3MC4xNjdIMTU5Ljk1OVY1MjguN0MxNTkuOTU5IDUyMi45NzUgMTY0LjYxIDUxOC4zMzMgMTcwLjM0NiA1MTguMzMzSDE5OS40M0MyMDUuMTY2IDUxOC4zMzMgMjA5LjgxNyA1MTMuNjkyIDIwOS44MTcgNTA3Ljk2N1Y0NzYuODY3QzIwOS44MTcgNDcxLjE0MSAyMTQuNDY3IDQ2Ni41IDIyMC4yMDQgNDY2LjVIMjQ5LjI4N0MyNTUuMDI0IDQ2Ni41IDI1OS42NzQgNDYxLjg1OSAyNTkuNjc0IDQ1Ni4xMzNWNDI1LjAzM0MyNTkuNjc0IDQxOS4zMDggMjY0LjMyNSA0MTQuNjY3IDI3MC4wNjEgNDE0LjY2N0gyOTkuMTQ1QzMwNC44ODEgNDE0LjY2NyAzMDkuNTMyIDQxMC4wMjUgMzA5LjUzMiA0MDQuM1YzNzMuMkMzMDkuNTMyIDM2Ny40NzUgMzE0LjE4MiAzNjIuODMzIDMxOS45MTkgMzYyLjgzM0gzNDkuMDAyQzM1NC43MzkgMzYyLjgzMyAzNTkuMzg5IDM1OC4xOTIgMzU5LjM4OSAzNTIuNDY3VjMyMS4zNjdDMzU5LjM4OSAzMTUuNjQxIDM2NC4wMzkgMzExIDM2OS43NzYgMzExSDM5OC44NTlDNDA0LjU5NiAzMTEgNDA5LjI0NiAzMDYuMzU5IDQwOS4yNDYgMzAwLjYzM1YyNjkuNTMzQzQwOS4yNDYgMjYzLjgwOCA0MDQuNTk2IDI1OS4xNjcgMzk4Ljg1OSAyNTkuMTY3SDMxOC44OEMzMTMuMTQzIDI1OS4xNjcgMzA4LjQ5MyAyNTQuNTI1IDMwOC40OTMgMjQ4LjhWMjE3LjdDMzA4LjQ5MyAyMTEuOTc1IDMxMy4xNDMgMjA3LjMzMyAzMTguODggMjA3LjMzM0gzNDcuOTYzQzM1My43IDIwNy4zMzMgMzU4LjM1IDIwMi42OTIgMzU4LjM1IDE5Ni45NjdWMTY1Ljg2N0MzNTguMzUgMTYwLjE0MSAzNjMuMDAxIDE1NS41IDM2OC43MzcgMTU1LjVIMzk3LjgyMUM0MDMuNTU3IDE1NS41IDQwOC4yMDggMTUwLjg1OSA0MDguMjA4IDE0NS4xMzNWMTE0LjAzM0M0MDguMjA4IDEwOC4zMDggNDEyLjg1OCAxMDMuNjY3IDQxOC41OTUgMTAzLjY2N0g0NDcuNjc4QzQ1My40MTUgMTAzLjY2NyA0NTguMDY1IDk5LjAyNTMgNDU4LjA2NSA5My4zVjYyLjJDNDU4LjA2NSA1Ni40NzQ2IDQ1My40MTUgNTEuODMzMyA0NDcuNjc4IDUxLjgzMzNIMjA4Ljc3OEMyMDMuMDQxIDUxLjgzMzMgMTk4LjM5MSA1Ni40NzQ2IDE5OC4zOTEgNjIuMlYxNDUuMTMzQzE5OC4zOTEgMTUwLjg1OSAxOTMuNzQxIDE1NS41IDE4OC4wMDQgMTU1LjVIMTU4LjkyMUMxNTMuMTg0IDE1NS41IDE0OC41MzQgMTYwLjE0MSAxNDguNTM0IDE2NS44NjdWMjIyLjg4M0MxNDguNTM0IDIyOC42MDkgMTQzLjg4MyAyMzMuMjUgMTM4LjE0NyAyMzMuMjVIMTA5LjA2M0MxMDMuMzI3IDIzMy4yNSA5OC42NzYyIDIzNy44OTEgOTguNjc2MiAyNDMuNjE3VjMwMC42MzNDOTguNjc2MiAzMDYuMzU5IDEwMy4zMjcgMzExIDEwOS4wNjMgMzExSDE5Ny4zNTJDMjAzLjA4OSAzMTEgMjA3LjczOSAzMTUuNjQxIDIwNy43MzkgMzIxLjM2N1Y0MzAuMjE3QzIwNy43MzkgNDM1Ljk0MiAyMDMuMDg5IDQ0MC41ODMgMTk3LjM1MiA0NDAuNTgzSDE2OC4yNjlaIiBmaWxsPSIjRDdGRjY0Ii8+PC9zdmc+)](https://github.com/astral-sh/ruff)[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&logoColor=white&style=for-the-badge)](https://pre-commit.ci)
<br>
[![PyPI](https://img.shields.io/pypi/v/typeshed-stats?style=for-the-badge)](https://pypi.org/project/typeshed-stats/)![PyPI - Wheel](https://img.shields.io/pypi/wheel/typeshed-stats?style=for-the-badge)[![license](https://img.shields.io/github/license/AlexWaygood/typeshed-stats?style=for-the-badge)](https://opensource.org/licenses/MIT)

---

<br>
</div>

## What's this project for?

This project is for easy gathering of statistics relating to [typeshed](https://github.com/python/typeshed)'s stubs. As well as being a CLI tool and library, it also powers [a website](https://alexwaygood.github.io/typeshed-stats/) where stats about typeshed's stubs are uploaded twice a day.

This project was created by Alex Waygood. It is not necessarily endorsed by any of the other typeshed maintainers.

Some examples of things you can do from the command line:

- Create a `.csv` file with stats on all typeshed stubs: `typeshed-stats --typeshed-dir <PATH_TO_TYPESHED_CLONE> --to-file stats.csv` (the `.csv` file extension will be automatically detected by the script to identify the format required).
- Pretty-print stats on typeshed stubs for emoji and redis to the terminal, in JSON format: `typeshed-stats --typeshed-dir <PATH_TO_TYPESHED_CLONE> --to-json emoji redis`
- Generate a MarkDown file detailing stats on typeshed's stubs for protobuf and the stdlib: `typeshed-stats --typeshed-dir <PATH_TO_TYPESHED_CLONE> --to-file stats.md stdlib protobuf`

Example usage of the Python-level API:

```python
from typeshed_stats.gather import tmpdir_typeshed, gather_stats

with tmpdir_typeshed() as typeshed:
    stats_on_all_packages = gather_stats_on_multiple_packages(typeshed_dir=typeshed)
```

## How can I use this?

1. Run `pip install typeshed-stats[rich]` to install the package
1. Run `typeshed-stats --help` for information about various options

## Are there any examples of things this script can produce, other than [the website](https://alexwaygood.github.io/typeshed-stats/)?

I'm glad you asked! They're in the `examples/` folder in this repo.
(These examples are generated using the `regenerate.py` script in the `scripts/` directory.)

## How do I run tests/linters?

1. Clone the repo and `cd` into it
1. Create and activate a virtual environment
1. Run `pip install -e .[dev]`
1. Either run the linters/tests individually (see the `.github/workflows` directory for details about what's run in CI) or use the `scripts/runtests.py` convenience script to run them all in succession.
