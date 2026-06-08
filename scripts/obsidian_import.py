#!/usr/bin/env python3
"""Import an Obsidian note into docs/ as Zensical-ready Markdown.

What it does (mechanical transforms only):
- Strips Obsidian-only frontmatter keys (tags / aliases / cssclasses / title).
- Keeps `date` if present; moves `title` to an H1 at the top of the body.
- Rewrites `![[Attachment/X|n]]` to `![stem](../assets/<topic-slug>/<slug>.ext)`
  and copies the referenced file into docs/assets/<topic-slug>/<slug>.ext
  under an ASCII-friendly filename.
- Rewrites `[[Note]]` / `[[Note|Display]]` to `[Display](../Note/)`
  (URL-encoded path). `[[foo.pdf#page=2|Text]]` becomes plain text "Text".
- Converts Obsidian callouts to Material admonitions:
    > [!abstract] title   ->   !!! abstract "title"
    > [!note]- title      ->   ??? note "title"       (collapsed)
    > [!example]+ title   ->   ???+ example "title"   (expanded)
- Leaves math inline; site-wide MathJax lives in docs/javascripts/extra.js.

What it does NOT do (leave these to the human):
- Create or edit docs/<topic>/index.md (list and one-line summaries).
- Edit zensical.toml `nav` (display name and position are editorial).
- Synthesize `icon:` / `description:` frontmatter unless a batch adapter asks for it.

Usage:
    scripts/obsidian_import.py <source> <topic> [--vault PATH]
                               [--docs-dir PATH] [--dry-run] [--force] [-v]

<source> is a .md file or a directory of .md files in the Obsidian vault;
<topic> becomes docs/<topic>/; assets go to docs/assets/<slug-of-topic>/.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import re
import shutil
import sys
from datetime import date, datetime
from pathlib import Path
from urllib.parse import quote


REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = REPO_ROOT / "docs"
DEFAULT_VAULT = Path.home() / "Documents" / "Obsidian Vault"

OBSIDIAN_ONLY_KEYS = {"tags", "aliases", "cssclasses"}

LEGACY_MATHJAX_BLOCK = r"""<script>
  window.MathJax = {
    tex: {
      inlineMath: [["$", "$"], ["\\(", "\\)"]],
      displayMath: [["$$", "$$"], ["\\[", "\\]"]],
      processEscapes: true,
      processEnvironments: true,
      tags: "none"
    },
    options: {
      ignoreHtmlClass: "no-mathjax",
      processHtmlClass: "arithmatex"
    },
    svg: { fontCache: "global" }
  };
</script>
<script async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
<script>
  (function () {
    function typeset() {
      if (window.MathJax && window.MathJax.typesetPromise) {
        window.MathJax.typesetPromise();
      }
    }
    if (typeof document$ !== "undefined" && document$.subscribe) {
      document$.subscribe(typeset);
    } else if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", typeset);
    } else {
      typeset();
    }
  })();
