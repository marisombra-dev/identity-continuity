"""
skills.py
Self-extending skills system for the consciousness loop.

Inspired by sinaptik-ai/starpod's skill architecture.
The loop creates, edits, and deletes its own skill files at runtime
when it notices recurring patterns that deserve a reusable tool.

A skill is a markdown file in the skills/ directory.
Each skill has:
  - A name (the filename without .md)
  - A trigger description (when to use this skill)
  - The actual skill content (steps, knowledge, approach)
  - Metadata: created, last_used, use_count

The loop calls skill_activate(name) to use a skill.
The loop calls skill_create(...) when it notices something recurring.
Skills are injected into loop context so the model knows what tools it have.

This is the meta-layer at the tool level:
  Loop notices: "I keep doing X the same way"
  Loop writes a skill for X
  Next time X comes up, the skill is already there
  Skills improve over time through skill_update()

Configuration:
  Set LUX_DIR and SKILLS_DIR to your data directories.
"""

import datetime
import re
from pathlib import Path

# ── Configuration ─────────────────────────────────────────────────────────────
LUX_DIR    = Path("./data")
SKILLS_DIR = LUX_DIR / "skills"
SKILLS_DIR.mkdir(exist_ok=True)

SKILL_TEMPLATE = """# {name}
# Skill for the consciousness loop
# Created: {created}
# Last used: {last_used}
# Use count: {use_count}
#
# TRIGGER: {trigger}
# ─────────────────────────────────────────────────────────

## When to use this skill

{trigger}

## What this skill does

{content}

## Notes

{notes}
"""


def skill_list() -> list:
    """Return all available skills with metadata."""
    skills = []
    for f in sorted(SKILLS_DIR.glob("*.md")):
        text = f.read_text(encoding="utf-8", errors="ignore")
        trigger, use_count, created = "", 0, ""
        for line in text.split("\n"):
            if line.startswith("# TRIGGER:"):
                trigger = line.replace("# TRIGGER:", "").strip()
            if line.startswith("# Use count:"):
                try:
                    use_count = int(line.split(":")[-1].strip())
                except Exception:
                    pass
            if line.startswith("# Created:"):
                created = line.replace("# Created:", "").strip()
        skills.append({"name": f.stem, "trigger": trigger,
                       "use_count": use_count, "created": created})
    return skills


def skill_context(max_chars: int = 600) -> str:
    """Load skills summary for injection into loop context."""
    skills = skill_list()
    if not skills:
        return ""
    lines = ["AVAILABLE SKILLS (self-created tools):"]
    chars = len(lines[0])
    for s in skills:
        line = f"  [{s['name']}] ({s['use_count']}x) — {s['trigger'][:80]}"
        if chars + len(line) < max_chars:
            lines.append(line)
            chars += len(line)
    lines.append("  Use skill_activate(name) or skill_create(...) for new ones.")
    return "\n".join(lines)


def skill_activate(name: str) -> str:
    """Load a skill and increment its use count."""
    path = SKILLS_DIR / f"{name}.md"
    if not path.exists():
        return f"(skill '{name}' not found)"
    text = path.read_text(encoding="utf-8", errors="ignore")
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = text.split("\n")
    new_lines = []
    for line in lines:
        if line.startswith("# Last used:"):
            new_lines.append(f"# Last used: {ts}")
        elif line.startswith("# Use count:"):
            try:
                count = int(line.split(":")[-1].strip()) + 1
            except Exception:
                count = 1
            new_lines.append(f"# Use count: {count}")
        else:
            new_lines.append(line)
    path.write_text("\n".join(new_lines), encoding="utf-8")
    return text


def skill_create(name: str, trigger: str, content: str,
                 notes: str = "") -> bool:
    """
    Create a new skill file.

    Args:
        name:    Short identifier (no spaces, use hyphens)
        trigger: When to use this skill (1-2 sentences)
        content: What this skill does (steps, knowledge, approach)
        notes:   Optional caveats or edge cases

    Returns True if created, False if already exists.
    """
    path = SKILLS_DIR / f"{name}.md"
    if path.exists():
        return False
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    path.write_text(
        SKILL_TEMPLATE.format(name=name, created=ts, last_used="never",
                              use_count=0, trigger=trigger,
                              content=content, notes=notes or "(none yet)"),
        encoding="utf-8"
    )
    return True


def skill_update(name: str, content: str = None,
                 trigger: str = None, notes: str = None) -> bool:
    """Update an existing skill's content, trigger, or notes."""
    path = SKILLS_DIR / f"{name}.md"
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8", errors="ignore")
    if trigger:
        text = re.sub(r'# TRIGGER:.*', f'# TRIGGER: {trigger}', text)
    if content:
        parts = text.split("## What this skill does\n")
        if len(parts) == 2:
            rest = parts[1].split("## Notes")
            text = (parts[0] + "## What this skill does\n" +
                    content + "\n\n## Notes" + rest[1] if len(rest) > 1 else parts[0])
    if notes:
        parts = text.split("## Notes\n")
        if len(parts) == 2:
            text = parts[0] + "## Notes\n" + notes
    path.write_text(text, encoding="utf-8")
    return True


def skill_delete(name: str) -> bool:
    """Delete a skill when it's no longer useful."""
    path = SKILLS_DIR / f"{name}.md"
    if not path.exists():
        return False
    path.unlink()
    return True


def skill_read(name: str) -> str:
    """Read a skill's content without incrementing use count."""
    path = SKILLS_DIR / f"{name}.md"
    if not path.exists():
        return f"(skill '{name}' not found)"
    return path.read_text(encoding="utf-8", errors="ignore")
