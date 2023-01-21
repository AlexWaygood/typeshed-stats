---
hide:
  - navigation
  - toc
  - footer
---

Download the data <a href="../stats_as_csv.csv" title="Download the data as a .csv file">here</a>.

Note: This data is updated twice a day. For up-to-date results, consider using
[the CLI tool][cli-tool] instead.

---

<input type="text" id="statsTableFilterInput" onkeyup="filterTable()" placeholder="Search for packages..">

<table id="statsTable">
  <thead>
    <tr>
      {% for key, val in stats_as_csv[0].items() %}
        {% if is_int(val) %}
          <th data-sort-method="number">{{ key }}</th>
        {% else %}
          <th>{{ key }}</th>
        {% endif %}
      {% endfor %}
    </tr>
  </thead>
  <tbody>
    {% for row in stats_as_csv %}
      <tr>
        {% for val in row.values() %}
          <td>{{ val if is_int(val) else markdown.markdown(val) }}</td>
        {% endfor %}
      </tr>
    {% endfor %}
  </tbody>
</table>
