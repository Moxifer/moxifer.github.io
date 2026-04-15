---
layout: default
title: Baldur's Gate 3 Dialog
---

{% assign dialog_files = site.static_files | where_exp: "file", "file.path contains '/dialog/'" | where_exp: "file", "file.extname == '.html'" | sort: "path" %}

# Baldur's Gate 3 Dialog

<ul>
  {% for file in dialog_files %}
    {% assign label = file.path | remove_first: '/dialog/' | replace: '.html', '' %}
    <li><a href="{{ file.path | relative_url }}">{{ label }}</a></li>
  {% endfor %}
</ul>
