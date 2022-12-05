---
hide:
  - footer
  - navigation
---

<!-- NOTE: This file is generated. Do not edit manually! -->

To install the CLI, simply run `pip install typeshed-stats[rich]`.

```console
usage: typeshed-stats [-h] [--log {NOTSET,DEBUG,INFO,WARNING,ERROR,CRITICAL}]
                      [--pprint | --to-json | --to-csv | --to-markdown | -f WRITEFILE]
                      [-o] (-t TYPESHED_DIR | -d)
                      [packages ...]

Tool to gather stats on typeshed

positional arguments:
  packages              Packages to gather stats on (defaults to all third-
                        party packages, plus the stdlib)

options:
  -h, --help            show this help message and exit
  --log {NOTSET,DEBUG,INFO,WARNING,ERROR,CRITICAL}
                        Specify the level of logging (defaults to
                        logging.INFO)

Output Options:
  --pprint              Pretty-print Python representations of the data
                        (default output)
  --to-json             Print output as JSON to the terminal
  --to-csv              Print output in csv format to the terminal
  --to-markdown         Print output as formatted MarkDown to the terminal
  -f WRITEFILE, --to-file WRITEFILE
                        Write output to WRITEFILE instead of printing to the
                        terminal. The file format will be inferred by the file
                        extension. The file extension must be one of ['.csv',
                        '.json', '.md', '.txt'].
  -o, --overwrite       Overwrite the path passed to `--file` if it already
                        exists (defaults to False)

Typeshed options:
  -t TYPESHED_DIR, --typeshed-dir TYPESHED_DIR
                        Path to a local clone of typeshed, to be used as the
                        basis for analysis
  -d, --download-typeshed
                        Download a fresh copy of typeshed into a temporary
                        directory, and use that as the basis for analysis

```
