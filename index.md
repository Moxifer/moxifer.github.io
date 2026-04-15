---
layout: default
title: BG3 Dialog Browser
---

{% assign dialog_files = site.static_files | where_exp: "file", "file.path contains '/dialog/'" | where_exp: "file", "file.extname == '.html'" | sort: "path" %}

Browse the generated dialog pages below. This landing page is built by GitHub
Pages and updates automatically when a new `.html` file is added under
`dialog/`.

<style>
  .dialog-tools {
    margin: 1.25rem 0 1rem;
  }

  .dialog-tools input {
    width: 100%;
    max-width: 32rem;
    padding: 0.65rem 0.8rem;
    border: 1px solid #c3ccd8;
    border-radius: 0.5rem;
    font: inherit;
  }

  .dialog-count {
    margin: 0 0 1rem;
    color: #4a5565;
  }

  .dialog-list {
    list-style: none;
    margin: 0;
    padding: 0;
    display: grid;
    gap: 0.75rem;
  }

  .dialog-list li {
    border: 1px solid #d8dee8;
    border-radius: 0.75rem;
    padding: 0.85rem 1rem;
    background: #fbfcfe;
  }

  .dialog-list li.hidden {
    display: none;
  }

  .dialog-list a {
    display: inline-block;
    font-weight: 600;
    text-decoration: none;
  }

  .dialog-list a:hover {
    text-decoration: underline;
  }

  .dialog-path {
    margin-top: 0.2rem;
    font-size: 0.92rem;
    color: #5d6a7c;
  }
</style>

<div class="dialog-tools">
  <input
    id="dialog-filter"
    type="search"
    placeholder="Filter dialog names..."
    aria-label="Filter dialog names"
  >
</div>

<p class="dialog-count">
  <strong>{{ dialog_files | size }}</strong> dialog pages available.
</p>

<ul id="dialog-list" class="dialog-list">
  {% for file in dialog_files %}
    {% assign label = file.path | remove_first: '/dialog/' | replace: '.html', '' %}
    <li data-name="{{ label | downcase }}">
      <a href="{{ file.path | relative_url }}">{{ label }}</a>
      <div class="dialog-path">{{ file.path }}</div>
    </li>
  {% endfor %}
</ul>

<script>
  (function () {
    var input = document.getElementById("dialog-filter");
    var items = Array.prototype.slice.call(
      document.querySelectorAll("#dialog-list li")
    );

    if (!input || !items.length) {
      return;
    }

    input.addEventListener("input", function () {
      var query = input.value.trim().toLowerCase();

      items.forEach(function (item) {
        var name = item.getAttribute("data-name") || "";
        item.classList.toggle("hidden", query && name.indexOf(query) === -1);
      });
    });
  })();
</script>
