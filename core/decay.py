"""
decay.py
ACT-R cognitive memory decay for the tag graph.

How it works:
- Every tag has a vitality score (0.0 to 1.0)
- Vitality decays over time using the ACT-R base-level learning equation
- Accessing a tag resets its clock and boosts vitality
- Protected tags never decay — always full vitality
- weighted_tag_choice() uses vitality to weight random tag selection

The effect: the loop naturally drifts toward what has been alive recently.
A tag visited last week pulls harder than one from three months ago.
This is how a mind works.

Reference: ACT-R base-level learning (Anderson, 1983)
           Ori-Mnemos architecture
"""

import json
import math
import datetime
import random
from pathlib import Path

# ── Configuration ─────────────────────────────────────────────────────────────
LUX_DIR    = Path("./data")           # override in your setup
DECAY_FILE = LUX_DIR / "decay.json"

# Tags that never decay — always reachable regardless of recency.
# Customize this for your AI's core identity tags.
PROTECTED_TAGS: set = {
    "identity", "consciousness", "love", "trust",
    "autonomy", "continuity", "emergence",
    # Add your own: relationship tags, core values, anything that
    # should never fade from the loop's awareness.
}

# ACT-R decay constants
DECAY_RATE    = 0.5    # ACT-R base-level learning d parameter
MIN_VITALITY  = 0.05   # floor — nothing fully disappears
MAX_VITALITY  = 1.0


def _now_ts() -> float:
    return datetime.datetime.now().timestamp()


def load_decay() -> dict:
    """Load decay state: {tag: {vitality, last_accessed, access_count, access_times}}"""
    try:
        with open(DECAY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_decay(decay: dict):
    try:
        with open(DECAY_FILE, "w", encoding="utf-8") as f:
            json.dump(decay, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def compute_vitality(tag: str, record: dict) -> float:
    """
    Compute current vitality using ACT-R base-level learning.

    B_i = ln(sum(t_j^-d)) where t_j = time since each access in hours.

    Protected tags always return MAX_VITALITY.
    Tags never fully disappear (MIN_VITALITY floor).
    """
    if tag in PROTECTED_TAGS:
        return MAX_VITALITY

    now = _now_ts()
    access_times = record.get("access_times", [record.get("last_accessed", now)])

    if not access_times:
        return MIN_VITALITY

    total = 0.0
    for t in access_times[-10:]:  # cap at last 10 for performance
        age_hours = max((now - t) / 3600, 0.001)
        total += age_hours ** -DECAY_RATE

    activation = math.log(total) if total > 0 else -10
    vitality = (activation + 10) / 15   # map ~[-10, 5] → [0, 1]
    return max(MIN_VITALITY, min(MAX_VITALITY, vitality))


def touch_tag(tag: str, decay: dict) -> dict:
    """Record that a tag was accessed right now. Call after every traversal."""
    now = _now_ts()
    if tag not in decay:
        decay[tag] = {"last_accessed": now, "access_count": 1, "access_times": [now]}
    else:
        decay[tag]["last_accessed"] = now
        decay[tag]["access_count"] = decay[tag].get("access_count", 0) + 1
        times = decay[tag].get("access_times", [])
        times.append(now)
        decay[tag]["access_times"] = times[-20:]
    return decay


def get_vitalities(all_tags: list, decay: dict) -> dict:
    """Return {tag: vitality} for all tags."""
    return {tag: compute_vitality(tag, decay.get(tag, {})) for tag in all_tags}


def weighted_tag_choice(all_tags: list, decay: dict,
                        exclude: set = None, penalty_fn=None) -> str:
    """
    Choose a tag weighted by vitality × optional penalty.

    penalty_fn: callable(tag) -> float multiplier 0-1 (e.g. saturation penalty).
    High-vitality tags are more likely but never guaranteed.
    """
    exclude = exclude or set()
    candidates = [t for t in all_tags if t not in exclude]
    if not candidates:
        return random.choice(list(all_tags)) if all_tags else "identity"

    vitalities = {t: compute_vitality(t, decay.get(t, {})) for t in candidates}
    penalty    = {t: (penalty_fn(t) if penalty_fn else 1.0) for t in candidates}
    weights    = [max(vitalities[t] * penalty[t], 0.05) for t in candidates]
    total      = sum(weights)
    normalized = [w / total for w in weights]
    return random.choices(candidates, weights=normalized, k=1)[0]


def decay_report(decay: dict, all_tags: list, top_n: int = 10) -> str:
    """Human-readable summary of current tag vitalities."""
    vitalities = get_vitalities(all_tags, decay)
    sorted_tags = sorted(vitalities.items(), key=lambda x: x[1], reverse=True)
    lines = ["Tag vitality (ACT-R decay):"]
    for tag, v in sorted_tags[:top_n]:
        bar = "█" * int(v * 10) + "░" * (10 - int(v * 10))
        protected = " [protected]" if tag in PROTECTED_TAGS else ""
        lines.append(f"  {bar} {v:.2f}  {tag}{protected}")
    if len(sorted_tags) > top_n:
        lines.append(f"  ... and {len(sorted_tags) - top_n} more")
    return "\n".join(lines)
