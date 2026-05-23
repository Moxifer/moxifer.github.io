from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html import escape, unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable


TEXT_CLASSES = {"text-line", "dialog"}
SPEAKER_CLASSES = {"speaker-name", "speaker-label"}
SEARCH_CHUNK_CLASSES = {
    "meta-item",
    "preview-note",
    "context-line",
    "checkflag-line",
    "setflag-line",
    "node-line",
    "inline-meta",
    "source",
    "source-text",
    "summary-line",
    "ruletag",
    "flag-group-type",
    "signal-item",
    "signal-heading",
    "end",
}
SEARCH_CHUNK_TAGS = {"h1"}
SKIP_TAGS = {"script", "style"}
IGNORE_CLASSES = {"repeat", "speaker-map"}
SKIP_META_SEARCH_LABELS = {"speaker"}
SKIP_SEARCH_CHUNK_CLASSES = {"signal-heading", "checkflag-line", "setflag-line", "flag-group-type", "end"}
SOURCE_FULLTEXT_LABELS = {"dialog", "timeline", "scene", "synopsis", "how to trigger", "howtotrigger"}
PREVIEW_META_BLOCK_START = "  <!-- dialog-preview-meta:start -->\n"
PREVIEW_META_BLOCK_END = "  <!-- dialog-preview-meta:end -->\n"
PREVIEW_META_RE = re.compile(
    r"\s*<!-- dialog-preview-meta:start -->.*?<!-- dialog-preview-meta:end -->\s*",
    re.DOTALL,
)
FAVICON_BLOCK_START = "  <!-- dialog-favicon:start -->\n"
FAVICON_BLOCK_END = "  <!-- dialog-favicon:end -->\n"
FAVICON_RE = re.compile(
    r"\s*<!-- dialog-favicon:start -->.*?<!-- dialog-favicon:end -->\s*",
    re.DOTALL,
)
PAGE_NAV_BLOCK_START = "      <!-- dialog-page-nav:start -->\n"
PAGE_NAV_BLOCK_END = "      <!-- dialog-page-nav:end -->\n"
PAGE_NAV_RE = re.compile(
    r"\s*<!-- dialog-page-nav:start -->.*?<!-- dialog-page-nav:end -->\s*",
    re.DOTALL,
)
LEGACY_PAGE_NAV_RE = re.compile(
    r"\s*<nav[^>]*class=\"[^\"]*\bpage-nav\b[^\"]*\"[^>]*>.*?</nav>\s*",
    re.DOTALL,
)
HERO_TITLE_RE = re.compile(r"(<header class=\"hero\">\s*)(<h1\b)", re.DOTALL)
NESTED_SUMMARY_RE = re.compile(
    r"(<span class=['\"]nodelink['\"][^>]*>nested=)(?:<a [^>]+>)?([A-Za-z0-9_.-]+)(?:</a>)?(\s*<code>[^<]+</code></span>)"
)
NESTED_META_RE = re.compile(
    r"(<span class=['\"]meta-item['\"]><strong>Nested Target</strong>:\s*)(?:<a [^>]+>)?([A-Za-z0-9_.-]+)(?:</a>)?(\s*\([0-9a-fA-F-]+\)</span>)"
)
NESTED_SUMMARY_TITLE_RE = re.compile(
    r"(<span class=['\"]nodelink['\"][^>]*\btitle=)(['\"])([^'\"]*)(\2)([^>]*>nested=(?:<a [^>]+>)?)([A-Za-z0-9_.-]+)"
)
SYNOPSIS_BLOCK_RE = re.compile(
    r'<div[^>]*class="[^"]*\bsource\b[^"]*\bsource-text\b[^"]*"[^>]*>\s*'
    r'<span[^>]*class="[^"]*\bsource-label\b[^"]*"[^>]*>\s*Synopsis:\s*</span>'
    r"(.*?)</div>",
    re.IGNORECASE | re.DOTALL,
)
DIALOG_SOURCE_RE = re.compile(
    r'<div[^>]*class="[^"]*\bsource\b[^"]*"[^>]*>\s*'
    r'<span[^>]*class="[^"]*\bsource-label\b[^"]*"[^>]*>\s*Dialog:\s*</span>'
    r"(.*?)</div>",
    re.IGNORECASE | re.DOTALL,
)
HTML_TAG_RE = re.compile(r"<[^>]+>")
IDENTIFIER_BOUNDARY_RE = re.compile(
    r"(?<=[a-z])(?=[A-Z])|(?<=[A-Za-z])(?=\d)|(?<=\d)(?=[A-Za-z])"
)
UUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
TEXT_HANDLE_RE = re.compile(
    r"\bh[a-z0-9]{4,}(?:g[a-z0-9]{2,})+\b",
    re.IGNORECASE,
)
FAVICON_BLOCK = (
    FAVICON_BLOCK_START
    + '  <link rel="icon" type="image/x-icon" href="/favicon.ico">\n'
    + '  <link rel="icon" type="image/png" href="/favicon.png">\n'
    + FAVICON_BLOCK_END
)
TARGET_STYLE_BLOCK = """  <style data-search-target-highlight>
    :root {
      color-scheme: dark;
      --ink: #e7edf6;
      --muted: #9ba8bb;
      --line: #2a3748;
      --npc: #ff8a80;
      --player: #8ce5a7;
      --system: #8cb4ff;
      --rule: #78d3a7;
      --tag: #7ddbe6;
      --check: #d0bbff;
      --set: #ffb86b;
      --roll: #c4b5fd;
      --approval: #79e2d0;
      --jump: #9dc2ff;
      --context: #a0acbd;
      --surface: #101822;
      --surface-active: #152132;
      --surface-hover: #1b2940;
      --detail-surface: #142030;
      --detail-border: #324258;
      --focus: #6f8eb4;
      --highlight: #1f3044;
      --scrollbar-proxy-bg: rgba(8, 12, 18, 0.94);
    }
    body {
      background: #0b1117;
      color: var(--ink);
    }
    a {
      color: var(--jump);
    }
    .page,
    .tree-shell,
    .tree-shell-inner,
    .hero,
    .node-detail-panel,
    .section,
    .section-signals,
    .section-metadata {
      background: transparent;
      color: var(--ink);
    }
    .node-summary,
    .node-main,
    .node-main-row,
    .node-previews,
    .summary-line,
    .source,
    .source-text,
    .meta-list,
    .meta-item,
    .signal-heading,
    .signal-scope,
    .signal-item,
    .line-meta,
    .inline-meta {
      color: var(--ink);
    }
    .text-block {
      background: #162131;
      border: 1px solid var(--line);
      box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.03);
    }
    .text-line {
      color: var(--ink);
    }
    .line-meta,
    .inline-meta,
    .signal-scope,
    .meta-item,
    .source,
    .summary-line {
      color: var(--muted);
    }
    .signal-item .asset-id,
    .signal-item .asset-state,
    .meta-item code,
    .line-meta code,
    .source code {
      color: var(--muted);
    }
    .rule-op {
      color: #90a0b5;
    }
    .context-line .signal-item {
      color: var(--muted);
    }
    .missing,
    .cycle {
      color: #ff9d9d;
      background: rgba(139, 30, 30, 0.15);
    }
    .toolbar {
      background: rgba(11, 17, 23, 0.96);
      border-bottom-color: var(--line);
      backdrop-filter: blur(8px);
    }
    .speaker-map ul {
      background: #0f1822;
      border-color: var(--line);
      box-shadow: 0 12px 32px rgba(0, 0, 0, 0.45);
    }
    .tree-toggle-marker {
      cursor: pointer;
      user-select: none;
    }
    .page-nav {
      margin-bottom: 0.45rem;
      padding-bottom: 0.3rem;
      border-bottom: 1px solid var(--line);
      font-size: 0.9rem;
    }
    .page-nav a {
      color: var(--muted);
      text-decoration: none;
    }
    .page-nav a:hover,
    .page-nav a:focus-visible {
      color: var(--jump);
      text-decoration: underline;
    }
    .node-shell:target {
      outline: 3px solid #f0bd58;
      background: rgba(240, 189, 88, 0.12);
      scroll-margin-top: 1rem;
    }
    .search-target-line {
      background: rgba(240, 189, 88, 0.18);
      border-radius: 2px;
    }
    .text-line.search-target-line,
    .meta-item.search-target-line,
    .preview-note.search-target-line,
    .context-line.search-target-line,
    .checkflag-line.search-target-line,
    .setflag-line.search-target-line,
    .source.search-target-line,
    .summary-line.search-target-line,
    .inline-meta.search-target-line {
      padding: 0 0.08rem;
    }
  </style>
"""
TARGET_STYLE_RE = re.compile(
    r"\s*<style data-search-target-highlight>.*?</style>\s*",
    re.DOTALL,
)
TARGET_LINE_SCRIPT_BLOCK = """  <script data-search-target-line>
    (function () {
      const params = new URLSearchParams(window.location.search);
      const targetLine = params.get("line");
      const targetHash = window.location.hash;

      if (!targetLine) {
        return;
      }

      const normalize = (value) =>
        (value || "")
          .toLowerCase()
          .normalize("NFKD")
          .replace(/[\\u0300-\\u036f]/g, "")
          .replace(/\\s+/g, " ")
          .trim();

      const normalizedTargetLine = normalize(targetLine);
      if (!normalizedTargetLine) {
        return;
      }

      const candidateSelector = [
        ".text-line",
        ".dialog",
        ".meta-item",
        ".preview-note",
        ".context-line",
        ".checkflag-line",
        ".setflag-line",
        ".source",
        ".summary-line",
        ".inline-meta",
        ".flag-group-type",
        ".signal-item",
        ".signal-heading",
        ".speaker-name",
        ".speaker-label",
        ".end",
        "h1"
      ].join(", ");

      const candidateRoots = [];
      let targetShell = null;
      if (targetHash) {
        targetShell = document.querySelector(targetHash);
        if (!targetShell) {
          return;
        }
        if (typeof openParents === "function") {
          openParents(targetShell);
        }
        if (typeof setDetailOpen === "function") {
          setDetailOpen(targetShell, true);
        }
        candidateRoots.push(targetShell);
      } else {
        const hero = document.querySelector(".hero");
        if (hero) {
          candidateRoots.push(hero);
        }
        if (document.body) {
          candidateRoots.push(document.body);
        }
      }

      let matchingLine = null;
      for (const root of candidateRoots) {
        const lineElements = Array.from(root.querySelectorAll(candidateSelector));
        matchingLine = lineElements.find((element) => {
          const lineText = normalize(element.textContent);
          return (
            lineText === normalizedTargetLine ||
            lineText.includes(normalizedTargetLine) ||
            normalizedTargetLine.includes(lineText)
          );
        });
        if (matchingLine) {
          break;
        }
      }

      if (!matchingLine) {
        return;
      }

      matchingLine.classList.add("search-target-line");
      requestAnimationFrame(() => {
        matchingLine.scrollIntoView({ block: "center" });
      });
    })();
  </script>
"""
TARGET_LINE_SCRIPT_RE = re.compile(
    r"\s*<script data-search-target-line>.*?</script>\s*",
    re.DOTALL,
)
TREE_TOGGLE_CLICK_TARGET = """      const link = event.target.closest("a[href^='#node-']");
      if (link) {
        event.preventDefault();
        const target = document.querySelector(link.getAttribute("href"));
        if (target) {
          revealAndFocusNodeTarget(target, link.getAttribute("href"));
        }
        return;
      }
      const summary = event.target.closest(".node-summary");
"""
TREE_TOGGLE_CLICK_REPLACEMENT = """      const link = event.target.closest("a[href^='#node-']");
      if (link) {
        event.preventDefault();
        const target = document.querySelector(link.getAttribute("href"));
        if (target) {
          revealAndFocusNodeTarget(target, link.getAttribute("href"));
        }
        return;
      }
      const marker = event.target.closest(".tree-toggle-marker[data-branch-target]");
      if (marker) {
        const isOpen = marker.dataset.branchExpanded === "true";
        setBranchOpen(marker, !isOpen);
        if (isOpen) {
          const shell = marker.closest(".node-shell");
          if (shell) {
            const panel = getNodeDetailPanel(shell);
            if (panel && !panel.hasAttribute("hidden")) {
              setDetailOpen(shell, false);
            }
          }
        }
        return;
      }
      const summary = event.target.closest(".node-summary");
"""
TREE_TOGGLE_MARKER_STYLE_TARGET = """    .speaker-map ul {
      background: #0f1822;
      border-color: var(--line);
      box-shadow: 0 12px 32px rgba(0, 0, 0, 0.45);
    }
    .page-nav {
"""
TREE_TOGGLE_MARKER_STYLE_REPLACEMENT = """    .speaker-map ul {
      background: #0f1822;
      border-color: var(--line);
      box-shadow: 0 12px 32px rgba(0, 0, 0, 0.45);
    }
    .tree-toggle-marker {
      cursor: pointer;
      user-select: none;
    }
    .page-nav {
"""


