---
hide:
  - footer
  - navigation
---

<!-- NOTE: This file is generated. Do not edit manually! -->

Tools for gathering stats about typeshed packages.

<hr>

::: typeshed_stats.gather.AnnotationStats
    options:
      show_root_heading: true

**Attributes:**

| Name | Type |
|------|------|
| `annotated_parameters` | [`int`][int] |
| `unannotated_parameters` | [`int`][int] |
| `annotated_returns` | [`int`][int] |
| `unannotated_returns` | [`int`][int] |
| `explicit_Incomplete_parameters` | [`int`][int] |
| `explicit_Incomplete_returns` | [`int`][int] |
| `explicit_Any_parameters` | [`int`][int] |
| `explicit_Any_returns` | [`int`][int] |
| `annotated_variables` | [`int`][int] |
| `explicit_Any_variables` | [`int`][int] |
| `explicit_Incomplete_variables` | [`int`][int] |
| `classdefs` | [`int`][int] |
| `classdefs_with_Any` | [`int`][int] |
| `classdefs_with_Incomplete` | [`int`][int] |

<hr>

::: typeshed_stats.gather.FileInfo
    options:
      show_root_heading: true

**Attributes:**

| Name | Type |
|------|------|
| `file_path` | [`Path`][pathlib.Path] |
| `parent_package` | [`str`][str] |
| `number_of_lines` | [`int`][int] |
| `pyright_setting` | [`PyrightSetting`][typeshed_stats.gather.PyrightSetting] |
| `annotation_stats` | [`AnnotationStats`][typeshed_stats.gather.AnnotationStats] |

<hr>

::: typeshed_stats.gather.PackageInfo
    options:
      show_root_heading: true

**Attributes:**

| Name | Type |
|------|------|
| `package_name` | [`str`][str] |
| `stub_distribution_name` | [`str`][str] |
| `extra_description` | [`str`][str] \| [`None`][None] |
| `number_of_lines` | [`int`][int] |
| `package_status` | [`PackageStatus`][typeshed_stats.gather.PackageStatus] |
| `upload_status` | [`UploadStatus`][typeshed_stats.gather.UploadStatus] |
| `stubtest_settings` | [`StubtestSettings`][typeshed_stats.gather.StubtestSettings] |
| `pyright_setting` | [`PyrightSetting`][typeshed_stats.gather.PyrightSetting] |
| `annotation_stats` | [`AnnotationStats`][typeshed_stats.gather.AnnotationStats] |

<hr>

::: typeshed_stats.gather.PackageName
    options:
      show_root_heading: true

<hr>

::: typeshed_stats.gather.PackageStatus
    options:
      show_root_heading: true

**Members:**

| Name | Description |
|------|-------------|
| `STDLIB` | These are typeshed's stubs for the standard library. Typeshed's stdlib stubs are generally fairly up to date, and are tested against all currently supported Python versions in typeshed's CI. |
| `NOT_ON_PYPI` | The runtime package that these stubs are for doesn't exist on PyPI, so whether or not these stubs are up to date or not is unknown. |
| `OBSOLETE` | The runtime package has added inline type hints; these typeshed stubs are now obsolete. |
| `NO_LONGER_UPDATED` | The runtime package has not added type hints, but these stubs are no longer updated by typeshed for some other reason. |
| `OUT_OF_DATE` | These stubs are out of date. In typeshed's CI, [stubtest][] tests these stubs against an older version of the runtime package than the latest that's available. |
| `UP_TO_DATE` | These stubs should be fairly up to date. In typeshed's CI, [stubtest][] tests these stubs against the latest version of the runtime package that's available. |

<hr>

::: typeshed_stats.gather.PyrightSetting
    options:
      show_root_heading: true

**Members:**

| Name | Description |
|------|-------------|
| `ENTIRELY_EXCLUDED` | All files in this stubs package are excluded from the pyright check in typeshed's CI. |
| `SOME_FILES_EXCLUDED` | Some files in this stubs package are excluded from the pyright check in typeshed's CI. |
| `NOT_STRICT` | All files in this stubs package are excluded from the stricter pyright settings in typeshed's CI. |
| `STRICT_ON_SOME_FILES` | Some files in this stubs package are tested with the stricter pyright settings in typeshed's CI; some are excluded. |
| `STRICT` | All files in this stubs package are tested with the stricter pyright settings in typeshed's CI. |

<hr>

::: typeshed_stats.gather.StubtestSettings
    options:
      show_root_heading: true

**Attributes:**

| Name | Type |
|------|------|
| `strictness` | [`StubtestStrictness`][typeshed_stats.gather.StubtestStrictness] |
| `platforms` | [`list`][list][[`str`][str]] |
| `allowlist_length` | [`int`][int] |

<hr>

::: typeshed_stats.gather.StubtestStrictness
    options:
      show_root_heading: true

**Members:**

| Name | Description |
|------|-------------|
| `SKIPPED` | Stubtest is skipped in typeshed's CI for this package. |
| `MISSING_STUBS_IGNORED` | The `--ignore-missing-stub` stubtest setting is used in typeshed's CI. |
| `ERROR_ON_MISSING_STUB` | Objects missing from the stub cause stubtest to emit an error in typeshed's CI. |

<hr>

::: typeshed_stats.gather.UploadStatus
    options:
      show_root_heading: true

**Members:**

| Name | Description |
|------|-------------|
| `UPLOADED` | These stubs are currently uploaded to PyPI. |
| `NOT_CURRENTLY_UPLOADED` | These stubs are not currently uploaded to PyPI. |

<hr>

::: typeshed_stats.gather.gather_annotation_stats_on_file
    options:
      show_root_heading: true

<hr>

::: typeshed_stats.gather.gather_annotation_stats_on_package
    options:
      show_root_heading: true

<hr>

::: typeshed_stats.gather.gather_stats_on_file
    options:
      show_root_heading: true

<hr>

::: typeshed_stats.gather.gather_stats_on_multiple_packages
    options:
      show_root_heading: true

<hr>

::: typeshed_stats.gather.gather_stats_on_package
    options:
      show_root_heading: true

<hr>

::: typeshed_stats.gather.get_number_of_lines_of_file
    options:
      show_root_heading: true

<hr>

::: typeshed_stats.gather.get_package_extra_description
    options:
      show_root_heading: true

<hr>

::: typeshed_stats.gather.get_package_size
    options:
      show_root_heading: true

<hr>

::: typeshed_stats.gather.get_package_status
    options:
      show_root_heading: true

<hr>

::: typeshed_stats.gather.get_pyright_setting_for_package
    options:
      show_root_heading: true

<hr>

::: typeshed_stats.gather.get_pyright_setting_for_path
    options:
      show_root_heading: true

<hr>

::: typeshed_stats.gather.get_stub_distribution_name
    options:
      show_root_heading: true

<hr>

::: typeshed_stats.gather.get_stubtest_allowlist_length
    options:
      show_root_heading: true

<hr>

::: typeshed_stats.gather.get_stubtest_platforms
    options:
      show_root_heading: true

<hr>

::: typeshed_stats.gather.get_stubtest_settings
    options:
      show_root_heading: true

<hr>

::: typeshed_stats.gather.get_stubtest_strictness
    options:
      show_root_heading: true

<hr>

::: typeshed_stats.gather.get_upload_status
    options:
      show_root_heading: true

<hr>

::: typeshed_stats.gather.tmpdir_typeshed
    options:
      show_root_heading: true
