---
hide:
  - footer
  - navigation
  - toc
---
Tools for gathering stats about typeshed packages.
<hr>

## **`AnnotationStats`**

::: typeshed_stats.gather.AnnotationStats

<p><strong>Attributes:</strong></p>
<table>
  <thead>
    <tr>
      <th>Name</th>
      <th>Type</th>
    </tr>
  </thead>
  <tbody>
      <tr>
        <td><code>annotated_parameters</code></td>
        <td><code>int</code></td>
      </tr>
      <tr>
        <td><code>unannotated_parameters</code></td>
        <td><code>int</code></td>
      </tr>
      <tr>
        <td><code>annotated_returns</code></td>
        <td><code>int</code></td>
      </tr>
      <tr>
        <td><code>unannotated_returns</code></td>
        <td><code>int</code></td>
      </tr>
      <tr>
        <td><code>explicit_Incomplete_parameters</code></td>
        <td><code>int</code></td>
      </tr>
      <tr>
        <td><code>explicit_Incomplete_returns</code></td>
        <td><code>int</code></td>
      </tr>
      <tr>
        <td><code>explicit_Any_parameters</code></td>
        <td><code>int</code></td>
      </tr>
      <tr>
        <td><code>explicit_Any_returns</code></td>
        <td><code>int</code></td>
      </tr>
      <tr>
        <td><code>annotated_variables</code></td>
        <td><code>int</code></td>
      </tr>
      <tr>
        <td><code>explicit_Any_variables</code></td>
        <td><code>int</code></td>
      </tr>
      <tr>
        <td><code>explicit_Incomplete_variables</code></td>
        <td><code>int</code></td>
      </tr>

  </tbody>
</table>

<hr>

## **`PackageName`**

::: typeshed_stats.gather.PackageName


<hr>

## **`PackageStats`**

::: typeshed_stats.gather.PackageStats

<p><strong>Attributes:</strong></p>
<table>
  <thead>
    <tr>
      <th>Name</th>
      <th>Type</th>
    </tr>
  </thead>
  <tbody>
      <tr>
        <td><code>package_name</code></td>
        <td><code>str</code></td>
      </tr>
      <tr>
        <td><code>number_of_lines</code></td>
        <td><code>int</code></td>
      </tr>
      <tr>
        <td><code>package_status</code></td>
        <td><code><a class="autorefs autorefs-internal" title="typeshed_stats.gather.PackageStatus" href="#typeshed_stats.gather.PackageStatus">PackageStatus</a></code></td>
      </tr>
      <tr>
        <td><code>stubtest_setting</code></td>
        <td><code><a class="autorefs autorefs-internal" title="typeshed_stats.gather.StubtestSetting" href="#typeshed_stats.gather.StubtestSetting">StubtestSetting</a></code></td>
      </tr>
      <tr>
        <td><code>pyright_setting</code></td>
        <td><code><a class="autorefs autorefs-internal" title="typeshed_stats.gather.PyrightSetting" href="#typeshed_stats.gather.PyrightSetting">PyrightSetting</a></code></td>
      </tr>
      <tr>
        <td><code>annotation_stats</code></td>
        <td><code><a class="autorefs autorefs-internal" title="typeshed_stats.gather.AnnotationStats" href="#typeshed_stats.gather.AnnotationStats">AnnotationStats</a></code></td>
      </tr>

  </tbody>
</table>

<hr>

## **`PackageStatus`**

::: typeshed_stats.gather.PackageStatus

<p><strong>Members:</strong></p>
<table>
  <thead>
    <tr>
      <th>Name</th>
      <th>Description</th>
    </tr>
  </thead>
  <tbody>
      <tr>
        <td><code>STDLIB</code></td>
        <td>These are the stdlib stubs. Typeshed's stdlib stubs are generally fairly up to date, and tested against all currently supported Python versions in CI.</td>
      </tr>
      <tr>
        <td><code>NOT_ON_PYPI</code></td>
        <td>The upstream for this package doesn't exist on PyPI, so whether or not these stubs are up to date or not is unknown.</td>
      </tr>
      <tr>
        <td><code>OBSOLETE</code></td>
        <td>Upstream has added type hints; these typeshed stubs are now obsolete.</td>
      </tr>
      <tr>
        <td><code>NO_LONGER_UPDATED</code></td>
        <td>Upstream has not added type hints, but these stubs are no longer updated for some other reason.</td>
      </tr>
      <tr>
        <td><code>OUT_OF_DATE</code></td>
        <td>These stubs are out of date. In CI, stubtest tests these stubs against an older version of this package than the latest that's available.</td>
      </tr>
      <tr>
        <td><code>UP_TO_DATE</code></td>
        <td>These stubs should be fairly up to date. In CI, stubtest tests these stubs against the latest version of the package that's available.</td>
      </tr>

  </tbody>
</table>

<hr>

## **`PyrightSetting`**

::: typeshed_stats.gather.PyrightSetting

<p><strong>Members:</strong></p>
<table>
  <thead>
    <tr>
      <th>Name</th>
      <th>Description</th>
    </tr>
  </thead>
  <tbody>
      <tr>
        <td><code>ENTIRELY_EXCLUDED</code></td>
        <td>All files are excluded from the pyright check in CI.</td>
      </tr>
      <tr>
        <td><code>SOME_FILES_EXCLUDED</code></td>
        <td>Some files are excluded from the pyright check in CI.</td>
      </tr>
      <tr>
        <td><code>NOT_STRICT</code></td>
        <td>All files are excluded from the stricter pyright settings in CI.</td>
      </tr>
      <tr>
        <td><code>STRICT_ON_SOME_FILES</code></td>
        <td>Some files are tested with the stricter pyright settings in CI; some are excluded.</td>
      </tr>
      <tr>
        <td><code>STRICT</code></td>
        <td>All files are tested with the stricter pyright settings in CI.</td>
      </tr>

  </tbody>
</table>

<hr>

## **`StubtestSetting`**

::: typeshed_stats.gather.StubtestSetting

<p><strong>Members:</strong></p>
<table>
  <thead>
    <tr>
      <th>Name</th>
      <th>Description</th>
    </tr>
  </thead>
  <tbody>
      <tr>
        <td><code>SKIPPED</code></td>
        <td>Stubtest is skipped in CI for this package.</td>
      </tr>
      <tr>
        <td><code>MISSING_STUBS_IGNORED</code></td>
        <td>The `--ignore-missing-stub` stubtest setting is used in CI.</td>
      </tr>
      <tr>
        <td><code>ERROR_ON_MISSING_STUB</code></td>
        <td>Objects missing from the stub cause stubtest to emit an error in CI.</td>
      </tr>

  </tbody>
</table>

<hr>

## **`gather_annotation_stats_on_file`**

::: typeshed_stats.gather.gather_annotation_stats_on_file

<hr>

## **`gather_annotation_stats_on_package`**

::: typeshed_stats.gather.gather_annotation_stats_on_package

<hr>

## **`gather_stats`**

::: typeshed_stats.gather.gather_stats

<hr>

## **`gather_stats_on_package`**

::: typeshed_stats.gather.gather_stats_on_package

<hr>

## **`get_package_size`**

::: typeshed_stats.gather.get_package_size

<hr>

## **`get_package_status`**

::: typeshed_stats.gather.get_package_status

<hr>

## **`get_pyright_setting`**

::: typeshed_stats.gather.get_pyright_setting

<hr>

## **`get_stubtest_setting`**

::: typeshed_stats.gather.get_stubtest_setting

