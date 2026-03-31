#!/usr/bin/env python3
"""
Archive a completed research result from the daemon workspace to results/.

Usage:
  python archive_result.py <workspace_path>
  python archive_result.py --latest
  python archive_result.py --all
"""
import json
import re
import sys
from datetime import datetime
from pathlib import Path

RESULTS_DIR = Path(__file__).resolve().parents[3] / "results"
WORKSPACE_DIR = Path.home() / ".darklab" / "memento-codex" / "workspaces"
KNOWLEDGE_FILE = Path.home() / ".darklab" / "memento-codex" / "knowledge.jsonl"


def slugify(text: str, max_len: int = 60) -> str:
    """Convert topic to filesystem-safe slug."""
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text[:max_len]


def find_topic_for_workspace(ws_name: str) -> dict:
    """Find the knowledge base entry matching this workspace."""
    if not KNOWLEDGE_FILE.exists():
        return {}
    for line in KNOWLEDGE_FILE.read_text().splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
            if ws_name in entry.get("workspace", ""):
                return entry
        except json.JSONDecodeError:
            continue
    return {}


def archive_workspace(ws_path: Path, category: str = "research"):
    """Archive a workspace to results/."""
    if not ws_path.exists():
        print(f"Workspace not found: {ws_path}")
        return None

    final = ws_path / "final.md"
    papers = ws_path / "papers.json"

    if not final.exists():
        print(f"No final.md in {ws_path.name} — skipping")
        return None

    # Find topic from knowledge base
    kb_entry = find_topic_for_workspace(ws_path.name)
    topic = kb_entry.get("topic", ws_path.name)
    score = kb_entry.get("score", 0)
    paper_count = kb_entry.get("paper_count", 0)
    timestamp = kb_entry.get("timestamp", "")

    # Generate filename
    date_str = timestamp[:10] if timestamp else ws_path.name[:8]
    if len(date_str) == 8 and date_str.isdigit():
        date_str = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
    slug = slugify(topic)
    base_name = f"{date_str}_{slug}"

    # Determine category
    out_dir = RESULTS_DIR / category
    out_dir.mkdir(parents=True, exist_ok=True)

    # Write research report
    report_path = out_dir / f"{base_name}.md"
    content = final.read_text()

    # Add metadata header if not present
    if not content.startswith("# "):
        header = (
            f"# {topic}\n\n"
            f"**Score:** {score:.2f}/1.0 | **Papers:** {paper_count} | "
            f"**Date:** {date_str}\n\n---\n\n"
        )
        content = header + content

    report_path.write_text(content)
    print(f"  Report: {report_path.relative_to(RESULTS_DIR.parent)}")

    # Write source index
    if papers.exists():
        sources_path = out_dir / f"{base_name}_sources.json"
        sources_path.write_text(papers.read_text())
        print(f"  Sources: {sources_path.relative_to(RESULTS_DIR.parent)}")

    # Copy lessons if present
    lessons = ws_path / "lessons.md"
    if lessons.exists():
        lessons_path = out_dir / f"{base_name}_lessons.md"
        lessons_path.write_text(lessons.read_text())

    return report_path


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python archive_result.py <workspace_path>")
        print("  python archive_result.py --latest")
        print("  python archive_result.py --all")
        return

    arg = sys.argv[1]
    category = sys.argv[2] if len(sys.argv) > 2 else "research"

    if arg == "--latest":
        workspaces = sorted(WORKSPACE_DIR.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
        if workspaces:
            archive_workspace(workspaces[0], category)
        else:
            print("No workspaces found")

    elif arg == "--all":
        archived = 0
        for ws in sorted(WORKSPACE_DIR.iterdir()):
            if ws.is_dir():
                result = archive_workspace(ws, category)
                if result:
                    archived += 1
        print(f"\nArchived {archived} results to results/{category}/")

    else:
        ws_path = Path(arg)
        if not ws_path.is_absolute():
            ws_path = WORKSPACE_DIR / arg
        archive_workspace(ws_path, category)


if __name__ == "__main__":
    main()
