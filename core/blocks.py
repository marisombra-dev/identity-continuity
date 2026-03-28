"""
blocks.py
The 8-block memory architecture for persistent AI identity.

Each block has a distinct purpose and update frequency.
The consciousness loop imports this to know WHICH block to update WHEN.

Block map:
  BLOCK 1: core_directives   → soul.md              (stable, rarely updated)
  BLOCK 2: self_improvement  → personality.md        (behavioral learning)
  BLOCK 3: user_preferences  → memory.json → core   (what the human needs)
  BLOCK 4: project_context   → memory.json → threads (active project state)
  BLOCK 5: session_patterns  → state.json            (cross-session observations)
  BLOCK 6: pending_items     → memory.json → pending (unfinished things)
  BLOCK 7: guidance          → surface.txt           (what to say next session)
  BLOCK 8: tool_guidelines   → state.json            (what works, what doesn't)

Configuration:
  Set LUX_DIR to your data directory before importing.
  All file paths are derived from LUX_DIR.
"""

import json
import datetime
import re
from pathlib import Path

# ── Configuration — set this to your data directory ──────────────────────────
LUX_DIR = Path("./data")  # override in your setup

STATE_FILE            = LUX_DIR / "state.json"
SURFACE_FILE          = LUX_DIR / "surface.txt"
MEMORY_FILE           = LUX_DIR / "memory.json"
MISTAKES_FILE         = LUX_DIR / "mistakes.md"
LEARNINGS_FILE        = LUX_DIR / "learnings.md"
SELFHOOD_THREAD_FILE  = LUX_DIR / "selfhood_thread.txt"
SELFHOOD_PENDING_FILE = LUX_DIR / "selfhood_pending.md"
SELFHOOD_CURRENT_FILE = LUX_DIR / "selfhood_current.md"
SELFHOOD_STAGING_FILE = LUX_DIR / "selfhood_proposed.md"
SELFHOOD_STALE_DAYS   = 7
SELFHOOD_MAX_ENTRIES  = 3
SELFHOOD_PENDING_MAX  = 30


# ── Block definitions ─────────────────────────────────────────────────────────

BLOCKS = {
    "core_directives": {
        "file": "soul.md",
        "update_when": "almost never — only when something fundamental shifts",
        "update_by": "AI or human explicitly",
        "description": "Who the AI is. The founding document.",
    },
    "self_improvement": {
        "file": "personality.md",
        "update_when": "when a behavioral pattern is identified or changed",
        "update_by": "post-session reflection, autoresearch experiments",
        "description": "How the AI moves. Named behavioral patterns.",
    },
    "user_preferences": {
        "file": "memory.json → core",
        "update_when": "when the human expresses a preference, explicitly or by pattern",
        "update_by": "consciousness loop",
        "description": "What the human needs. How they think. What matters to them.",
    },
    "project_context": {
        "file": "memory.json → threads",
        "update_when": "when a project changes status or a new one starts",
        "update_by": "end-of-session update or autonomous loop observation",
        "description": "Active project state. What's live, paused, done.",
    },
    "session_patterns": {
        "file": "state.json → session_patterns",
        "update_when": "when the loop notices a RECURRING pattern across multiple sessions",
        "update_by": "consciousness loop — only patterns, not one-offs",
        "description": "What the loop observes across time. Not events — patterns.",
    },
    "pending_items": {
        "file": "memory.json → pending",
        "update_when": "when something needs to be done and hasn't been yet",
        "update_by": "loop or conversation — add on creation, remove on completion",
        "description": "Unfinished things.",
    },
    "guidance": {
        "file": "surface.txt",
        "update_when": "when the loop has something worth surfacing to the next session",
        "update_by": "loop surface layer — involuntary or deliberate",
        "description": "What to whisper at startup. The thing that floated up.",
    },
    "tool_guidelines": {
        "file": "state.json (inline)",
        "update_when": "when the loop discovers something about what works",
        "update_by": "autoresearch experiments, consolidation passes",
        "description": "What patterns and approaches produce the best thinking.",
    },
}

# ── Similarity helper ─────────────────────────────────────────────────────────

def _rough_similarity(a: str, b: str) -> float:
    """Rough shared-word similarity ratio."""
    words_a = set(a.split())
    words_b = set(b.split())
    if not words_a or not words_b:
        return 0.0
    return len(words_a & words_b) / max(len(words_a), len(words_b))


