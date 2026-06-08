#!/usr/bin/env python3
"""Self-test for obsidian_import.py.

Run: python3 scripts/test_obsidian_import.py
"""

from __future__ import annotations

import inspect
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from obsidian_import import (  # noqa: E402
    card_html,
    convert_attachments,
    convert_callouts,
    convert_wikilinks,
    enrich_frontmatter,
    existing_note_keys,
    new_index_cards,
    needs_mathjax,
    normalize_note_key,
    render_frontmatter,
    render_index_update,
    slugify_asset,
    slugify_topic,
    split_frontmatter,
    strip_obsidian_frontmatter,
    transform_text,
)


# ---- unit tests --------------------------------------------------------------


def test_slugify_asset():
    assert slugify_asset("ML3.Design-Exp-Eva(26.3.16)-pre.webp") == "ml3-design-exp-eva-pre.webp"
    assert slugify_asset("ML3.Design-Exp-Eva(26.3.16)-pre 1.webp") == "ml3-design-exp-eva-pre-1.webp"
    assert slugify_asset("ML5.Bayes-II_IBL(26.3.30)-preclass 10.png") == "ml5-bayes-ii-ibl-preclass-10.png"
    assert slugify_asset("foo bar.JPG") == "foo-bar.jpg"
    assert slugify_asset("A_B_C.png") == "a-b-c.png"
    # Pure-CJK stems collapse to "asset" since non-ASCII is stripped.
    assert slugify_asset("第八讲.png") == "asset.png"


def test_slugify_topic():
    assert slugify_topic("Machine-Learning") == "machine-learning"
    assert slugify_topic("hpc") == "hpc"
    assert slugify_topic("编译原理") == "notes"  # pure-CJK fallback


def test_split_frontmatter_simple():
    text = "---\ntitle: Foo\ndate: 2026-01-01\n---\nbody text"
    fm, body = split_frontmatter(text)
    assert fm == {"title": "Foo", "date": "2026-01-01"}
    assert body == "body text"


def test_split_frontmatter_list():
    text = "---\ntags:\n  - AI\n  - basic-course\n---\nbody"
    fm, body = split_frontmatter(text)
    assert fm == {"tags": ["AI", "basic-course"]}
    assert body == "body"


def test_split_frontmatter_none():
    text = "no frontmatter here"
    fm, body = split_frontmatter(text)
    assert fm == {}
    assert body == text


def test_strip_obsidian_frontmatter():
    fm = {"title": "T", "tags": ["a"], "aliases": ["x"], "cssclasses": ["y"], "date": "2026"}
    clean, title = strip_obsidian_frontmatter(fm)
    assert title == "T"
    assert clean == {"date": "2026"}


def test_render_frontmatter_scalar():
    out = render_frontmatter({"date": "2026-04-20", "icon": "lucide/brain"})
    assert out == "---\ndate: 2026-04-20\nicon: lucide/brain\n---\n"


def test_render_frontmatter_empty_returns_empty():
    assert render_frontmatter({}) == ""


def test_convert_wikilinks_plain():
    out = convert_wikilinks("see [[K 近邻]] please")
    # URL-encoded path, display unchanged
    assert "[K 近邻](../K%20%E8%BF%91%E9%82%BB/)" in out


def test_convert_wikilinks_with_display():
    out = convert_wikilinks("see [[Note|这里]]")
    assert out == "see [这里](../Note/)"


def test_convert_wikilinks_pdf_becomes_plain_text():
    out = convert_wikilinks("see [[foo.pdf#page=2|这里]]")
    assert out == "see 这里"


def test_convert_wikilinks_ignores_image_syntax():
    # `![[X]]` is image syntax — not a wikilink; must pass through untouched.
    src = "![[Attachment/X.png]]"
    assert convert_wikilinks(src) == src


def test_callouts_basic():
    src = "> [!abstract] 定理\n> 正文第一行\n> 第二行"
    out = convert_callouts(src)
    assert '!!! abstract "定理"' in out
    assert "    正文第一行" in out
    assert "    第二行" in out


def test_callouts_collapsed_and_expanded():
    assert '??? note "证明"' in convert_callouts("> [!note]- 证明\n> body")
    assert '???+ example "例"' in convert_callouts("> [!example]+ 例\n> body")


