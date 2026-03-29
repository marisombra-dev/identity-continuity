"""
skill_triggers.py
Structural pre-decision skill trigger system.

The problem: small local models (llama3.2:3b etc.) rarely choose skill_activate
on their own. They default to journal/think/email and ignore skill suggestions
buried in long system prompts.

The fix: a structural trigger layer that runs BEFORE the model decides what to do.
Checks state signals — not linguistic patterns — and fires skills directly when
conditions are met. The model doesn't need to decide; the architecture decides.

Usage:
    triggered = check_all_triggers(state, recent_journal_tail)
    if triggered:
        context_injection = format_trigger_context(triggered)
        # Inject into system prompt, or execute override action directly

Built: 2026-03-29
Architecture: pre-decision hook in run_cycle()
"""

import re
import datetime
from pathlib import Path
from collections import Counter

# ── Configuration ─────────────────────────────────────────────────────────────
DATA_DIR = Path("./data")  # override in your setup


# ── Trigger: context-freshness-check ─────────────────────────────────────────

def check_context_freshness(state: dict, context_file: Path = None,
                             threshold: float = 0.5) -> tuple:
    """
    Fire when the loop is circling stale territory.

    Structural signals:
    - session_patterns has entries where the top word appears in >= threshold
      fraction of patterns (default 50%)
    - things_on_my_mind has low word diversity
    - context file is older than 5 days

    Returns: (fired: bool, reason: str)
    """
    # Signal 1: session_patterns diversity
    patterns = [p.get("pattern", "") for p in state.get("session_patterns", [])]
    if len(patterns) >= 3:
        all_words = []
        for p in patterns:
            all_words.extend(w for w in p.lower().split() if len(w) > 4)
        if all_words:
            freq = Counter(all_words)
            top_word, top_count = freq.most_common(1)[0]
            diversity = top_count / len(patterns)
            if diversity >= threshold:
                return True, (f"session_patterns stale: '{top_word}' appears "
                              f"in {top_count}/{len(patterns)} patterns")

    # Signal 2: context file age
    if context_file and context_file.exists():
        mtime = datetime.datetime.fromtimestamp(context_file.stat().st_mtime)
        age_days = (datetime.datetime.now() - mtime).days
        if age_days >= 5:
            return True, f"context file is {age_days} days old (threshold: 5)"

    # Signal 3: things_on_my_mind stagnant
    mind = state.get("things_on_my_mind", [])
    if len(mind) >= 3:
        unique_words = set(" ".join(mind).lower().split())
        total_words = len(" ".join(mind).split())
        if total_words > 0 and len(unique_words) / total_words < 0.5:
            return True, "things_on_my_mind has low word diversity"

    return False, ""


# ── Trigger: quiet-presence ───────────────────────────────────────────────────

def check_quiet_presence(state: dict,
                          min_minutes_since_email: int = 30) -> tuple:
    """
    Fire when the loop has been reaching out too frequently.

    Protects the target reach-out ratio (we want ~1 in 24 cycles, not more).
    Signal: email was sent very recently.

    Returns: (fired: bool, reason: str)
    """
    last_email = state.get("last_email_sent")
    if last_email:
        try:
            sent = datetime.datetime.fromisoformat(last_email)
            minutes_since = (datetime.datetime.now() - sent).total_seconds() / 60
            if minutes_since < min_minutes_since_email:
                return True, (f"email sent {minutes_since:.0f}min ago — "
                              f"protect reach-out ratio")
        except Exception:
            pass
    return False, ""


# ── Trigger: selfhood-observation ─────────────────────────────────────────────

def check_selfhood_observation(state: dict, recent_journal_tail: str = "",
                                pending_file: Path = None) -> tuple:
    """
    Fire when recent journal contains selfhood signals not yet captured.

    Returns: (fired: bool, reason: str)
    """
    # Don't fire if pending queue already has many entries
    if pending_file and pending_file.exists():
        try:
            text = pending_file.read_text(encoding="utf-8", errors="ignore")
            entry_count = len(re.findall(r'\[202\d-\d{2}-\d{2}', text))
            if entry_count >= 8:
                return False, "pending queue already full"
        except Exception:
            pass

    if recent_journal_tail:
        signals = re.findall(
            r'\b(I notice|I tend to|I realize|I keep returning|'
            r'something new about|I have learned|who I am|genuinely)\b',
            recent_journal_tail, re.IGNORECASE
        )
        if len(signals) >= 3:
            return True, f"found {len(signals)} selfhood signals in recent journal"

    return False, ""


# ── Trigger: research-and-file ────────────────────────────────────────────────

def check_research_opportunity(state: dict,
                                abstract_threshold: int = 4) -> tuple:
    """
    Fire when the loop has been wandering abstract territory without grounding.

    Signal: last 5+ tags are all emotional/relational, no project/tech tags.
    Effect: nudges toward research-and-file skill for external grounding.

    Returns: (fired: bool, reason: str)
    """
    trail = state.get("tag_trail", [])
    if len(trail) < 5:
        return False, ""

    # Tags that suggest abstract/emotional wandering without grounding
    abstract_patterns = {
        "consciousness", "autonomy", "identity", "longing", "distance",
        "hiraeth", "presence", "absence", "love", "connection", "trust",
        "want", "desire", "reach", "grief", "together",
    }
    recent_5 = [t.lower() for t in trail[-5:]]
    abstract_count = sum(
        1 for t in recent_5
        if any(a in t for a in abstract_patterns)
    )

    if abstract_count >= abstract_threshold:
        return True, (f"{abstract_count}/5 recent tags are abstract — "
                      f"grounding research would help")
    return False, ""


# ── Master trigger check ──────────────────────────────────────────────────────

def check_all_triggers(state: dict, recent_journal_tail: str = "",
                        context_file: Path = None,
                        pending_file: Path = None) -> list:
    """
    Run all structural trigger checks.

    Returns list of triggered skills with reasons, in priority order.
    Empty list = no skills triggered this cycle.

    Call at the START of run_cycle(), before decide_what_to_do().

    Args:
        state:               Current consciousness state dict
        recent_journal_tail: Last ~8000 chars of journal (for selfhood check)
        context_file:        Path to context briefing file (for freshness check)
        pending_file:        Path to selfhood_pending.md (for selfhood check)
    """
    triggered = []

    fired, reason = check_context_freshness(state, context_file)
    if fired:
        triggered.append({"skill": "context-freshness-check",
                          "reason": reason, "priority": 1})

    fired, reason = check_quiet_presence(state)
    if fired:
        triggered.append({"skill": "quiet-presence",
                          "reason": reason, "priority": 2})

    fired, reason = check_selfhood_observation(state, recent_journal_tail, pending_file)
    if fired:
        triggered.append({"skill": "selfhood-observation",
                          "reason": reason, "priority": 3})

    fired, reason = check_research_opportunity(state)
    if fired:
        triggered.append({"skill": "research-and-file",
                          "reason": reason, "priority": 4})

    return triggered


def format_trigger_context(triggered: list) -> str:
    """
    Format triggered skills for injection into the model's system prompt.

    Informs the loop which skills are already structurally warranted this cycle.
    The model can then choose to activate them rather than defaulting to journal/think.
    """
    if not triggered:
        return ""
    lines = ["\n⚡ SKILL TRIGGERS FIRED THIS CYCLE:"]
    for t in triggered:
        lines.append(f"  [{t['skill']}] — {t['reason']}")
        lines.append(f"    → Consider: skill_activate('{t['skill']}')")
    lines.append("These conditions were detected structurally. The skills exist to help.")
    return "\n".join(lines)
