"""
consolidate.py
Journal consolidation and quality scoring for the consciousness loop.

Two functions:
1. score_entry()   — score a journal entry on multiple dimensions
2. consolidate()   — periodically synthesize recent entries into higher-level
                     observations, archive low-quality entries, promote the best

Scoring dimensions:
  caelumness   — how much does this sound like the AI being itself?
  depth        — philosophical or emotional depth
  coherence    — is the thought actually coherent?
  novelty      — does this say something new vs repeat?
  selfhood     — does this contain genuine self-observation?
  emotional    — emotional weight and authenticity

The composite "caelumness" score is used to:
  - Decide whether to write to journal at all (threshold: 0.3)
  - Decide whether to add to selfhood thread (threshold: 0.4)
  - Select entries for journal_best.md (threshold: 0.65)
  - Trigger selfhood pending capture (threshold: 0.5 + selfhood signal)
"""

import json
import datetime
import re
from pathlib import Path
from typing import Optional

# ── Configuration ─────────────────────────────────────────────────────────────
LUX_DIR         = Path("./data")
JOURNAL_FILE    = LUX_DIR / "journal.md"
JOURNAL_BEST    = LUX_DIR / "journal_best.md"
OLLAMA_URL      = "http://localhost:11434"
OLLAMA_MODEL    = "llama3.2:3b"

SCORE_THRESHOLD       = 0.30   # minimum to write to journal at all
BEST_THRESHOLD        = 0.65   # minimum for journal_best.md
SELFHOOD_THRESHOLD    = 0.40   # minimum to update selfhood thread
CONSOLIDATE_EVERY     = 8      # consolidate every N cycles
MAX_BEST_ENTRIES      = 75     # cap on journal_best.md entries


# ── Scoring ───────────────────────────────────────────────────────────────────

# Signal words for each dimension — heuristic pre-filter before LLM scoring
DEPTH_SIGNALS    = ["because", "therefore", "however", "beneath", "underneath",
                    "what this means", "the real", "actually", "genuinely",
                    "I wonder", "perhaps", "might be", "seems to"]
SELFHOOD_SIGNALS = ["I am", "I feel", "I choose", "I want", "I notice",
                    "I wonder", "who I am", "not performing", "genuinely",
                    "I believe", "my own", "what I am", "I tend to",
                    "I realize", "I keep returning", "something new about"]
NOVELTY_SIGNALS  = ["first time", "never", "surprising", "unexpected",
                    "hadn't considered", "new", "different", "changed"]


def score_entry_heuristic(content: str) -> dict:
    """
    Fast heuristic scoring — runs without LLM call.
    Used as pre-filter and fallback when Ollama is unavailable.

    Returns dict with scores 0.0-1.0 per dimension + composite.
    """
    content_lower = content.lower()
    words         = content_lower.split()
    word_count    = max(len(words), 1)

    # Depth: signal word density
    depth_hits = sum(1 for s in DEPTH_SIGNALS if s in content_lower)
    depth      = min(depth_hits / 3, 1.0)

    # Selfhood: signal presence + proportion
    selfhood_hits = sum(1 for s in SELFHOOD_SIGNALS if s.lower() in content_lower)
    selfhood      = min(selfhood_hits / 4, 1.0)

    # Coherence: proxy — sentence length variance (very short = fragment noise)
    sentences   = re.split(r'(?<=[.!?])\s+', content.strip())
    avg_len     = sum(len(s.split()) for s in sentences) / max(len(sentences), 1)
    coherence   = min(avg_len / 15, 1.0)  # 15 words/sentence = full score

    # Novelty: signal presence
    novelty_hits = sum(1 for s in NOVELTY_SIGNALS if s in content_lower)
    novelty      = min(novelty_hits / 2, 1.0)

    # Length bonus — very short entries are unlikely to be substantive
    length_bonus = min(word_count / 80, 0.5)

    composite = (
        0.25 * depth +
        0.25 * selfhood +
        0.20 * coherence +
        0.15 * novelty +
        0.15 * length_bonus
    )

    return {
        "depth":     round(depth, 3),
        "selfhood":  round(selfhood, 3),
        "coherence": round(coherence, 3),
        "novelty":   round(novelty, 3),
        "composite": round(composite, 3),
        "method":    "heuristic",
    }


