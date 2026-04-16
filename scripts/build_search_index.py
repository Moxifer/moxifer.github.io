from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable


TEXT_CLASSES = {"text-line", "dialog"}
SPEAKER_CLASSES = {"speaker-name", "speaker-label"}
SKIP_TAGS = {"script", "style"}
IGNORE_CLASSES = {"repeat"}
TARGET_STYLE_BLOCK = """  <style data-search-target-highlight>
    .node-shell:target {
      outline: 3px solid #c68b00;
      background: #fff7db;
      scroll-margin-top: 1rem;
    }
    .text-line.search-target-line {
      background: #fff0a6;
      border-radius: 2px;
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

      if (!targetLine || !targetHash) {
        return;
      }

      const targetShell = document.querySelector(targetHash);
      if (!targetShell) {
        return;
      }

      if (typeof openParents === "function") {
        openParents(targetShell);
      }
      if (typeof setDetailOpen === "function") {
        setDetailOpen(targetShell, true);
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

      const lineElements = Array.from(targetShell.querySelectorAll(".text-line"));
      const matchingLine = lineElements.find((element) => {
        const lineText = normalize(element.textContent);
        return (
          lineText === normalizedTargetLine ||
          lineText.includes(normalizedTargetLine) ||
          normalizedTargetLine.includes(lineText)
        );
      });

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


@dataclass
class DialogParseResult:
    title: str = ""
    speakers: list[str] = field(default_factory=list)
    nodes: list["DialogNode"] = field(default_factory=list)


@dataclass
class DialogNode:
    node_id: str
    texts: list[str] = field(default_factory=list)
    speakers: list[str] = field(default_factory=list)


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
            self._capture_stack.append({"tag": tag, "kind": "title", "parts": []})
            return

        if TEXT_CLASSES & class_names:
            self._capture_stack.append({"tag": tag, "kind": "text", "parts": []})
            return

        if SPEAKER_CLASSES & class_names:
            self._capture_stack.append({"tag": tag, "kind": "speaker", "parts": []})

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
        elif kind == "speaker" and self._node_stack:
            self._node_stack[-1].speakers.append(normalize_speaker(value))

        self._close_node_depth()

    def handle_data(self, data: str) -> None:
        if self._skip_depth or self._ignore_stack or not self._capture_stack:
            return
        self._capture_stack[-1]["parts"].append(data)


def ensure_target_highlight(html_text: str) -> str:
    cleaned = TARGET_STYLE_RE.sub("\n", html_text)
    cleaned = TARGET_LINE_SCRIPT_RE.sub("\n", cleaned)
    if "</head>" not in cleaned:
        return cleaned
    cleaned = cleaned.replace("</head>", f"{TARGET_STYLE_BLOCK}</head>", 1)
    if "</body>" in cleaned:
        cleaned = cleaned.replace("</body>", f"{TARGET_LINE_SCRIPT_BLOCK}</body>", 1)
    return cleaned


def parse_dialog_html(html_text: str) -> DialogParseResult:
    parser = DialogHTMLParser()
    parser.feed(html_text)
    parser.close()
    all_speakers: list[str] = []
    for node in parser.result.nodes:
        node.texts = unique(node.texts)
        node.speakers = unique(node.speakers)
        all_speakers.extend(node.speakers)
    parser.result.speakers = unique(all_speakers)
    return parser.result


def build_index(repo_root: Path, dialog_root: Path, output_path: Path) -> dict:
    documents: list[dict[str, object]] = []
    all_speakers: set[str] = set()

    html_files = sorted(dialog_root.rglob("*.html"))
    for html_path in html_files:
        html_text = html_path.read_text(encoding="utf-8")
        patched_html = ensure_target_highlight(html_text)
        if patched_html != html_text:
            html_path.write_text(patched_html, encoding="utf-8")

        parsed = parse_dialog_html(patched_html)
        relative_path = html_path.relative_to(repo_root).as_posix()
        title = parsed.title or html_path.stem
        nodes = []
        for node in parsed.nodes:
            nodes.append(
                {
                    "id": node.node_id,
                    "speakers": node.speakers,
                    "lines": node.texts,
                }
            )

        document = {
            "path": relative_path,
            "title": title,
            "speakers": parsed.speakers,
            "size_bytes": html_path.stat().st_size,
            "nodes": nodes,
        }
        documents.append(document)
        all_speakers.update(parsed.speakers)

    index = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dialog_count": len(documents),
        "speakers": sorted(all_speakers, key=lambda value: value.casefold()),
        "documents": documents,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(index, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
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
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    dialog_root = (args.dialog_root or (repo_root / "dialog")).resolve()
    output_path = (args.output or (repo_root / "search-index.json")).resolve()

    if not dialog_root.is_dir():
        raise SystemExit(f"Dialog root does not exist: {dialog_root}")

    index = build_index(repo_root=repo_root, dialog_root=dialog_root, output_path=output_path)
    print(f"Indexed {index['dialog_count']} dialog files into {output_path}")
    print(f"Speakers: {len(index['speakers'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
