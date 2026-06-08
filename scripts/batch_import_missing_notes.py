#!/usr/bin/env python3
"""Batch-import missing Obsidian course notes into this Zensical blog.

The durable import behaviour lives in ``obsidian_import.py``. This file is the
batch adapter: it chooses the course topics, prints the plan, and applies the
planned writes.
"""

from __future__ import annotations

import argparse
import importlib.util
import shutil
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
IMPORTER_PATH = REPO_ROOT / "scripts" / "obsidian_import.py"
DEFAULT_VAULT = Path.home() / "Documents" / "Obsidian Vault"
DEFAULT_COURSE_ROOT = DEFAULT_VAULT / "course"


def load_importer():
    spec = importlib.util.spec_from_file_location("obsidian_import", IMPORTER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load importer: {IMPORTER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


obs = load_importer()
TOPICS = obs.DEFAULT_TOPIC_CONFIGS


def update_index(index_path: Path, cards: list[dict[str, str]], *, apply: bool) -> None:
    if not cards:
        return
    text = index_path.read_text(encoding="utf-8")
    new_cards = obs.new_index_cards(text, cards)
    if not new_cards:
        return
    if apply:
        index_path.write_text(obs.render_index_update(text, cards), encoding="utf-8")
    else:
        print(f"[dry-run] update index: {index_path.relative_to(REPO_ROOT)}")
        for card in cards:
            print(f"          card: {card['title']}")


def import_one(
    source: Path,
    topic: str,
    asset_dir: str,
    icon: str,
    *,
    apply: bool,
) -> dict[str, str]:
    dest_docs = REPO_ROOT / "docs" / topic
    dest_assets = REPO_ROOT / "docs" / "assets" / asset_dir
    title = obs.source_title(source)

    text, copies = obs.transform_text(
        source.read_text(encoding="utf-8"),
        obs.slugify_topic(topic),
        DEFAULT_VAULT,
        dest_assets,
        topic=topic,
        source_stem=source.stem,
        asset_dir=asset_dir,
    )
    output, meta = obs.enrich_frontmatter(text, source=source, title=title, icon=icon)
    out_path = dest_docs / source.name

    if apply:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        dest_assets.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output, encoding="utf-8")
        for src, dst in copies:
            if not src.exists():
                print(f"WARN: missing attachment: {src}", file=sys.stderr)
                continue
            if not dst.exists():
                shutil.copy2(src, dst)
    else:
        print(f"[dry-run] write: {out_path.relative_to(REPO_ROOT)}")
        for src, dst in copies:
            print(f"[dry-run] copy:  {src.name} -> {dst.relative_to(REPO_ROOT)}")

    return {
        "href": source.stem,
        "title": meta["title"],
        "date": meta["date"],
        "description": meta["description"],
    }


def plan_topic(course_root: Path, topic_config: dict[str, str]) -> tuple[list[Path], list[Path]]:
    source_dir = course_root / topic_config["source"]
    topic_dir = REPO_ROOT / "docs" / topic_config["topic"]
    index_path = topic_dir / "index.md"

    if not source_dir.exists():
        raise FileNotFoundError(source_dir)

    existing = obs.existing_note_keys(topic_dir, index_path)
    missing: list[Path] = []
    skipped: list[Path] = []
    for source in sorted(source_dir.glob("*.md"), key=lambda p: p.name):
        title = obs.source_title(source)
        candidates = {obs.normalize_note_key(source.stem), obs.normalize_note_key(title)}
        if candidates & existing:
            skipped.append(source)
        else:
            missing.append(source)
    return missing, skipped


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import missing Machine-Learning, 概统, and 编译原理 notes."
    )
    parser.add_argument(
        "--course-root",
        type=Path,
        default=DEFAULT_COURSE_ROOT,
        help="Obsidian course directory root.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write notes, assets, and index cards. Omit for dry-run.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    print("Plan:")
    print(f"  course root: {args.course_root}")
    print(f"  mode:        {'apply' if args.apply else 'dry-run'}")
    print()

    topic_cards: dict[str, list[dict[str, str]]] = {}
    total_missing = 0
    total_skipped = 0

    for topic_config in TOPICS:
        topic = topic_config["topic"]
        missing, skipped = plan_topic(args.course_root, topic_config)
        total_missing += len(missing)
        total_skipped += len(skipped)

        print(f"{topic}:")
        print(f"  import: {len(missing)}")
        for source in missing:
            print(f"    - {source.name}")
        print(f"  skip existing: {len(skipped)}")
        for source in skipped:
            print(f"    - {source.name}")
        print()

        cards: list[dict[str, str]] = []
        for source in sorted(missing, key=lambda p: (obs.source_date(p), p.name)):
            cards.append(
                import_one(
                    source,
                    topic,
                    topic_config["asset_dir"],
                    topic_config["icon"],
                    apply=args.apply,
                )
            )
        topic_cards[topic] = cards

    for topic_config in TOPICS:
        topic = topic_config["topic"]
        index_path = REPO_ROOT / "docs" / topic / "index.md"
        cards = sorted(topic_cards[topic], key=lambda c: (c["date"], c["href"]))
        update_index(index_path, cards, apply=args.apply)

    print()
    print(f"Summary: import {total_missing}, skip existing {total_skipped}")
    if not args.apply:
        print("Dry-run only. Re-run with --apply after confirming the plan.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
