# Script to gather stats on various things about typeshed

## How to use this?

1. Clone the repo and `cd` into it
2. Create and activate a virtual environment
3. Run `pip install .[everything]`
4. Run `typeshed-stats --help` for information about various options

(You'll need a local clone of typeshed for the script to work properly.)

## What are some things can you do with this script?

Some examples of things you can do from the command line:
- Create a `.csv` file with stats on all typeshed stubs: `typeshed-stats --typeshed-dir <PATH_TO_TYPESHED_CLONE> --to-file stats.csv` (the `.csv` file extension will be automatically detected by the script to identify the format required).
- Pretty-print stats on typeshed stubs for emoji and redis to the terminal, in JSON format: `typeshed-stats --typeshed-dir <PATH_TO_TYPESHED_CLONE> --to-json emoji redis`
- Generate a MarkDown file detailing stats on typeshed's stubs for protobuf and the stdlib: `typeshed-stats --typeshed-dir <PATH_TO_TYPESHED_CLONE> --to-file stats.md stdlib protobuf`

## Are there any examples of things this script can produce?
I'm glad you asked! They're in the `examples/` folder in this repo.
(These examples are generated using the `regenerate_examples.py` script in the repository root.)

## How do I run tests/linters?
1. Create and activate a virtual environment
2. Run `pip install -r requirements-dev.txt`
3. Run `pip install -e .[everything]`
4. Either run the linters/tests individually (see the `.github/workflows` directory for details about what's run in CI) or use the `runtests.py` convenience script to run them all in succession.
