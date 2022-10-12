# Script to gather stats on various things about typeshed

## How to use this?

1. Clone the repo
2. Create and activate a virtual environment
3. Run `pip install requirements.txt`
4. Run `python typeshed_stats.py --help` for information about various options.

(You'll need a local clone of typeshed for the script to work properly.)

## What are some things can you do with this script?

Some examples of things you can do:
- Create a `.csv` file with stats on all typeshed stubs: `python typeshed_stats.py --typeshed-dir <PATH_TO_TYPESHED_CLONE> --to-file stats.csv` (the `.csv` file extension will be automatically detected by the script to identify the format required).
- Pretty-print stats on typeshed stubs for emoji and redis to the terminal, in JSON format: `python typeshed_stats.py --typeshed-dir <PATH_TO_TYPESHED_CLONE> --to-json emoji redis`
- Generate a MarkDown file detailing stats on typeshed's stubs for protobuf and the stdlib: `python typeshed_stats.py --typeshed-dir <PATH_TO_TYPESHED_CLONE> --to-file stats.md stdlib protobuf`

## Are there any examples of things this script can produce?
I'm glad you asked! They're in the `examples/` folder in this repo.

## Are there any tests?
Not yet! TODO!
