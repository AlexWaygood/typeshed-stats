---
hide:
  - footer
  - navigation
---

{{ gather.__doc__ }}

{% for name in gather.__all__ %}

<hr>

<a name={{ name }}></a>

::: typeshed_stats.gather.{{ name }}
    options:
      show_root_heading: true

{% if name != "PackageName" %}
{% set obj = gather|attr(name) %}

{% if is_enum(obj) %}
{% set enum = obj %}
__Members:__

| Name | Description |
|------|-------------|

{%- for member in enum %}
| `{{ member.name }}` | {{ member.__doc__ }} |

{%- endfor -%}

{% elif attrs.has(obj) %}
{% set cls = obj %}
__Attributes:__

| Name | Type |
|------|------|

{%- for field in attrs.fields(cls) %}
| `{{ field.name }}` | {{ get_field_description(field.type) }} |

{%- endfor -%}

{% endif %}
{% endif %}
{% endfor %}