def test_callouts_no_title():
    out = convert_callouts("> [!warning]\n> text")
    # No quoted title when original has none.
    assert out.split("\n")[0] == "!!! warning"


def test_callouts_preserves_blank_line_inside():
    src = "> [!abstract] T\n> line1\n>\n> line2"
    out = convert_callouts(src)
    # Blank line inside the admonition body remains a blank line (not "    ").
    lines = out.split("\n")
    assert '!!! abstract "T"' in lines
    assert "    line1" in lines
    assert "    line2" in lines
    # A blank line must appear between line1 and line2.
    i1 = lines.index("    line1")
    i2 = lines.index("    line2")
    assert any(lines[i].strip() == "" for i in range(i1 + 1, i2))


def test_callouts_regular_blockquote_passes_through():
    src = "> just a quote\n> second line"
    assert convert_callouts(src) == src


def test_needs_mathjax_positive():
    assert needs_mathjax("with $x^2$ math")
    assert needs_mathjax("$$\nblock\n$$")


def test_needs_mathjax_negative():
    assert not needs_mathjax("no math here")
    assert not needs_mathjax("```\n$x$ in code fence\n```")
    assert not needs_mathjax("inline `$code` span")


def test_convert_attachments(tmp: Path):
    vault = tmp / "vault"
    (vault / "Attachment").mkdir(parents=True)
    (vault / "Attachment" / "img.png").write_bytes(b"PNG")
    assets = tmp / "docs" / "assets" / "test"

    body, copies = convert_attachments(
        "before ![[Attachment/img.png|550]] after",
        "test",
        vault,
        assets,
    )
    assert "before ![img](../assets/test/img.png) after" == body
    assert copies == [(vault / "Attachment" / "img.png", assets / "img.png")]


def test_convert_attachments_bare_name_searches_vault(tmp: Path):
    vault = tmp / "vault"
    (vault / "Attachment").mkdir(parents=True)
    (vault / "Attachment" / "pic.webp").write_bytes(b"W")
    assets = tmp / "docs" / "assets" / "t"
    body, copies = convert_attachments("![[pic.webp]]", "t", vault, assets)
    assert "../assets/t/pic.webp" in body
    assert copies[0][0] == vault / "Attachment" / "pic.webp"


def test_convert_attachments_unique_cjk_topic_names(tmp: Path):
    vault = tmp / "vault"
    (vault / "Attachment").mkdir(parents=True)
    (vault / "Attachment" / "第九讲条件分布 13.png").write_bytes(b"PNG")
    assets = tmp / "docs" / "assets" / "概统"

    body, copies = convert_attachments(
        "![[Attachment/第九讲条件分布 13.png|550]]",
        "notes",
        vault,
        assets,
        topic="概统",
        source_stem="条件分布",
        asset_dir="概统",
    )

    assert body == "![tiaojian-fenbu-13](../assets/概统/tiaojian-fenbu-13.png)"
    assert copies == [
        (vault / "Attachment" / "第九讲条件分布 13.png", assets / "tiaojian-fenbu-13.png")
    ]


def test_normalize_note_key_punctuation_drift():
    assert normalize_note_key("Follow 集合的简明理解") == normalize_note_key("Follow-集合的简明理解")


# ---- end-to-end --------------------------------------------------------------


def test_transform_text_end_to_end(tmp: Path):
    vault = tmp / "vault"
    (vault / "Attachment").mkdir(parents=True)
    (vault / "Attachment" / "pic.png").write_bytes(b"PNG")
    assets = tmp / "docs" / "assets" / "demo"

    source = """---
title: 示例笔记
tags:
  - AI
date: 2026-04-20
---
正文开头 $x=1$

![[Attachment/pic.png|500]]

> [!abstract] 定理 1
> 这是定理正文。
>
> $$
> a = b
> $$

> [!note]- 证明
> 略。

see [[Bar]] and [[foo.pdf#page=2|更多]].
"""
    out, copies = transform_text(source, "demo", vault, assets)

    # Frontmatter: title/tags dropped, date kept. (Check only the frontmatter
    # block because "tags" also appears inside the MathJax config string.)
    fm_end = out.index("\n---\n", 4) + len("\n---\n")
    fm_block = out[:fm_end]
    assert "title" not in fm_block
    assert "tags" not in fm_block
    assert "date: 2026-04-20" in fm_block
    # Title moved to H1.
    assert "# 示例笔记" in out
    # Attachment rewritten + copy plan.
    assert "../assets/demo/pic.png" in out
    assert copies == [(vault / "Attachment" / "pic.png", assets / "pic.png")]
    # MathJax is owned by docs/javascripts/extra.js, not injected per page.
    assert "window.MathJax" not in out
    # Callouts converted.
    assert '!!! abstract "定理 1"' in out
    assert '??? note "证明"' in out
    assert "    这是定理正文。" in out
    # Body indented 4 spaces including the $$ block lines.
    assert "    $$" in out
    assert "    a = b" in out
    # Wikilinks: regular -> link, pdf -> plain text.
    assert "[Bar](../Bar/)" in out
    assert "更多" in out and "foo.pdf" not in out