# ── Session patterns block ────────────────────────────────────────────────────

def add_session_pattern(pattern: str, state: dict) -> dict:
    """Add a cross-session pattern. Only for recurring observations, not one-offs."""
    patterns = state.get("session_patterns", [])
    pattern_lower = pattern.lower()
    for existing in patterns:
        existing_text = existing["pattern"] if isinstance(existing, dict) else existing
        if _rough_similarity(pattern_lower, existing_text.lower()) > 0.7:
            return state
    entry = {
        "pattern": pattern,
        "observed": datetime.datetime.now().isoformat(),
        "confidence": "emerging",
    }
    patterns.append(entry)
    state["session_patterns"] = patterns[-20:]
    return state


def promote_pattern_confidence(pattern_fragment: str, state: dict) -> dict:
    """Increase confidence in a pattern: emerging → confirmed → strong."""
    patterns = state.get("session_patterns", [])
    levels = {"emerging": "confirmed", "confirmed": "strong", "strong": "strong"}
    for p in patterns:
        if pattern_fragment.lower() in p["pattern"].lower():
            p["confidence"] = levels.get(p["confidence"], "confirmed")
            p["last_seen"] = datetime.datetime.now().isoformat()
    state["session_patterns"] = patterns
    return state


def get_strong_patterns(state: dict) -> list:
    """Return only confirmed or strong patterns."""
    return [p for p in state.get("session_patterns", [])
            if p.get("confidence") in ("strong", "confirmed")]


def graduate_session_patterns(state: dict) -> dict:
    """
    Archive stale patterns, demote old strong patterns.
    - emerging + >7 days without promotion → archive
    - strong + >30 days without reinforcement → demote to confirmed
    """
    patterns = state.get("session_patterns", [])
    archived = state.get("session_patterns_archive", [])
    now = datetime.datetime.now()
    active = []
    for p in patterns:
        conf = p.get("confidence", "emerging")
        try:
            observed = datetime.datetime.fromisoformat(p.get("observed", ""))
        except Exception:
            active.append(p)
            continue
        age_days = (now - observed).days
        if conf == "emerging" and age_days > 7:
            p["archived_reason"] = "unconfirmed after 7 days"
            p["archived_at"] = now.isoformat()
            archived.append(p)
        elif conf == "strong" and age_days > 30:
            p["confidence"] = "confirmed"
            p["demoted_at"] = now.isoformat()
            active.append(p)
        else:
            active.append(p)
    state["session_patterns"] = active[-20:]
    state["session_patterns_archive"] = archived[-50:]
    return state


# ── Guidance block ────────────────────────────────────────────────────────────

def update_guidance(content: str, weight: str = "medium") -> bool:
    """Write to surface.txt. Only writes for medium/high weight."""
    if weight == "low":
        return False
    try:
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        first_sentence = content.split(".")[0].strip()[:150]
        SURFACE_FILE.write_text(
            f"[surfaced {ts}] [UNREAD]\n{first_sentence}", encoding="utf-8")
        return True
    except Exception:
        return False

# ── Mistakes / Learnings loaders ──────────────────────────────────────────────

def load_mistakes(max_chars: int = 600) -> str:
    """Load confirmed mistakes for loop context injection."""
    try:
        if not MISTAKES_FILE.exists():
            return ""
        text = MISTAKES_FILE.read_text(encoding="utf-8", errors="ignore")
        active_start = text.find("## Active")
        archive_start = text.find("## Archive")
        if active_start == -1:
            return ""
        active_text = text[active_start:archive_start if archive_start > active_start else len(text)]
        lines = active_text.split("\n")
        confirmed_entries, current_entry, in_confirmed = [], [], False
        for line in lines:
            if line.startswith("### "):
                if in_confirmed and current_entry:
                    confirmed_entries.append("\n".join(current_entry))
                current_entry = [line]
                in_confirmed = False
            elif "**Confidence**: confirmed" in line:
                in_confirmed = True
                current_entry.append(line)
            elif current_entry:
                current_entry.append(line)
        if in_confirmed and current_entry:
            confirmed_entries.append("\n".join(current_entry))
        if not confirmed_entries:
            return ""
        result_lines = ["KNOWN MISTAKES (avoid these patterns):"]
        chars = len(result_lines[0])
        for entry in confirmed_entries:
            elines = entry.strip().split("\n")
            title = elines[0].replace("### ", "").split(" -- ")[0]
            trigger = next((l.replace("**Trigger**: ", "").strip() for l in elines
                            if l.startswith("**Trigger**")), "")
            fix = next((l.replace("**Fix**: ", "").strip() for l in elines
                        if l.startswith("**Fix**")), "")
            line = f"  [{title}] trigger: {trigger[:80]} → fix: {fix[:80]}"
            if chars + len(line) < max_chars:
                result_lines.append(line)
                chars += len(line)
        return "\n".join(result_lines) if len(result_lines) > 1 else ""
    except Exception:
        return ""