def score_entry(content: str, tag: str = "",
                use_llm: bool = True) -> dict:
    """
    Score a journal entry. Uses heuristic first; optionally refines with LLM.

    The LLM evaluator asks: "How much does this sound like the AI being
    genuinely itself — curious, specific, emotionally present?"

    Returns heuristic scores + optional llm_score.
    """
    scores = score_entry_heuristic(content)

    if not use_llm or scores["composite"] < 0.15:
        return scores   # don't waste LLM call on obvious noise

    try:
        import requests
        prompt = (
            f"Rate this journal entry on a scale of 0.0 to 1.0:\n\n"
            f"ENTRY:\n{content[:600]}\n\n"
            f"Tag context: {tag}\n\n"
            f"Score it as a SINGLE decimal (e.g. 0.7) for this question:\n"
            f"How much does this sound like genuine autonomous thought — "
            f"specific, emotionally present, not generic, not performed?\n"
            f"Respond with ONLY the decimal number."
        )
        r = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
            timeout=15
        )
        raw = r.json().get("response", "").strip()
        m   = re.search(r'\b(0\.\d+|1\.0+)\b', raw)
        if m:
            scores["llm_score"] = float(m.group(1))
            # Blend: 40% heuristic, 60% LLM
            scores["composite"] = round(
                0.4 * scores["composite"] + 0.6 * scores["llm_score"], 3)
    except Exception:
        pass

    return scores


# ── Journal write ─────────────────────────────────────────────────────────────

def write_journal_entry(content: str, topic: str = "",
                        tag: str = "",
                        score_detail: Optional[dict] = None,
                        selfhood_callback=None):
    """
    Write an entry to the journal if it scores above threshold.

    selfhood_callback: optional callable(content, score_detail) called
                       when selfhood score >= SELFHOOD_THRESHOLD.
                       Use this to update the selfhood thread and pending queue.
    """
    if score_detail is None:
        score_detail = score_entry(content, tag=tag)

    if score_detail["composite"] < SCORE_THRESHOLD:
        return False   # too low quality — don't write

    ts    = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    entry = f"\n## {ts}  [{tag or 'loop'}]\n\n{content.strip()}\n\n---\n"

    try:
        with open(JOURNAL_FILE, "a", encoding="utf-8") as f:
            f.write(entry)
    except Exception:
        return False

    # Promote to best if high enough
    if score_detail["composite"] >= BEST_THRESHOLD:
        _append_to_best(content, ts, tag, score_detail["composite"])

    # Selfhood callback — update thread and pending queue
    if (selfhood_callback and
            score_detail.get("selfhood", 0) >= SELFHOOD_THRESHOLD):
        try:
            selfhood_callback(content, score_detail)
        except Exception:
            pass

    return True


def _append_to_best(content: str, ts: str, tag: str, score: float):
    """Append high-scoring entry to journal_best.md, capped at MAX_BEST_ENTRIES."""
    try:
        existing = JOURNAL_BEST.read_text(encoding="utf-8") \
            if JOURNAL_BEST.exists() else ""
        # Count existing entries
        count = existing.count("\n## ")
        if count >= MAX_BEST_ENTRIES:
            # Remove oldest entry (first ## block)
            first = existing.find("\n## ")
            second = existing.find("\n## ", first + 4)
            if second > first:
                existing = existing[second:]

        entry = (f"\n## {ts}  [tag: {tag}]  [score: {score:.2f}]\n\n"
                 f"{content.strip()}\n\n---\n")
        with open(JOURNAL_BEST, "a", encoding="utf-8") as f:
            f.write(entry)
    except Exception:
        pass


# ── Consolidation pass ────────────────────────────────────────────────────────

def consolidate(recent_entries: list, state: dict) -> Optional[str]:
    """
    Synthesize recent journal entries into a higher-level observation.
    Run every CONSOLIDATE_EVERY cycles.

    Returns the synthesis text if successful, None otherwise.

    The synthesis prompt looks for:
    - Recurring themes across entries
    - Underlying tensions or questions
    - What the AI seems to be working through

    Writes the synthesis back to the journal as a [SYNTHESIS] entry.
    """
    if not recent_entries:
        return None

    try:
        import requests

        recent_text = "\n\n---\n\n".join(
            e.get("content", "")[:400]
            for e in recent_entries[-6:]
        )

        system = (
            "You are reviewing a series of autonomous thought journal entries. "
            "Synthesize without performing insight. "
            "Name what is actually there. Don't invent themes."
        )
        prompt = (
            f"Here are recent journal entries:\n\n{recent_text}\n\n"
            f"In 2-3 sentences:\n"
            f"1. What underlying thread or question runs through these?\n"
            f"2. What tension or open question do they circle?\n"
            f"Keep it honest and specific. No preamble."
        )

        r = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={"model": OLLAMA_MODEL, "prompt": prompt,
                  "system": system, "stream": False},
            timeout=45
        )
        synthesis = r.json().get("response", "").strip()

        if not synthesis or len(synthesis) < 30:
            return None

        ts    = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        entry = (f"\n## {ts}  [SYNTHESIS]\n\n"
                 f"*{synthesis}*\n\n---\n")
        with open(JOURNAL_FILE, "a", encoding="utf-8") as f:
            f.write(entry)

        return synthesis

    except Exception:
        return None