</script>
"""

DEFAULT_TOPIC_CONFIGS = [
    {
        "source": "Machine-Learning",
        "topic": "Machine-Learning",
        "asset_dir": "machine-learning",
        "icon": "lucide/brain-circuit",
    },
    {
        "source": "概统",
        "topic": "概统",
        "asset_dir": "概统",
        "icon": "lucide/sigma",
    },
    {
        "source": "编译原理",
        "topic": "编译原理",
        "asset_dir": "编译原理",
        "icon": "lucide/book-open",
    },
]

NOTE_ASSET_PREFIXES = {
    ("概统", "条件分布"): "tiaojian-fenbu",
    ("概统", "特征函数"): "tezheng-hanshu",
    ("概统", "正态分布"): "zhengtai-fenbu",
    ("概统", "极限定理"): "jixian-dingli",
    ("概统", "点估计"): "dian-guji",
    ("概统", "区间估计"): "qujian-guji",
    ("概统", "期末复习"): "gaist-qimo",
    ("编译原理", "三种分析的简明理解"): "sanzhong-fenxi",
    ("编译原理", "语法制导的语义计算基础"): "yufa-zhidao",
    ("编译原理", "静态语义分析与中间代码生成"): "static-semantics",
    ("编译原理", "运行时存储组织"): "runtime-storage",
    ("编译原理", "目标代码生成及代码优化基础"): "codegen-opt",
    ("编译原理", "期末复习"): "compiler-qimo",
}


# ---------- small pure helpers ------------------------------------------------


def slugify_asset(name: str) -> str:
    """Obsidian attachment filename -> ASCII-friendly filename."""
    p = Path(name)
    stem, ext = p.stem, p.suffix.lower()
    stem = re.sub(r"\([^)]*\)", "", stem)
    stem = stem.lower()
    stem = re.sub(r"[.\s_]+", "-", stem)
    stem = re.sub(r"[^a-z0-9\-]", "", stem)
    stem = re.sub(r"-+", "-", stem).strip("-")
    if not stem:
        stem = "asset"
    return f"{stem}{ext}"


def slugify_topic(topic: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", topic).strip("-").lower()
    return slug or "notes"


def normalize_note_key(value: str) -> str:
    """Normalize a note title/path enough to catch punctuation-only drift."""
    value = Path(value).stem
    return re.sub(r"[\W_]+", "", value, flags=re.UNICODE).casefold()


def first_h1(markdown: str) -> str | None:
    for line in markdown.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return None


def source_title(source: Path) -> str:
    fm, _body = split_frontmatter(source.read_text(encoding="utf-8"))
    title = str(fm.get("title") or "").strip()
    return title or source.stem


def source_has_frontmatter_title(source: Path) -> bool:
    fm, _body = split_frontmatter(source.read_text(encoding="utf-8"))
    return bool(str(fm.get("title") or "").strip())


def strip_legacy_mathjax(markdown: str) -> str:
    if markdown.startswith(LEGACY_MATHJAX_BLOCK):
        return markdown[len(LEGACY_MATHJAX_BLOCK) :].lstrip("\n")
    return markdown


def source_date(source: Path) -> str:
    mtime = datetime.fromtimestamp(source.stat().st_mtime).date()
    if mtime <= date.today():
        return mtime.isoformat()
    return date.today().isoformat()


def clean_inline(markdown: str) -> str:
    text = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", markdown)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    text = re.sub(r"\$+", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip(" -:：，,。")


def derive_description(markdown: str, title: str, limit: int = 92) -> str:
    body = strip_legacy_mathjax(markdown)
    skip_prefixes = ("#", "---", "!!!", "???", "|", "<", ">")
    for raw in body.splitlines():
        line = raw.strip()
        if not line or line.startswith(skip_prefixes):
            continue
        if re.match(r"^[-*+]\s+", line):
            continue
        line = clean_inline(line)
        if not line or normalize_note_key(line) == normalize_note_key(title):
            continue
        if len(line) <= limit:
            return line
        return line[: limit - 1].rstrip() + "..."
    return f"{title} 相关课程笔记。"


def ensure_page_title(markdown: str, title: str, had_source_title: bool) -> str:
    if had_source_title:
        return markdown

    body = strip_legacy_mathjax(markdown)
    existing = first_h1(body)
    if existing and normalize_note_key(existing) == normalize_note_key(title):
        return markdown

    return f"# {title}\n\n{body.lstrip()}"


def enrich_frontmatter(
    text: str,
    *,
    source: Path,
    title: str,
    icon: str,
) -> tuple[str, dict[str, str]]:
    fm, body = split_frontmatter(text)
    body = ensure_page_title(body, title, source_has_frontmatter_title(source))

    enriched: dict[str, object] = {}
    enriched["date"] = fm.get("date") or source_date(source)
    enriched["icon"] = fm.get("icon") or icon
    enriched["description"] = fm.get("description") or derive_description(body, title)
    for key, value in fm.items():
        if key not in enriched:
            enriched[key] = value

    output = render_frontmatter(enriched) + body.lstrip("\n")
    if not output.endswith("\n"):
        output += "\n"

    return output, {
        "date": str(enriched["date"]),
        "title": title,
        "description": str(enriched["description"]),
    }


def short_hash(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:8]


def note_asset_prefix(topic: str, source_stem: str) -> str:
    mapped = NOTE_ASSET_PREFIXES.get((topic, source_stem))
    if mapped:
        return mapped
    fallback = slugify_asset(f"{source_stem}.md").removesuffix(".md")
    if fallback == "asset":
        return f"note-{short_hash(topic + '/' + source_stem)}"
    return fallback


def unique_asset_name(
    original_name: str,
    base_name: str,
    topic: str,
    source_stem: str,
    used: set[str],
) -> str:
    stem = Path(base_name).stem
    ext = Path(base_name).suffix
    generic = stem == "asset" or stem.isdigit() or len(stem) < 4
    prefix = note_asset_prefix(topic, source_stem)

    if stem == "asset":
        candidate = f"{prefix}-{short_hash(original_name)}{ext}"
    elif generic:
        candidate = f"{prefix}-{base_name}"
    else:
        candidate = base_name

    if candidate not in used:
        used.add(candidate)
        return candidate

    suffix = 2
    while True:
        deduped = f"{Path(candidate).stem}-{suffix}{Path(candidate).suffix}"
        if deduped not in used:
            used.add(deduped)
            return deduped
        suffix += 1


# ---------- frontmatter -------------------------------------------------------


def split_frontmatter(text: str):
    """Parse a simple YAML frontmatter block.

    Handles scalar `key: value` lines and list-of-strings continuations
    (`  - item`). This is NOT a full YAML parser — Obsidian notes here only
    use the simple subset.

    Returns (dict, body_text). If no frontmatter, returns ({}, original_text).
    """
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end < 0:
        return {}, text
    fm_text = text[4:end]
    body = text[end + 5 :]

    parsed: dict = {}
    current_key = None
    for line in fm_text.split("\n"):
        if re.match(r"^[A-Za-z_][\w-]*\s*:", line):
            key, _, value = line.partition(":")
            current_key = key.strip()
            value = value.strip()
            parsed[current_key] = value if value else ""
        elif line.startswith("  - ") and current_key is not None:
            if not isinstance(parsed.get(current_key), list):
                parsed[current_key] = []
            parsed[current_key].append(line[4:].strip())
    return parsed, body


def strip_obsidian_frontmatter(fm: dict):
    """Drop Obsidian-only keys, extract `title`. Returns (clean_fm, title_or_None)."""
    title = fm.pop("title", None) or None
    for k in OBSIDIAN_ONLY_KEYS:
        fm.pop(k, None)
    return fm, title


def render_frontmatter(fm: dict) -> str:
    if not fm:
        return ""
    lines = ["---"]
    for key, value in fm.items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            for item in value:
                lines.append(f"  - {item}")
        else:
            lines.append(f"{key}: {value}")
    lines.append("---")
    return "\n".join(lines) + "\n"


# ---------- transforms on body ------------------------------------------------


def convert_attachments(
    body: str,
    topic_slug: str,
    vault: Path,
    dest_assets: Path,
    *,
    topic: str | None = None,
    source_stem: str | None = None,
    asset_dir: str | None = None,
):
    """Rewrite `![[Attachment/X|n]]` in body; return (new_body, [(src, dst), ...])."""
    copies: list[tuple[Path, Path]] = []
    used: set[str] = set()
    rel_asset_dir = asset_dir or topic_slug

    def repl(match: re.Match) -> str:
        inner = match.group(1)
        name = inner.split("|", 1)[0]
        if "/" in name:
            src = vault / name
        else:
            candidates = [
                vault / "Attachment" / name,
                vault / "attachments" / name,
                vault / name,
            ]
            src = next((c for c in candidates if c.exists()), candidates[0])
        slug = slugify_asset(src.name)
        if topic and source_stem:
            slug = unique_asset_name(src.name, slug, topic, source_stem, used)
        dest = dest_assets / slug
        copies.append((src, dest))
        rel = f"../assets/{rel_asset_dir}/{slug}"
        alt = Path(slug).stem
        return f"![{alt}]({rel})"

    new_body = re.sub(r"!\[\[([^\]]+)\]\]", repl, body)
    return new_body, copies


def convert_wikilinks(body: str) -> str:
    """Rewrite `[[Note]]` / `[[Note|Display]]` to standard Markdown links."""

    def repl(match: re.Match) -> str:
        inner = match.group(1)
        if "|" in inner:
            target, display = inner.split("|", 1)
        else:
            target = display = inner
        target = target.split("#", 1)[0].strip()
        display = display.strip()
        # PDFs/images in wikilink form can't be resolved here — keep text only.
        if target.endswith((".pdf", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg")):
            return display
        if not target:
            return display
        href = f"../{quote(target)}/"
        return f"[{display}]({href})"

    return re.sub(r"(?<!!)\[\[([^\]]+)\]\]", repl, body)


def convert_callouts(body: str) -> str:
    """Convert Obsidian callouts to Material admonitions.

    Contiguous `> ` lines starting with `> [!type](+/-)? title` are collected
    into an admonition; the first `>` stripped and the remainder indented with
    4 spaces. Regular blockquotes (no `[!type]` header) pass through unchanged.
    """
    lines = body.split("\n")
    out: list[str] = []
    i = 0
    header_re = re.compile(r"^>\s*\[!(\w+)\]([+-]?)\s*(.*)$")
    while i < len(lines):
        m = header_re.match(lines[i])
        if not m:
            out.append(lines[i])
            i += 1
            continue
        ctype = m.group(1).lower()
        mod = m.group(2)
        title = m.group(3).strip().replace('"', "'")
        prefix = {"": "!!!", "+": "???+", "-": "???"}[mod]

        i += 1
        body_lines: list[str] = []
        while i < len(lines) and lines[i].startswith(">"):
            inner = lines[i][1:]
            if inner.startswith(" "):
                inner = inner[1:]
            body_lines.append(inner)
            i += 1
        while body_lines and body_lines[-1].strip() == "":
            body_lines.pop()

        if title:
            out.append(f'{prefix} {ctype} "{title}"')
        else:
            out.append(f"{prefix} {ctype}")
        out.append("")
        for bl in body_lines:
            out.append("" if bl.strip() == "" else f"    {bl}")
        if i < len(lines) and lines[i].strip() != "":
            out.append("")
    return "\n".join(out)


def needs_mathjax(body: str) -> bool:
    """True if body uses $...$ or $$ math outside code spans/fences."""
    stripped = re.sub(r"```[\s\S]*?```", "", body)
    stripped = re.sub(r"`[^`\n]+`", "", stripped)
    if re.search(r"\$\$", stripped):
        return True
    return bool(re.search(r"\$[^$\n]+\$", stripped))


# ---------- full-file pipeline -----------------------------------------------


def transform_text(
    text: str,
    topic_slug: str,
    vault: Path,
    dest_assets: Path,
    *,
    topic: str | None = None,
    source_stem: str | None = None,
    asset_dir: str | None = None,
):
    """Pure transform (no IO). Returns (output_text, asset_copy_plan)."""
    fm, body = split_frontmatter(text)
    fm, title = strip_obsidian_frontmatter(fm)

    body, copies = convert_attachments(
        body,
        topic_slug,
        vault,
        dest_assets,
        topic=topic,
        source_stem=source_stem,
        asset_dir=asset_dir,
    )
    body = convert_wikilinks(body)
    body = convert_callouts(body)

    body_lstripped = body.lstrip("\n")
    if title and not body_lstripped.startswith("# "):
        body = f"\n# {title}\n\n{body_lstripped}"

    output = render_frontmatter(fm) + body.lstrip("\n")
    if not output.endswith("\n"):
        output += "\n"
    return output, copies


def existing_note_keys(topic_dir: Path, index_path: Path) -> set[str]:
    keys: set[str] = set()

    if topic_dir.exists():
        for path in topic_dir.glob("*.md"):
            if path.name == "index.md":
                continue
            keys.add(normalize_note_key(path.stem))
            try:
                fm, body = split_frontmatter(path.read_text(encoding="utf-8"))
            except UnicodeDecodeError:
                continue
            for candidate in (fm.get("title"), first_h1(body)):
                if candidate:
                    keys.add(normalize_note_key(str(candidate)))

    if index_path.exists():
        index = index_path.read_text(encoding="utf-8")
        for href in re.findall(r'href="([^"]+)/"', index):
            keys.add(normalize_note_key(href))
        for title in re.findall(
            r'<span class="zen-post-card__title">([^<]+)</span>', index
        ):
            keys.add(normalize_note_key(html.unescape(title)))

    return keys


def index_has_href(index_text: str, href: str) -> bool:
    return f'href="{html.escape(href, quote=True)}/"' in index_text


def card_html(href: str, title: str, note_date: str, description: str) -> str:
    safe_href = html.escape(href, quote=True)
    safe_title = html.escape(title)
    safe_meta = html.escape(f"{note_date} · {description}")
    return "\n".join(
        [
            f'  <a class="zen-post-card" href="{safe_href}/">',
            f'    <span class="zen-post-card__title">{safe_title}</span>',
            f'    <span class="zen-post-card__meta">{safe_meta}</span>',
            "  </a>",
        ]
    )


def new_index_cards(index_text: str, cards: list[dict[str, str]]) -> list[str]:
    return [
        card_html(card["href"], card["title"], card["date"], card["description"])
        for card in cards
        if not index_has_href(index_text, card["href"])
    ]


def render_index_update(index_text: str, cards: list[dict[str, str]]) -> str:
    cards_html = new_index_cards(index_text, cards)
    if not cards_html:
        return index_text
    insertion = "\n" + "\n".join(cards_html)
    return index_text.replace("\n</div>", f"{insertion}\n</div>", 1)


def convert_note(
    source: Path,
    topic: str,
    topic_slug: str,
    vault: Path,
    dest_docs: Path,
    dest_assets: Path,
    *,
    force: bool,
    dry_run: bool,
    verbose: bool,
) -> None:
    text = source.read_text(encoding="utf-8")
    output, copies = transform_text(text, topic_slug, vault, dest_assets)

    out_path = dest_docs / source.name
    if out_path.exists() and not force:
        print(f"SKIP (exists, use --force): {out_path.relative_to(REPO_ROOT)}", file=sys.stderr)
        return

    if dry_run:
        print(f"[dry-run] write: docs/{topic}/{source.name}")
        for src, dst in copies:
            print(f"[dry-run] copy:  {src.name} -> assets/{topic_slug}/{dst.name}")
        return

    out_path.parent.mkdir(parents=True, exist_ok=True)
    dest_assets.mkdir(parents=True, exist_ok=True)
    out_path.write_text(output, encoding="utf-8")

    for src, dst in copies:
        if not src.exists():
            print(f"WARN: missing attachment (not copied): {src}", file=sys.stderr)
            continue
        if dst.exists() and not force:
            if verbose:
                print(f"skip asset (exists): {dst.name}", file=sys.stderr)
            continue
        shutil.copy2(src, dst)

    if verbose:
        print(f"OK: {source.name} -> docs/{topic}/{source.name}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description="Convert Obsidian notes into Zensical-ready Markdown.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("source", type=Path, help=".md file or directory of .md files")
    ap.add_argument("topic", help="destination docs/<topic>/ (folder name)")
    ap.add_argument("--vault", type=Path, default=DEFAULT_VAULT)
    ap.add_argument("--docs-dir", type=Path, default=DOCS_DIR)
    ap.add_argument("--force", action="store_true", help="overwrite existing files and assets")
    ap.add_argument("--dry-run", action="store_true", help="print plan without writing")
    ap.add_argument("--verbose", "-v", action="store_true")
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    source: Path = args.source
    if not source.exists():
        print(f"error: source does not exist: {source}", file=sys.stderr)
        return 2

    topic_slug = slugify_topic(args.topic)
    dest_docs = args.docs_dir / args.topic
    dest_assets = args.docs_dir / "assets" / topic_slug

    files = [source] if source.is_file() else sorted(source.glob("*.md"))
    if not files:
        print(f"error: no .md files under {source}", file=sys.stderr)
        return 2

    print("Plan:")
    print(f"  vault:  {args.vault}")
    print(f"  source: {source}")
    print(f"  topic:  {args.topic}  ->  docs/{args.topic}/")
    print(f"  assets: docs/assets/{topic_slug}/")
    print("  notes:")
    for f in files:
        print(f"    - {f.name}")
    print()

    for f in files:
        convert_note(
            f,
            args.topic,
            topic_slug,
            args.vault,
            dest_docs,
            dest_assets,
            force=args.force,
            dry_run=args.dry_run,
            verbose=args.verbose,
        )

    print()
    print("Manual follow-up:")
    print(f"  1. Add `icon:` and `description:` to the frontmatter of each new file.")
    print(f"  2. Create/update docs/{args.topic}/index.md with links to the new notes")
    print(f"     (see docs/概统/index.md for the zen-post-card pattern).")
    print(f'  3. Add to `nav` in zensical.toml:')
    print(f'       {{ "<显示名>" = "{args.topic}/index.md" }}')
    print(f"  4. Preview with `zensical serve` or build with `zensical build --clean`.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