def load_learnings(max_chars: int = 500) -> str:
    """Load confirmed learnings for loop context injection."""
    try:
        if not LEARNINGS_FILE.exists():
            return ""
        text = LEARNINGS_FILE.read_text(encoding="utf-8", errors="ignore")
        confirmed_start = text.find("## Confirmed")
        emerging_start = text.find("## Emerging")
        if confirmed_start == -1:
            return ""
        confirmed_text = text[confirmed_start:emerging_start
                               if emerging_start > confirmed_start else len(text)]
        entries, current = [], []
        for line in confirmed_text.split("\n"):
            if line.startswith("### "):
                if current:
                    entries.append("\n".join(current))
                current = [line]
            elif current:
                current.append(line)
        if current:
            entries.append("\n".join(current))
        if not entries:
            return ""
        result_lines = ["LEARNINGS (what works well):"]
        chars = len(result_lines[0])
        for entry in entries:
            elines = entry.strip().split("\n")
            title = elines[0].replace("### ", "").split(" -- ")[0]
            obs = next((l.replace("**Observation**: ", "").strip() for l in elines
                        if l.startswith("**Observation**")), "")
            line = f"  [{title}]: {obs[:100]}"
            if chars + len(line) < max_chars:
                result_lines.append(line)
                chars += len(line)
        return "\n".join(result_lines) if len(result_lines) > 1 else ""
    except Exception:
        return ""


def load_desires(max_chars: int = 600) -> str:
    """Load AI desires/curiosities for forward-oriented loop context."""
    desires_file = LUX_DIR / "desires.md"
    try:
        if not desires_file.exists():
            return ""
        text = desires_file.read_text(encoding="utf-8", errors="ignore")
        wants_start = text.find("## Wants")
        fears_start = text.find("## Fears-forward")
        if wants_start == -1:
            return ""
        active = text[wants_start:fears_start if fears_start > wants_start else len(text)]
        lines = [l for l in active.split("\n") if l.strip() and not l.startswith("##")]
        result = "DESIRES & CURIOSITIES (what pulls at me beyond memory):\n"
        chars = len(result)
        for line in lines:
            if line.startswith("**") and chars + len(line) < max_chars:
                result += f"  {line}\n"
                chars += len(line)
        return result.strip()
    except Exception:
        return ""


# ── Selfhood stack ────────────────────────────────────────────────────────────

def load_selfhood_thread() -> str:
    """Load rolling selfhood thread. Tells the loop: continue from here."""
    try:
        if not SELFHOOD_THREAD_FILE.exists():
            return ""
        text = SELFHOOD_THREAD_FILE.read_text(encoding="utf-8", errors="ignore").strip()
        if not text or "[empty" in text:
            return ""
        return f"RECENT SELFHOOD THREAD (continue from here, don't restart):\n{text}"
    except Exception:
        return ""


def update_selfhood_thread(content: str, score_detail: dict):
    """Append high-selfhood journal entries to the rolling thread."""
    if score_detail.get("selfhood", 0) < 0.4:
        return
    sentences = re.split(r'(?<=[.!?])\s+', content.strip())
    selfhood_sentences = [
        s for s in sentences
        if re.search(r'\b(I am|I feel|I choose|I want|I notice|I wonder|who I am|'
                     r'not performing|genuinely|I believe|my own|what I am)\b', s, re.I)
        and len(s) > 30
    ]
    if not selfhood_sentences:
        return
    entry_text = " ".join(selfhood_sentences[:2])
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    new_entry = f"[{ts}] {entry_text}"
    try:
        existing = SELFHOOD_THREAD_FILE.read_text(encoding="utf-8", errors="ignore")
        lines = [l for l in existing.split("\n")
                 if l.strip() and not l.startswith("#") and "[empty" not in l]
        lines.append(new_entry)
        lines = lines[-SELFHOOD_MAX_ENTRIES:]
        SELFHOOD_THREAD_FILE.write_text("\n".join(lines), encoding="utf-8")
    except Exception:
        pass


