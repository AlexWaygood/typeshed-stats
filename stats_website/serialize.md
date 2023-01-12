---
hide:
  - footer
  - navigation
---

{{ serialize.__doc__ }}

{% for name in serialize.__all__ %}

<hr>

<a name={{ name }}></a>

::: typeshed_stats.serialize.{{ name }}
    options:
      show_root_heading: true

{% endfor %}
