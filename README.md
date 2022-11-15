<div align=center>

# typeshed-stats

A CLI tool and library to gather stats on typeshed

[![build status](https://github.com/AlexWaygood/typeshed-stats/actions/workflows/check.yml/badge.svg)](https://github.com/AlexWaygood/typeshed-stats/actions/workflows/check.yml)
[![Checked with mypy](http://www.mypy-lang.org/static/mypy_badge.svg)](http://mypy-lang.org/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Imports: isort](https://img.shields.io/badge/%20imports-isort-%231674b1?style=flat&labelColor=ef8336)](https://pycqa.github.io/isort/)

<hr>
<br>
</div>

## What's this project for?

This project is for easy gathering of statistics relating to typeshed's stubs.

Some examples of things you can do from the command line:
- Create a `.csv` file with stats on all typeshed stubs: `typeshed-stats --typeshed-dir <PATH_TO_TYPESHED_CLONE> --to-file stats.csv` (the `.csv` file extension will be automatically detected by the script to identify the format required).
- Pretty-print stats on typeshed stubs for emoji and redis to the terminal, in JSON format: `typeshed-stats --typeshed-dir <PATH_TO_TYPESHED_CLONE> --to-json emoji redis`
- Generate a MarkDown file detailing stats on typeshed's stubs for protobuf and the stdlib: `typeshed-stats --typeshed-dir <PATH_TO_TYPESHED_CLONE> --to-file stats.md stdlib protobuf`

Example usage of the Python-level API:
```python
from typeshed_stats.gather import tmpdir_typeshed, gather_stats

with tmpdir_typeshed() as typeshed:
    stats = gather_stats(typeshed_dir=typeshed)
```

## How can I use this?

1. Run `pip install git+https://github.com/AlexWaygood/typeshed-stats.git#egg=typeshed-stats[everything]` to install the package
2. Run `typeshed-stats --help` for information about various options

## Are there any examples of things this script can produce?
I'm glad you asked! They're in the `examples/` folder in this repo.
(These examples are generated using the `regenerate_examples.py` script in the repository root.)

## How do I run tests/linters?
1. Clone the repo and `cd` into it
2. Create and activate a virtual environment
3. Run `pip install -r requirements-dev.txt`
4. Run `pip install -e .[everything]`
5. Either run the linters/tests individually (see the `.github/workflows` directory for details about what's run in CI) or use the `runtests.py` convenience script to run them all in succession.