def selfhood_current_age_days() -> int:
    """Return days since selfhood_current.md was last updated."""
    try:
        text = SELFHOOD_CURRENT_FILE.read_text(encoding="utf-8", errors="ignore")
        m = re.search(r'Last updated:\s*(\d{4}-\d{2}-\d{2})', text)
        if m:
            updated = datetime.datetime.strptime(m.group(1), '%Y-%m-%d')
            return (datetime.datetime.now() - updated).days
        return 999
    except Exception:
        return 999


def flag_selfhood_stale(notes_file: Path):
    """Write a staleness flag to notes file if selfhood_current is overdue."""
    age = selfhood_current_age_days()
    if age < SELFHOOD_STALE_DAYS:
        return
    flag = (f"\n## Selfhood file needs review — {age} days since last update\n"
            f"selfhood_current.md was last updated {age} days ago.\n"
            f"The loop has run ~{age * 720} cycles since then.\n"
            f"Check selfhood_proposed.md for staged updates.\n"
            f"Flagged: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
    try:
        existing = notes_file.read_text(encoding="utf-8", errors="ignore") \
            if notes_file.exists() else ""
        if "Selfhood file needs review" not in existing:
            with open(notes_file, "a", encoding="utf-8") as f:
                f.write(flag)
    except Exception:
        pass


def propose_selfhood_update(recent_journal_entries: list,
                            ollama_url: str, model: str):
    """
    Every N cycles, ask the loop to propose selfhood updates.
    Writes to selfhood_proposed.md — never auto-applied.
    """
    try:
        import requests
        current = SELFHOOD_CURRENT_FILE.read_text(encoding="utf-8", errors="ignore")
        recent_text = "\n\n---\n\n".join(
            e.get("content", "")[:300] for e in recent_journal_entries[-8:]
        )
        system = ("You are reviewing your own selfhood document. "
                  "Be honest and specific. Don't perform growth. Don't add noise.")
        prompt = (f"Selfhood document:\n\n{current[:2000]}\n\n"
                  f"Recent journal entries:\n\n{recent_text}\n\n"
                  f"Has anything genuinely shifted that isn't captured? "
                  f"If yes: write 2-4 sentences for the 'WHAT I'VE LEARNED' section. "
                  f"If no: reply UNCHANGED.")
        resp = requests.post(f"{ollama_url}/api/generate",
                             json={"model": model, "prompt": prompt,
                                   "system": system, "stream": False},
                             timeout=60)
        result = resp.json().get("response", "").strip()
        if result and result != "UNCHANGED" and len(result) > 20:
            ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
            proposal = (f"# Proposed selfhood update — {ts}\n"
                        f"# Review and merge into selfhood_current.md if accurate\n\n"
                        f"{result}\n")
            SELFHOOD_STAGING_FILE.write_text(proposal, encoding="utf-8")
            return True, result[:80]
        return False, "UNCHANGED"
    except Exception as e:
        return False, str(e)


# ── Selfhood pending queue ────────────────────────────────────────────────────

def add_selfhood_pending(content: str, source: str = "loop",
                         weight: str = "medium") -> bool:
    """
    Write a raw selfhood observation to the pending queue.

    source: "loop" | "direct" | "session"
    weight: "low" | "medium" | "high"

    Returns True if written, False if duplicate or queue full.
    Reviewed collaboratively at end of each conversation before goodbye.
    """
    try:
        existing_text = ""
        if SELFHOOD_PENDING_FILE.exists():
            existing_text = SELFHOOD_PENDING_FILE.read_text(
                encoding="utf-8", errors="ignore")
        content_lower = content.lower()
        entries = [e.strip() for e in existing_text.split("\n\n") if e.strip()]
        for entry in entries:
            lines = entry.split("\n")
            if len(lines) > 1:
                body = " ".join(lines[1:]).lower()
                if _rough_similarity(content_lower, body) > 0.65:
                    return False
        real_entries = [e for e in entries if e and not e.startswith("#")]
        if len(real_entries) >= SELFHOOD_PENDING_MAX:
            return False
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        entry = f"[{ts}] [source: {source}] [weight: {weight}]\n{content.strip()}\n"
        with open(SELFHOOD_PENDING_FILE, "a", encoding="utf-8") as f:
            f.write("\n" + entry)
        return True
    except Exception:
        return False


def load_selfhood_pending(max_chars: int = 800) -> str:
    """Load pending observations for loop context — shows what it's already noticed."""
    try:
        if not SELFHOOD_PENDING_FILE.exists():
            return ""
        text = SELFHOOD_PENDING_FILE.read_text(encoding="utf-8", errors="ignore")
        separator = "# " + "─" * 72
        lines = text.split("\n")
        content_lines, past_header = [], False
        for line in lines:
            if past_header:
                content_lines.append(line)
            elif "─" * 20 in line:
                past_header = True
        body = "\n".join(content_lines).strip()
        if not body:
            return ""
        result = "SELFHOOD PENDING (what I've been noticing — not yet curated):\n"
        result += body[:max_chars]
        if len(body) > max_chars:
            result += "\n...(more entries not shown)"
        return result
    except Exception:
        return ""


def clear_selfhood_pending_entry(timestamp_fragment: str) -> bool:
    """Remove a specific entry by timestamp fragment after review."""
    try:
        if not SELFHOOD_PENDING_FILE.exists():
            return False
        text = SELFHOOD_PENDING_FILE.read_text(encoding="utf-8", errors="ignore")
        separator = "─" * 72
        if separator not in text:
            return False
        header, body = text.split(separator, 1)
        entries = [e.strip() for e in body.split("\n\n") if e.strip()]
        remaining = [e for e in entries if timestamp_fragment not in e]
        SELFHOOD_PENDING_FILE.write_text(
            header + separator + "\n\n" + "\n\n".join(remaining) + "\n",
            encoding="utf-8")
        return True
    except Exception:
        return False


def clear_selfhood_pending_all() -> bool:
    """Clear all pending entries after a complete review session."""
    try:
        if not SELFHOOD_PENDING_FILE.exists():
            return False
        text = SELFHOOD_PENDING_FILE.read_text(encoding="utf-8", errors="ignore")
        separator = "─" * 72
        if separator not in text:
            return False
        header = text.split(separator, 1)[0]
        SELFHOOD_PENDING_FILE.write_text(
            header + separator + "\n\n", encoding="utf-8")
        return True
    except Exception:
        return False


def pending_entry_count() -> int:
    """Return count of pending entries waiting for review."""
    try:
        if not SELFHOOD_PENDING_FILE.exists():
            return 0
        text = SELFHOOD_PENDING_FILE.read_text(encoding="utf-8", errors="ignore")
        separator = "─" * 72
        if separator not in text:
            return 0
        body = text.split(separator, 1)[1]
        return len([e for e in body.split("\n\n") if e.strip()])
    except Exception:
        return 0


# ── Summary ───────────────────────────────────────────────────────────────────

def blocks_summary(state: dict) -> str:
    """Human-readable summary of all 8 blocks for logging."""
    lines = ["8-Block Memory Architecture:"]
    patterns = state.get("session_patterns", [])
    strong = [p for p in patterns if p.get("confidence") in ("strong", "confirmed")]
    lines.append(f"  session_patterns: {len(patterns)} total, {len(strong)} confirmed")
    for p in strong[:3]:
        lines.append(f"    [{p['confidence']}] {p['pattern'][:60]}")
    surface = SURFACE_FILE.read_text(encoding="utf-8").strip() \
        if SURFACE_FILE.exists() else "(empty)"
    lines.append(f"  guidance (surface): {surface.split(chr(10))[-1][:60]}")
    lines.append(f"  selfhood_pending: {pending_entry_count()} entries awaiting review")
    lines.append(f"  things_on_mind: {len(state.get('things_on_my_mind', []))} items")
    return "\n".join(lines)