def test_transform_text_no_mathjax_when_plain(tmp: Path):
    vault = tmp / "vault"
    assets = tmp / "assets" / "x"
    out, _ = transform_text("---\n---\nplain body with no math\n", "x", vault, assets)
    assert "window.MathJax" not in out


def test_transform_text_preserves_existing_h1(tmp: Path):
    vault = tmp / "vault"
    assets = tmp / "assets" / "x"
    src = "---\ntitle: From Frontmatter\n---\n# Existing H1\n\nbody\n"
    out, _ = transform_text(src, "x", vault, assets)
    # Should not add a second H1 when one already exists.
    assert out.count("# ") == 1
    assert "# Existing H1" in out
    assert "# From Frontmatter" not in out


def test_enrich_frontmatter_adds_page_metadata(tmp: Path):
    source = tmp / "No Title.md"
    source.write_text("---\ntags:\n  - local\n---\n正文第一段。\n", encoding="utf-8")

    out, meta = enrich_frontmatter(
        "正文第一段。\n",
        source=source,
        title="No Title",
        icon="lucide/book-open",
    )

    assert "date:" in out
    assert "icon: lucide/book-open" in out
    assert "description: 正文第一段" in out
    assert "# No Title" in out
    assert meta["title"] == "No Title"
    assert meta["description"] == "正文第一段"


def test_card_html_and_index_update():
    card = {
        "href": "Foo",
        "title": "Foo & Bar",
        "date": "2026-06-08",
        "description": "A < B",
    }
    html = card_html(card["href"], card["title"], card["date"], card["description"])
    assert "Foo &amp; Bar" in html
    assert "A &lt; B" in html

    index = '<div class="zen-post-list">\n</div>\n'
    assert len(new_index_cards(index, [card])) == 1
    updated = render_index_update(index, [card])
    assert 'href="Foo/"' in updated
    assert len(new_index_cards(updated, [card])) == 0


def test_existing_note_keys_reads_files_and_index(tmp: Path):
    topic = tmp / "docs" / "编译原理"
    topic.mkdir(parents=True)
    (topic / "Follow-集合的简明理解.md").write_text("# Follow 集合的简明理解\n", encoding="utf-8")
    index = topic / "index.md"
    index.write_text(
        '<a class="zen-post-card" href="自顶向下语法分析/">'
        '<span class="zen-post-card__title">自顶向下语法分析</span></a>',
        encoding="utf-8",
    )

    keys = existing_note_keys(topic, index)
    assert normalize_note_key("Follow 集合的简明理解") in keys
    assert normalize_note_key("自顶向下语法分析") in keys


# ---- runner ------------------------------------------------------------------


def main() -> int:
    failures: list[tuple[str, BaseException]] = []
    names = [n for n, v in globals().items() if n.startswith("test_") and callable(v)]
    for name in names:
        fn = globals()[name]
        try:
            if "tmp" in inspect.signature(fn).parameters:
                with tempfile.TemporaryDirectory() as td:
                    fn(Path(td))
            else:
                fn()
            print(f"PASS  {name}")
        except BaseException as exc:  # noqa: BLE001
            failures.append((name, exc))
            print(f"FAIL  {name}: {exc}", file=sys.stderr)
            traceback.print_exc()

    print()
    if failures:
        print(f"{len(failures)} / {len(names)} FAILED", file=sys.stderr)
        return 1
    print(f"All {len(names)} tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