def clean_text(value: str) -> str:
    return " ".join(value.split())


def normalize_speaker(value: str) -> str:
    value = clean_text(value)
    if value.startswith("(") and value.endswith(")"):
        inner = clean_text(value[1:-1])
        if inner:
            return inner
    return value


def unique(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def split_label_value(value: str) -> tuple[str, str]:
    value = clean_text(value)
    if not value:
        return "", ""
    label, separator, remainder = value.partition(":")
    if not separator:
        return "", value
    return clean_text(label).casefold(), clean_text(remainder)


def extract_uuid_and_handle_tokens(value: str) -> list[str]:
    return unique([*UUID_RE.findall(value), *TEXT_HANDLE_RE.findall(value)])


def extract_signal_item_values(value: str) -> list[str]:
    value = clean_text(value)
    if not value:
        return []

    signal_name = re.sub(r"\s*\{[0-9a-fA-F-]+\}", "", value)
    signal_name = re.sub(r"\s*\([0-9a-fA-F-]+\)", "", signal_name)
    signal_name = re.sub(r"\s*=\s*(?:True|False)\b.*$", "", signal_name, flags=re.IGNORECASE)
    signal_name = clean_text(signal_name)

    chunks: list[str] = []
    if signal_name:
        chunks.append(signal_name)
    chunks.extend(extract_uuid_and_handle_tokens(value))
    return unique(chunks)


def extract_search_values(class_names: set[str], value: str) -> list[str]:
    value = clean_text(value)
    if not value:
        return []

    if SKIP_SEARCH_CHUNK_CLASSES & class_names:
        return []

    if "signal-item" in class_names:
        return extract_signal_item_values(value)

    if "meta-item" in class_names:
        label, remainder = split_label_value(value)
        if label in SKIP_META_SEARCH_LABELS:
            return []
        return extract_uuid_and_handle_tokens(remainder or value)

    if "source" in class_names or "source-text" in class_names:
        label, remainder = split_label_value(value)
        if label in SKIP_META_SEARCH_LABELS:
            return []
        if label in SOURCE_FULLTEXT_LABELS and remainder:
            chunks = [remainder]
            chunks.extend(extract_uuid_and_handle_tokens(remainder))
            return unique(chunks)
        if "uuid" in label or "handle" in label:
            return extract_uuid_and_handle_tokens(remainder or value)
        return [remainder] if remainder else [value]

    return [value]


def humanize_identifier(value: str) -> str:
    value = value.replace("\\", " ").replace("/", " ")
    value = value.replace("_", " ").replace("-", " ")
    value = IDENTIFIER_BOUNDARY_RE.sub(" ", value)
    return clean_text(value)


def build_dialog_target_lookup(
    repo_root: Path, html_files: list[Path]
) -> dict[str, dict[str, str]]:
    stem_to_entries: dict[str, list[tuple[str, str]]] = {}
    for html_path in html_files:
        relative_path = html_path.relative_to(repo_root).as_posix()
        dialog_source = extract_dialog_source_path(
            html_path.read_text(encoding="utf-8")
        )
        stem_to_entries.setdefault(html_path.stem, []).append(
            (relative_path, dialog_source)
        )

    target_lookup: dict[str, dict[str, str]] = {}
    for stem, entries in stem_to_entries.items():
        if len(entries) != 1:
            continue
        relative_path, dialog_source = entries[0]
        target_lookup[stem] = {"href": f"/{relative_path}"}
        if dialog_source:
            target_lookup[stem]["dialog_source"] = dialog_source
    return target_lookup


def link_nested_dialog_targets(
    html_text: str, dialog_target_lookup: dict[str, dict[str, str]]
) -> str:
    def replace_nested_summary(match: re.Match[str]) -> str:
        target_name = match.group(2)
        target_info = dialog_target_lookup.get(target_name)
        if not target_info:
            return match.group(0)
        href = target_info["href"]
        linked_name = f'<a href="{escape(href, quote=True)}">{escape(target_name)}</a>'
        return f"{match.group(1)}{linked_name}{match.group(3)}"

    def replace_nested_meta(match: re.Match[str]) -> str:
        target_name = match.group(2)
        target_info = dialog_target_lookup.get(target_name)
        if not target_info:
            return match.group(0)
        href = target_info["href"]
        linked_name = f'<a href="{escape(href, quote=True)}">{escape(target_name)}</a>'
        return f"{match.group(1)}{linked_name}{match.group(3)}"

    def replace_nested_summary_title(match: re.Match[str]) -> str:
        target_name = match.group(6)
        target_info = dialog_target_lookup.get(target_name)
        dialog_source = target_info.get("dialog_source") if target_info else ""
        if not dialog_source:
            return match.group(0)
        return (
            f"{match.group(1)}{match.group(2)}"
            f"{escape(dialog_source, quote=True)}"
            f"{match.group(4)}{match.group(5)}{match.group(6)}"
        )

    html_text = NESTED_SUMMARY_RE.sub(replace_nested_summary, html_text)
    html_text = NESTED_META_RE.sub(replace_nested_meta, html_text)
    html_text = NESTED_SUMMARY_TITLE_RE.sub(replace_nested_summary_title, html_text)
    return html_text


def extract_synopsis(html_text: str) -> str:
    match = SYNOPSIS_BLOCK_RE.search(html_text)
    if not match:
        return ""
    synopsis_html = match.group(1)
    synopsis_text = HTML_TAG_RE.sub(" ", synopsis_html)
    return clean_text(unescape(synopsis_text))


def extract_dialog_source_path(html_text: str) -> str:
    match = DIALOG_SOURCE_RE.search(html_text)
    if not match:
        return ""
    dialog_html = match.group(1)
    dialog_text = HTML_TAG_RE.sub(" ", dialog_html)
    return clean_text(unescape(dialog_text))


def build_preview_meta_block(title: str, synopsis: str) -> str:
    safe_title = escape(title, quote=True)
    safe_synopsis = escape(synopsis, quote=True)
    return (
        PREVIEW_META_BLOCK_START
        + f'  <meta name="description" content="{safe_synopsis}">\n'
        + '  <meta property="og:type" content="article">\n'
        + f'  <meta property="og:title" content="{safe_title}">\n'
        + f'  <meta property="og:description" content="{safe_synopsis}">\n'
        + '  <meta name="twitter:card" content="summary">\n'
        + f'  <meta name="twitter:title" content="{safe_title}">\n'
        + f'  <meta name="twitter:description" content="{safe_synopsis}">\n'
        + PREVIEW_META_BLOCK_END
    )


@dataclass
class DialogParseResult:
    title: str = ""
    synopsis: str = ""
    speakers: list[str] = field(default_factory=list)
    search_chunks: list[str] = field(default_factory=list)
    nodes: list["DialogNode"] = field(default_factory=list)


@dataclass
class DialogNode:
    node_id: str
    texts: list[str] = field(default_factory=list)
    speakers: list[str] = field(default_factory=list)
    search_chunks: list[str] = field(default_factory=list)


class DialogHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.result = DialogParseResult()
        self._capture_stack: list[dict[str, object]] = []
        self._ignore_stack: list[str] = []
        self._node_depths: list[int] = []
        self._node_stack: list[DialogNode] = []
        self._skip_depth = 0

    def _close_node_depth(self) -> None:
        if self._node_depths:
            self._node_depths[-1] -= 1
            if self._node_depths[-1] == 0:
                self._node_depths.pop()
                self._node_stack.pop()

    def _append_search_chunk(self, class_names: set[str], value: str) -> None:
        values = extract_search_values(class_names, value)
        if not values:
            return
        if self._node_stack:
            self._node_stack[-1].search_chunks.extend(values)
            return
        self.result.search_chunks.extend(values)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._node_depths:
            self._node_depths[-1] += 1

        if tag in SKIP_TAGS:
            self._skip_depth += 1
            return

        if self._skip_depth:
            return

        attr_map = {name: value or "" for name, value in attrs}
        class_names = set(attr_map.get("class", "").split())
        node_id = attr_map.get("id", "")

        if "node-shell" in class_names and node_id.startswith("node-"):
            node = DialogNode(node_id=node_id)
            self.result.nodes.append(node)
            self._node_stack.append(node)
            self._node_depths.append(1)

        if IGNORE_CLASSES & class_names:
            self._ignore_stack.append(tag)
            return

        if self._ignore_stack:
            return

        if tag == "title":
            self._capture_stack.append(
                {"tag": tag, "kind": "title", "parts": [], "classes": class_names}
            )
            return

        if TEXT_CLASSES & class_names:
            self._capture_stack.append(
                {"tag": tag, "kind": "text", "parts": [], "classes": class_names}
            )
            return

        if SPEAKER_CLASSES & class_names:
            self._capture_stack.append(
                {"tag": tag, "kind": "speaker", "parts": [], "classes": class_names}
            )
            return

        if SEARCH_CHUNK_CLASSES & class_names or tag in SEARCH_CHUNK_TAGS:
            self._capture_stack.append(
                {"tag": tag, "kind": "chunk", "parts": [], "classes": class_names}
            )

    def handle_endtag(self, tag: str) -> None:
        if tag in SKIP_TAGS:
            if self._skip_depth:
                self._skip_depth -= 1
            self._close_node_depth()
            return

        if self._ignore_stack:
            if self._ignore_stack[-1] == tag:
                self._ignore_stack.pop()
            self._close_node_depth()
            return

        if self._skip_depth or not self._capture_stack:
            self._close_node_depth()
            return

        current = self._capture_stack[-1]
        if current["tag"] != tag:
            self._close_node_depth()
            return

        self._capture_stack.pop()
        value = clean_text("".join(current["parts"]))
        if not value:
            self._close_node_depth()
            return

        kind = current["kind"]
        if kind == "title":
            self.result.title = value
        elif kind == "text":
            if self._node_stack:
                self._node_stack[-1].texts.append(value)
                self._node_stack[-1].search_chunks.append(value)
            else:
                self.result.search_chunks.append(value)
        elif kind == "speaker":
            speaker = normalize_speaker(value)
            if self._node_stack:
                self._node_stack[-1].speakers.append(speaker)
        elif kind == "chunk":
            self._append_search_chunk(set(current.get("classes", set())), value)

        self._close_node_depth()

    def handle_data(self, data: str) -> None:
        if self._skip_depth or self._ignore_stack or not self._capture_stack:
            return
        self._capture_stack[-1]["parts"].append(data)


def build_page_nav_block(search_page_href: str) -> str:
    safe_href = escape(search_page_href, quote=True)
    return (
        PAGE_NAV_BLOCK_START
        + f'      <nav class="page-nav"><a href="{safe_href}">Search All Dialog</a></nav>\n'
        + PAGE_NAV_BLOCK_END
    )


def ensure_dialog_page_features(
    html_text: str, title: str, synopsis: str, search_page_href: str
) -> str:
    cleaned = PREVIEW_META_RE.sub("\n", html_text)
    cleaned = FAVICON_RE.sub("\n", cleaned)
    cleaned = TARGET_STYLE_RE.sub("\n", cleaned)
    cleaned = TARGET_LINE_SCRIPT_RE.sub("\n", cleaned)
    cleaned = PAGE_NAV_RE.sub("\n", cleaned)
    cleaned = LEGACY_PAGE_NAV_RE.sub("\n", cleaned)
    if "</head>" not in cleaned:
        return cleaned
    preview_meta_block = build_preview_meta_block(title=title, synopsis=synopsis)
    cleaned = cleaned.replace(
        "</head>",
        f"{preview_meta_block}{FAVICON_BLOCK}{TARGET_STYLE_BLOCK}</head>",
        1,
    )
    page_nav_block = build_page_nav_block(search_page_href)
    cleaned = HERO_TITLE_RE.sub(rf"\1{page_nav_block}      \2", cleaned, count=1)
    if "</body>" in cleaned:
        cleaned = cleaned.replace("</body>", f"{TARGET_LINE_SCRIPT_BLOCK}</body>", 1)
    return cleaned


def patch_tree_toggle_marker_behavior(html_text: str) -> str:
    if TREE_TOGGLE_CLICK_REPLACEMENT in html_text:
        return html_text
    return html_text.replace(
        TREE_TOGGLE_CLICK_TARGET,
        TREE_TOGGLE_CLICK_REPLACEMENT,
        1,
    )


def patch_tree_toggle_marker_style(html_text: str) -> str:
    if ".tree-toggle-marker {" in html_text:
        return html_text
    return html_text.replace(
        TREE_TOGGLE_MARKER_STYLE_TARGET,
        TREE_TOGGLE_MARKER_STYLE_REPLACEMENT,
        1,
    )


def parse_dialog_html(html_text: str) -> DialogParseResult:
    parser = DialogHTMLParser()
    parser.feed(html_text)
    parser.close()
    parser.result.synopsis = extract_synopsis(html_text)
    parser.result.search_chunks = unique(parser.result.search_chunks)
    all_speakers: list[str] = []
    for node in parser.result.nodes:
        node.texts = unique(node.texts)
        node.speakers = unique(node.speakers)
        node.search_chunks = unique(node.search_chunks)
        all_speakers.extend(node.speakers)
    parser.result.speakers = unique(all_speakers)
    return parser.result


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )


def build_index(
    repo_root: Path,
    dialog_root: Path,
    output_path: Path,
    manifest_output_path: Path,
) -> dict:
    documents: list[dict[str, object]] = []
    manifest_documents: list[dict[str, object]] = []
    all_speakers: set[str] = set()

    html_files = sorted(dialog_root.rglob("*.html"))
    dialog_target_lookup = build_dialog_target_lookup(repo_root, html_files)
    for html_path in html_files:
        html_text = html_path.read_text(encoding="utf-8")
        parsed = parse_dialog_html(html_text)
        title = parsed.title or html_path.stem
        search_page_href = Path(
            os.path.relpath(repo_root / "index.html", html_path.parent)
        ).as_posix()
        patched_html = ensure_dialog_page_features(
            html_text,
            title=title,
            synopsis=parsed.synopsis,
            search_page_href=search_page_href,
        )
        patched_html = link_nested_dialog_targets(patched_html, dialog_target_lookup)
        patched_html = patch_tree_toggle_marker_style(patched_html)
        patched_html = patch_tree_toggle_marker_behavior(patched_html)
        if patched_html != html_text:
            html_path.write_text(patched_html, encoding="utf-8")

        relative_path = html_path.relative_to(repo_root).as_posix()
        nodes = []
        for node in parsed.nodes:
            nodes.append(
                {
                    "id": node.node_id,
                    "speakers": node.speakers,
                    "chunks": node.search_chunks,
                }
            )

        document_search_chunks = unique(
            [
                title,
                humanize_identifier(title),
                relative_path,
                humanize_identifier(relative_path),
                html_path.stem,
                humanize_identifier(html_path.stem),
                *parsed.search_chunks,
            ]
        )
        manifest_document = {
            "path": relative_path,
            "title": title,
            "speakers": parsed.speakers,
            "size_bytes": html_path.stat().st_size,
        }
        document = {
            **manifest_document,
            "search_chunks": document_search_chunks,
            "nodes": nodes,
        }
        manifest_documents.append(manifest_document)
        documents.append(document)
        all_speakers.update(parsed.speakers)

    generated_at = datetime.now(timezone.utc).isoformat()
    speakers = sorted(all_speakers, key=lambda value: value.casefold())
    manifest = {
        "generated_at": generated_at,
        "dialog_count": len(manifest_documents),
        "speakers": speakers,
        "documents": manifest_documents,
    }
    index = {
        "generated_at": generated_at,
        "dialog_count": len(documents),
        "speakers": speakers,
        "documents": documents,
    }

    write_json(manifest_output_path, manifest)
    write_json(output_path, index)
    return index


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a static search index for dialog HTML exports."
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root. Defaults to the parent of this script directory.",
    )
    parser.add_argument(
        "--dialog-root",
        type=Path,
        default=None,
        help="Dialog HTML root. Defaults to <repo-root>/dialog.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output JSON path. Defaults to <repo-root>/search-index.json.",
    )
    parser.add_argument(
        "--manifest-output",
        type=Path,
        default=None,
        help="Output JSON path. Defaults to <repo-root>/dialog-manifest.json.",
    )
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    dialog_root = (args.dialog_root or (repo_root / "dialog")).resolve()
    output_path = (args.output or (repo_root / "search-index.json")).resolve()
    manifest_output_path = (
        args.manifest_output or (repo_root / "dialog-manifest.json")
    ).resolve()

    if not dialog_root.is_dir():
        raise SystemExit(f"Dialog root does not exist: {dialog_root}")

    index = build_index(
        repo_root=repo_root,
        dialog_root=dialog_root,
        output_path=output_path,
        manifest_output_path=manifest_output_path,
    )
    print(f"Indexed {index['dialog_count']} dialog files into {output_path}")
    print(f"Wrote dialog manifest to {manifest_output_path}")
    print(f"Speakers: {len(index['speakers'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
