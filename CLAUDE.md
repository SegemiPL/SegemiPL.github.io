# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

See `AGENTS.md` for the canonical project overview (directory table, CI, etc.). This file captures the points most load-bearing for editing.

## What this repo is

Personal static blog built with **Zensical** (Material-for-MkDocs-style generator) deployed to GitHub Pages at `https://SegemiPL.github.io/`. UI language is Chinese (`language = "zh"`). Sole config is `zensical.toml`; content lives in `docs/`.

## Commands

```bash
pip install 'zensical>=0.0.28'   # one-time setup (use .venv)
zensical serve                    # live-reload preview
zensical build --clean            # CI-equivalent build → site/
```

`site/` is a build artifact — never commit or hand-edit it. CI (`.github/workflows/docs.yml`) re-runs `zensical build --clean` on push to `main`/`master` and uploads `site/` to Pages.

## Architecture: how content becomes navigation

The site has **two parallel structures** that must stay in sync:

1. **Filesystem** — topic folders under `docs/` (e.g. `docs/hpc/`, `docs/编译原理/`, `docs/tools/`, `docs/blog/`). Each topic folder has its own `index.md` that lists the notes inside it.
2. **Sidebar `nav`** in `zensical.toml` — only references each topic's `index.md`, never individual notes. Individual posts are discovered via the topic's `index.md` list page, not the sidebar.

So adding a new note is **two edits**: the `.md` file itself, plus a link entry in the topic's `index.md`. Creating a *new topic* is **four**: `docs/<topic>/` folder + `docs/<topic>/index.md` (list page) + the note + a `nav` entry in `zensical.toml` (insert in display order, not alphabetic). Topic folders with Chinese names work (e.g. `docs/编译原理/`, `docs/概统/`).

Non-course short-form writing goes in `docs/blog/` (update `docs/blog/index.md`). Course/topic notes go in `docs/<topic>/`.

## Frontmatter convention

Match existing posts — typical fields are `date` (`YYYY-MM-DD`), `icon` (e.g. `lucide/...`), `description`. Assets live under `docs/assets/<topic>/` and are referenced with paths relative to `docs/`. Asset filenames should be ASCII-friendly (e.g. `hpc-3-00.webp`, `pasted-20260305101645.png`, `hanshufenbu-04.png`) — do **not** keep Obsidian's `第八讲函数分布 4.png`-style names with spaces/CJK, as they hurt URLs and diff readability.

## Admonitions (callouts)

Use Material-style admonitions — **not** `> **bold**` blockquotes — for note/tip/warning/example boxes:

```
!!! abstract "定理（...）"

    正文必须缩进 4 空格，前后各一空行。

??? note "证明"           # collapsed by default
???+ example "例"         # expanded by default, user can collapse
```

Valid types: `note`, `abstract`, `tip`, `info`, `success`, `question`, `warning`, `failure`, `danger`, `example`, `quote`. CSS hooks already exist in `docs/stylesheets/extra.css` (`.md-typeset .admonition`).

## Math (MathJax)

MathJax is configured site-wide in `docs/javascripts/extra.js`, which is loaded via `extra_javascript` in `zensical.toml`. Pages should write math directly with `$...$` / `$$...$$`; do not paste per-page MathJax `<script>` blocks into notes.

The site-wide module configures `MathJax.tex.inlineMath`/`displayMath`, hooks `document$.subscribe(typeset)` for Zensical instant navigation, and sets `ignoreHtmlClass: "no-mathjax"` to keep MathJax out of code blocks.

## Theme overrides

`overrides/` is wired via `custom_dir = "overrides"` in `zensical.toml` — currently only `overrides/partials/toc.html`. Template overrides go here, not into `site/`.

## Importing from Obsidian (`~/Documents/Obsidian Vault`)

Use `scripts/obsidian_import.py` for the mechanical transforms (frontmatter strip, attachment rename+copy, wikilink/callout rewrite, page metadata helpers, card rendering helpers). Unit tests live alongside it: `python3 scripts/test_obsidian_import.py`.

`scripts/` is tracked source. Put machine-local script configuration under `scripts/local/` if needed.

```bash
# A whole topic folder
python3 scripts/obsidian_import.py \
    "$HOME/Documents/Obsidian Vault/course/<topic>" <Topic> -v

# A single note
python3 scripts/obsidian_import.py \
    "$HOME/Documents/Obsidian Vault/course/<topic>/<note>.md" <Topic> -v

# Preview without writing / copying
python3 scripts/obsidian_import.py <source> <Topic> --dry-run
```

`<Topic>` is the folder under `docs/` (e.g. `Machine-Learning`, `hpc`). Assets land in `docs/assets/<slug-of-topic>/` with slugified ASCII filenames. Re-import with `--force` to overwrite (manual frontmatter edits will be lost — apply them to the vault source, or re-do after import).

**Before running** (per `.cursor/rules/obsidian-notes-upload.mdc`): **report first** — list the source `.md` file(s) and confirm with the user before writing. `--dry-run` is the natural way to do this.

**After running** — four steps the script intentionally does NOT automate:

1. Add `icon:` / `description:` (and `date:` if the source lacked one) to each new file's frontmatter.
2. Create/update `docs/<Topic>/index.md` with zen-post-card entries (pattern: `docs/概统/index.md`).
3. For a **new topic**, add a `nav` entry in `zensical.toml` — insert in display order, not alphabetic: `{ "<显示名>" = "<Topic>/index.md" }`.
4. Verify with `zensical build --clean` (or `serve`).

**What the script transforms** (reference — the sections above are authoritative):

- Frontmatter: drops `tags` / `aliases` / `cssclasses`; moves `title:` into an H1; keeps `date:`.
- `![[Attachment/X|n]]` → `![stem](../assets/<topic-slug>/<slug>.ext)`; drops `|width`; copies and renames the asset.
- `[[Note]]` / `[[Note|Display]]` → `[Display](../Note/)` (URL-encoded); `[[foo.pdf#page=2|Text]]` → plain `Text`.
- `> [!type](+/-)? 标题` → `!!! / ???+ / ??? <type> "标题"`, body indented 4 spaces.
- Math remains inline; rendering is handled by the site-wide MathJax module in `docs/javascripts/extra.js`.
