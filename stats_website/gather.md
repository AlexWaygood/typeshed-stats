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

| Name                             | Type   |
|----------------------------------|--------|
| `annotated_parameters`           | `int`  |
| `unannotated_parameters`         | `int`  |
| `annotated_returns`              | `int`  |
| `unannotated_returns`            | `int`  |
| `explicit_Incomplete_parameters` | `int`  |
| `explicit_Incomplete_returns`    | `int`  |
| `explicit_Any_parameters`        | `int`  |
| `explicit_Any_returns`           | `int`  |
| `annotated_variables`            | `int`  |
| `explicit_Any_variables`         | `int`  |
| `explicit_Incomplete_variables`  | `int`  |
<hr>

::: typeshed_stats.gather.PackageInfo
    options:
      show_root_heading: true

**Attributes:**

| Name                 | Type                                                       |
|----------------------|------------------------------------------------------------|
| `package_name`       | `str`                                                      |
| `extra_description`  | `str | None`                                               |
| `number_of_lines`    | `int`                                                      |
| `package_status`     | [`PackageStatus`][typeshed_stats.gather.PackageStatus]     |
| `upload_status`      | [`UploadStatus`][typeshed_stats.gather.UploadStatus]       |
| `stubtest_setting`   | [`StubtestSetting`][typeshed_stats.gather.StubtestSetting] |
| `stubtest_platforms` | `list[str]`                                                |
| `pyright_setting`    | [`PyrightSetting`][typeshed_stats.gather.PyrightSetting]   |
| `annotation_stats`   | [`AnnotationStats`][typeshed_stats.gather.AnnotationStats] |
<hr>

::: typeshed_stats.gather.PackageName
    options:
      show_root_heading: true

<hr>

::: typeshed_stats.gather.PackageStatus
    options:
      show_root_heading: true

**Members:**

| Name                | Description                                                                                                                                            |
|---------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------|
| `STDLIB`            | These are the stdlib stubs. Typeshed's stdlib stubs are generally fairly up to date, and tested against all currently supported Python versions in CI. |
| `NOT_ON_PYPI`       | The upstream for this package doesn't exist on PyPI, so whether or not these stubs are up to date or not is unknown.                                   |
| `OBSOLETE`          | Upstream has added type hints; these typeshed stubs are now obsolete.                                                                                  |
| `NO_LONGER_UPDATED` | Upstream has not added type hints, but these stubs are no longer updated for some other reason.                                                        |
| `OUT_OF_DATE`       | These stubs are out of date. In CI, stubtest tests these stubs against an older version of this package than the latest that's available.              |
| `UP_TO_DATE`        | These stubs should be fairly up to date. In CI, stubtest tests these stubs against the latest version of the package that's available.                 |
<hr>

::: typeshed_stats.gather.PyrightSetting
    options:
      show_root_heading: true

**Members:**

| Name                   | Description                                                                        |
|------------------------|------------------------------------------------------------------------------------|
| `ENTIRELY_EXCLUDED`    | All files are excluded from the pyright check in CI.                               |
| `SOME_FILES_EXCLUDED`  | Some files are excluded from the pyright check in CI.                              |
| `NOT_STRICT`           | All files are excluded from the stricter pyright settings in CI.                   |
| `STRICT_ON_SOME_FILES` | Some files are tested with the stricter pyright settings in CI; some are excluded. |
| `STRICT`               | All files are tested with the stricter pyright settings in CI.                     |
<hr>

::: typeshed_stats.gather.StubtestSetting
    options:
      show_root_heading: true

**Members:**

| Name                    | Description                                                          |
|-------------------------|----------------------------------------------------------------------|
| `SKIPPED`               | Stubtest is skipped in CI for this package.                          |
| `MISSING_STUBS_IGNORED` | The `--ignore-missing-stub` stubtest setting is used in CI.          |
| `ERROR_ON_MISSING_STUB` | Objects missing from the stub cause stubtest to emit an error in CI. |
<hr>

::: typeshed_stats.gather.UploadStatus
    options:
      show_root_heading: true

**Members:**

| Name                     | Description                                     |
|--------------------------|-------------------------------------------------|
| `UPLOADED`               | These stubs are currently uploaded to PyPI.     |
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

::: typeshed_stats.gather.gather_stats
    options:
      show_root_heading: true

<hr>

::: typeshed_stats.gather.gather_stats_on_package
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

::: typeshed_stats.gather.get_pyright_setting
    options:
      show_root_heading: true

<hr>

::: typeshed_stats.gather.get_stubtest_platforms
    options:
      show_root_heading: true

<hr>

::: typeshed_stats.gather.get_stubtest_setting
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
