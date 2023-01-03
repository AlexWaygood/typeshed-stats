---
hide:
  - navigation
  - footer
---

# Statistics on typeshed's stubs

Typeshed currently contains stubs for {{ num_packages }} packages
(including the stdlib stubs as a "single package"),
for a total of {{ "{:,}".format(num_lines) }} non-empty lines of code.

<i>
Note: these statistics were last updated at: <b>{{ last_update_time }}</b>.
For up-to-date statistics, consider using [the CLI tool][cli-tool] instead.
</i>

<hr>

{{ formatted_stats }}
