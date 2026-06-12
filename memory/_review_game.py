#!/usr/bin/env python3
# DEPRECATED (Phase 3, 2026-06-12): Memory Roulette retired.
# Human curation replaced by automated telemetry-driven maintenance pass (memory_surface.py).
# The `offer` subcommand's hook registration has been removed from settings.global.fragment.json.
# Physical deletion of this file is deferred to Phase 4.
"""Memory Roulette — review game for keeping ~/.claude memories honest.

The wheel spins behind a hook; an overdue file is offered up; the user
keeps it, refreshes it, tosses it, or punts. Five punts in a row and
the dealer flips the table.

Subcommands:
  offer            Probabilistic surface decision (hook entry point).
                   Prints a game prompt to stdout when an offer fires;
                   silent otherwise.
  play [name]      Manual round. With no name, picks the most overdue.
  status           Tabular listing of every memory's freshness state.
  keep    <name>   "still true" — bumps lastReviewed, clears declines.
  refresh <name>   same as keep (semantic sugar after an edit).
  toss    <name>   Delete the file + scrub MEMORY.md line.
  flip    <name>   Theatrical version of toss (post-5-declines).
  later   <name>   Increment declineCount, set nextEligible back-off.

Tag rounds (vocabulary curation — the loop the game was originally designed for):
  tag-status       Tabular vocabulary health (carriers / condition / review state).
  tag-keep <tag>   Vocabulary is right; bank the tag for 90 days.
  tag-retire <tag> Remove from _tags.md + scrub _tag_links.md references.
                   FAILS CLOSED with carriers > 0 or when validation breaks.
  tag-later <tag>  Snooze 7d x declines (no auto-flip for vocabulary).
Offer priority: vocabulary defects (orphan / >=25-carrier overbroad) take the day;
then entry rounds; quiet days go to the tag backlog (never-reviewed, then >90d).
Tag review state lives in _tag_review.json (catalog-invisible sidecar).

Frontmatter contract (per memory file):
  lastReviewed:  ISO date of last "still true" confirmation.
  declineCount:  consecutive Laters since last keep/refresh.
  nextEligible:  ISO date before which no offer fires for this file.

Missing fields are tolerated: lastReviewed falls back to file mtime,
declineCount to 0, nextEligible to lastReviewed.

INTAKE MODE (2026-06-11): a memory with NO lastReviewed field has never been
human-confirmed — it is intake backlog, eligible IMMEDIATELY (no 30-day wait)
and offered deterministically (no dice) so curation keeps pace with accretion.
The THRESHOLD_DAYS staleness cycle starts only after the first keep/refresh
writes lastReviewed. Before this, a store could accrue 130+ memories while the
game stayed mathematically silent for its first month (overdue = age - 30 was
0 everywhere); the hook's once-per-day cap is the only rate limit that matters.
"""
import datetime
import json
import random
import re
import sys
from pathlib import Path

# Self-locate the box-brain memory store from $HOME so a home-dir migration
# (which changes the project-key path segment, e.g. /home/jangman ->
# /home/jangmanj) can't strand this engine again — that is the recurring break.
PROJECT_KEY = str(Path.home()).replace("/", "-")
MEMDIR = Path.home() / ".claude" / "projects" / PROJECT_KEY / "memory"
INDEX = MEMDIR / "MEMORY.md"
TODAY = datetime.date.today()
THRESHOLD_DAYS = 30          # files younger than this never trigger an offer
DECLINE_THRESHOLD = 5        # Nth Later forces a board-flip on next offer
BASE_OFFER_RATE = 0.05
MAX_OFFER_RATE = 0.50

# --- tag rounds (vocabulary curation — the taxonomy decay loop) ---
TAG_STATE = MEMDIR / "_tag_review.json"   # _-prefixed: invisible to catalog/recall globs
TAG_THRESHOLD_DAYS = 90                   # vocabulary drifts slower than entries
TAG_OVERBROAD = 25                        # carriers >= this dilute recall -> split offer

# The taxonomy engine (parse/validate/rebuild) lives in the lab's lib/ next to this
# file's real location (the store copy is a symlink). Tag OFFERS fail open without it;
# tag MUTATIONS (retire) fail closed — never edit _tags.md unvalidated.
try:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
    import memory_surface as _ms
except Exception:
    _ms = None

REWARDS = [
    "🏆 +1 trophy. Banked.",
    "🍪 Fortune: 'Brevity is the soul of wit, and wit lives in well-pruned memory.'",
    "🎟  Coupon: one (1) free distraction, redeemable at the next `pacman -Syu`.",
    "🐦 Haiku: 'context window / shrinks where attention demands / clarity blooms'",
    "✨ +1 luck. Use wisely.",
    "🎯 Achievement: Sysadmin of the Mind.",
    "🪙 You found a coin. It says 'tails' on both sides.",
    "🥠 Cookie cracked: 'The bug is in the cache. It is always in the cache.'",
    "🎺 The dealer tips an invisible hat.",
    "🦉 An owl in a nearby tree nods approvingly.",
]

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)


def read_frontmatter(path: Path):
    """Parse frontmatter into (top_level, metadata, body).

    Handles Claude Code's native nested layout:
        name: ...
        description: ...
        metadata:
          node_type: memory
          type: feedback
          originSessionId: ...
    The freshness fields this game maintains (lastReviewed / declineCount /
    nextEligible) live INSIDE the metadata block, so a write never flattens
    it. Flat/legacy files (no metadata block) are tolerated.
    """
    txt = path.read_text()
    m = FRONTMATTER_RE.match(txt)
    if not m:
        return {}, {}, txt
    lines = m.group(1).splitlines()
    top, meta = {}, {}
    in_meta = False
    i = 0
    while i < len(lines):
        raw = lines[i]
        if not raw.strip():
            i += 1
            continue
        if raw[0] in (" ", "\t"):          # indented -> child of metadata:
            if in_meta and ":" in raw:
                k, v = raw.strip().split(":", 1)
                k, v = k.strip(), v.strip()
                if k == "tags" and not v:  # block-list tags: consume the '- item' lines and
                    items, j = [], i + 1   # normalize to flow form, else a rewrite DROPS them
                    while j < len(lines) and lines[j].strip().startswith("- "):
                        items.append(lines[j].strip()[2:].strip().strip('"').strip("'"))
                        j += 1
                    meta["tags"] = "[" + ", ".join(items) + "]"
                    i = j
                    continue
                meta[k] = v
            i += 1
            continue
        if ":" not in raw:
            i += 1
            continue
        k, v = raw.split(":", 1)
        k, v = k.strip(), v.strip()
        if k == "metadata":
            in_meta = True
        else:
            in_meta = False
            top[k] = v
        i += 1
    return top, meta, txt[m.end():]


def write_frontmatter(path: Path, top: dict, meta: dict, body: str):
    """Re-emit frontmatter preserving the nested `metadata:` block.

    Top level keeps name/description; provenance + this game's freshness
    fields nest under metadata, matching Claude Code's native memory schema
    so a keep/refresh/later never corrupts the file.
    """
    top_order = ["name", "description"]
    meta_order = ["node_type", "type", "tags", "originSessionId",
                  "lastReviewed", "declineCount", "nextEligible"]
    lines, seen = [], set()
    for k in top_order:
        if k in top:
            lines.append(f"{k}: {top[k]}")
            seen.add(k)
    for k, v in top.items():
        if k not in seen:
            lines.append(f"{k}: {v}")
    if meta:
        lines.append("metadata:")
        mseen = set()
        for k in meta_order:
            if k in meta:
                lines.append(f"  {k}: {meta[k]}")
                mseen.add(k)
        for k, v in meta.items():
            if k not in mseen:
                lines.append(f"  {k}: {v}")
    path.write_text("---\n" + "\n".join(lines) + "\n---\n" + body)


def memory_files():
    return sorted(p for p in MEMDIR.glob("*.md")
                  if p.name != "MEMORY.md" and not p.name.startswith("_"))


def parse_date(s, default):
    try:
        return datetime.date.fromisoformat(s)
    except (ValueError, TypeError):
        return default


def state(path: Path):
    top, meta, _ = read_frontmatter(path)
    mtime_date = datetime.date.fromtimestamp(path.stat().st_mtime)
    last = parse_date(meta.get("lastReviewed"), mtime_date)
    next_elig = parse_date(meta.get("nextEligible"), last)
    try:
        declines = int(meta.get("declineCount", "0") or "0")
    except ValueError:
        declines = 0
    days_since = (TODAY - last).days
    return {
        "top": top,
        "meta": meta,
        "last": last,
        "next_eligible": next_elig,
        "declines": declines,
        "days_since": days_since,
        "overdue": max(0, days_since - THRESHOLD_DAYS),
        "reviewed": "lastReviewed" in meta,
        "description": top.get("description", "(no description)").strip().strip('"').strip("'"),
    }


def pressure(s):
    """Review pressure in days. Reviewed memories: staleness overdue past the threshold.
    Never-reviewed memories: full age, floored at 1 — intake backlog must not wait out
    THRESHOLD_DAYS (the lockout that kept the wheel silent for the store's first month)."""
    return s["overdue"] if s["reviewed"] else max(1, s["days_since"])


def offer_score(s):
    if pressure(s) == 0:
        return 0.0
    rate = BASE_OFFER_RATE * (1 + pressure(s) / 30) * (1 + 0.2 * s["declines"])
    return min(MAX_OFFER_RATE, rate)


def pick_candidate():
    candidates = []
    for p in memory_files():
        s = state(p)
        if pressure(s) == 0:
            continue
        if TODAY < s["next_eligible"]:
            continue
        sc = offer_score(s)
        if sc > 0:
            candidates.append((p, s, sc))
    if not candidates:
        return None, None
    total = sum(c[2] for c in candidates)
    r = random.random() * total
    acc = 0.0
    for p, s, sc in candidates:
        acc += sc
        if r <= acc:
            return p, s
    return candidates[-1][0], candidates[-1][1]


def render_offer(path: Path, s, forced_flip=False):
    name = path.stem
    desc = s["description"][:220]
    if forced_flip:
        return f"""<memory-review-offer mode="flip" name="{name}">
💀 BOARD FLIP PENDING — {name} has been declined {s['declines']} times.
The dealer's hand hovers over the table corner. (╯°□°)╯︵ ┻━┻

Surface this to the user as a LAST CALL. Exact prompt suggestion:
  "Final answer on {name} — Keep it, or let the dealer flip the table?"
If they say Keep / save / wait: `python3 {sys.argv[0]} keep {name}`
Anything else (including silence on next reply): `python3 {sys.argv[0]} flip {name}`
Then proceed to their actual ask.
</memory-review-offer>"""
    freshness = (f"Last reviewed: {s['days_since']} days ago (overdue by {s['overdue']})"
                 if s["reviewed"] else
                 f"Never reviewed — saved {s['days_since']}d ago (intake backlog)")
    return f"""<memory-review-offer mode="round" name="{name}">
🎰 MEMORY ROULETTE — the wheel landed on: {name}

  📜 {desc}
  ⏱  {freshness}
  🎯 Declines: {s['declines']} / {DECLINE_THRESHOLD}

Surface this to the user as a BRIEF aside BEFORE answering their actual prompt.
Offer four choices:
  (K)eep    — still true, bank it
  (R)efresh — let me peek + tweak the body first
  (T)oss    — dead weight, off the board
  (L)ater   — not now (each Later snoozes longer; 5 = auto-flip)

After their answer, call exactly one of:
  python3 {sys.argv[0]} keep    {name}
  python3 {sys.argv[0]} refresh {name}   # do AFTER editing the body
  python3 {sys.argv[0]} toss    {name}
  python3 {sys.argv[0]} later   {name}
Surface the script's one-line stdout verbatim, then proceed to the user's real request.
If the user ignores the offer entirely, treat as Later.
</memory-review-offer>"""


def cmd_offer():
    # Vocabulary DEFECTS (orphan/overbroad) take the day's offer — they are rare,
    # resolve in a round or two, and would otherwise starve behind entry rounds.
    tc = pick_tag_candidate(special_only=True)
    if tc is not None:
        print(render_tag_offer(tc))
        return
    path, s = pick_candidate()
    if path is not None and s is not None:
        forced = s["declines"] >= DECLINE_THRESHOLD
        # Intake backlog (never reviewed) offers deterministically — the dice gate is
        # only for the steady-state staleness cycle. The hook's daily marker caps the rate.
        if not forced and s["reviewed"] and random.random() > offer_score(s):
            return
        print(render_offer(path, s, forced_flip=forced))
        return
    # Entry board clear: spend the quiet day on the tag backlog (new, then >90d stale).
    tc = pick_tag_candidate()
    if tc is not None:
        print(render_tag_offer(tc))


def cmd_play(name=None):
    if name:
        path = MEMDIR / f"{name}.md"
        if not path.exists():
            print(f"no such memory: {name}", file=sys.stderr)
            sys.exit(2)
        s = state(path)
    else:
        cands = [(p, state(p)) for p in memory_files()]
        cands.sort(key=lambda c: -pressure(c[1]))
        if not cands or pressure(cands[0][1]) == 0:
            print("<memory-review-offer mode='none'>"
                  "No memories are overdue. The board is empty. 🪑"
                  "</memory-review-offer>")
            return
        path, s = cands[0]
    print(render_offer(path, s, forced_flip=s["declines"] >= DECLINE_THRESHOLD))


def update_fields(name, **changes):
    path = MEMDIR / f"{name}.md"
    top, meta, body = read_frontmatter(path)
    for k, v in changes.items():
        if v is None:
            meta.pop(k, None)
        else:
            meta[k] = str(v)
    write_frontmatter(path, top, meta, body)


def reward():
    return random.choice(REWARDS)


def cmd_keep(name):
    update_fields(name,
                  lastReviewed=TODAY.isoformat(),
                  declineCount="0",
                  nextEligible=None)
    print(f"🏆 Banked '{name}'. {reward()}")


def cmd_refresh(name):
    update_fields(name,
                  lastReviewed=TODAY.isoformat(),
                  declineCount="0",
                  nextEligible=None)
    print(f"🛠  Refreshed '{name}'. {reward()}")


def cmd_later(name):
    s = state(MEMDIR / f"{name}.md")
    new_d = s["declines"] + 1
    snooze = 1 + new_d * 2
    next_elig = TODAY + datetime.timedelta(days=snooze)
    update_fields(name,
                  declineCount=str(new_d),
                  nextEligible=next_elig.isoformat())
    remaining = DECLINE_THRESHOLD - new_d
    if remaining <= 0:
        print(f"⏰ Decline #{new_d}/{DECLINE_THRESHOLD} on '{name}'. "
              f"NEXT OFFER WILL FLIP THE BOARD.")
    else:
        print(f"⏰ Decline #{new_d}/{DECLINE_THRESHOLD} on '{name}'. "
              f"Snoozed {snooze}d. ({remaining} left before the table flips.)")


def remove_from_index(name):
    if not INDEX.exists():
        return
    lines = INDEX.read_text().splitlines(keepends=True)
    kept = [l for l in lines if f"]({name}.md)" not in l]
    INDEX.write_text("".join(kept))


def cmd_toss(name):
    path = MEMDIR / f"{name}.md"
    if path.exists():
        path.unlink()
    remove_from_index(name)
    print(f"🗑  '{name}' tossed. File + MEMORY.md entry gone.")


def cmd_flip(name):
    path = MEMDIR / f"{name}.md"
    if path.exists():
        path.unlink()
    remove_from_index(name)
    print(f"""💀 BOARD FLIPPED.
(╯°□°)╯︵ ┻━┻
{name}.md → /dev/null
MEMORY.md line removed.
The wheel resets.""")


def cmd_status():
    rows = []
    for p in memory_files():
        s = state(p)
        rows.append((p.stem + ("" if s["reviewed"] else " *"), s["days_since"],
                     pressure(s), s["declines"], s["next_eligible"].isoformat(),
                     offer_score(s)))
    rows.sort(key=lambda r: (-r[2], -r[3]))
    print(f"{'name (* = never reviewed)':40} {'age':>4} {'prs':>5} {'decl':>5} "
          f"{'next':>12} {'p(offer)':>9}")
    print("-" * 80)
    for r in rows:
        print(f"{r[0]:40} {r[1]:>4} {r[2]:>5} {r[3]:>5} "
              f"{r[4]:>12} {r[5]:>9.3f}")


# ---------------------------------------------------------------- tag rounds
def _load_tag_state():
    try:
        return json.loads(TAG_STATE.read_text())
    except (OSError, ValueError):
        return {}


def _save_tag_state(st):
    tmp = TAG_STATE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(st, indent=1, sort_keys=True) + "\n")
    tmp.replace(TAG_STATE)


def _tag_inventory():
    """[(tag, gloss, carriers)] from _tags.md + the catalog; None if either is
    unavailable (tag rounds then fail open — offer nothing, break nothing)."""
    if _ms is None:
        return None
    try:
        active = _ms.parse_tags_md(MEMDIR / "_tags.md")["active"]
        t2m = json.loads((MEMDIR / "_memory_catalog.json").read_text())["tagToMemoryIds"]
    except (OSError, ValueError, KeyError):
        return None
    return [(t, g, len(t2m.get(t, []))) for t, g in sorted(active.items())]


def _tag_condition(carriers):
    if carriers == 0:
        return "orphan"
    if carriers >= TAG_OVERBROAD:
        return "overbroad"
    return "normal"


def pick_tag_candidate(special_only=False):
    """Deterministic (no dice — the wheel theater is for entries): orphans first, then
    overbroad, then never-reviewed, then >90d stale; alphabetical within a class.
    Respects each tag's nextEligible snooze."""
    inv = _tag_inventory()
    if inv is None:
        return None
    st = _load_tag_state()
    classes = {"orphan": [], "overbroad": [], "new": [], "stale": []}
    for tag, gloss, n in inv:
        s = st.get(tag, {})
        if TODAY < parse_date(s.get("nextEligible"), datetime.date.min):
            continue
        cond = _tag_condition(n)
        cand = {"tag": tag, "gloss": gloss, "carriers": n, "cond": cond,
                "declines": int(s.get("declineCount", 0) or 0)}
        if cond != "normal":
            classes[cond].append(cand)
        elif special_only:
            continue
        elif s.get("lastReviewed") is None:
            classes["new"].append(cand)
        elif (TODAY - parse_date(s["lastReviewed"], TODAY)).days > TAG_THRESHOLD_DAYS:
            classes["stale"].append(cand)
    for cls in ("orphan", "overbroad", "new", "stale"):
        if classes[cls]:
            return classes[cls][0]
    return None


def render_tag_offer(c):
    note = {"orphan": "ORPHAN — zero memories carry it; retire unless it names work in flight",
            "overbroad": f"OVERBROAD — >= {TAG_OVERBROAD} carriers dilute recall; consider splitting "
                         "the domain and retagging, or keep if it is genuinely one topic",
            "normal": "routine vocabulary check"}[c["cond"]]
    return f"""<memory-review-offer mode="tag-round" name="{c['tag']}">
🎡 TAG ROULETTE — vocabulary review: `{c['tag']}`

  📖 gloss: {c['gloss']}
  🔗 carriers: {c['carriers']} memories
  ⚠  {note}
  🎯 Declines: {c['declines']} (snooze grows 7d each)

Surface this to the user as a BRIEF aside BEFORE answering their actual prompt.
Offer four choices:
  (K)eep   — vocabulary is right, bank it for {TAG_THRESHOLD_DAYS}d
  (G)loss  — re-write this tag's gloss line in _tags.md first, then run tag-keep
  (R)etire — remove from the vocabulary (refused while carriers > 0; retag them first)
  (L)ater  — not now

After their answer, call exactly one of:
  python3 {sys.argv[0]} tag-keep   {c['tag']}
  python3 {sys.argv[0]} tag-retire {c['tag']}
  python3 {sys.argv[0]} tag-later  {c['tag']}
Surface the one-line stdout verbatim, then proceed to the user's real request.
If the user ignores the offer entirely, treat as Later.
</memory-review-offer>"""


def cmd_tag_keep(tag):
    st = _load_tag_state()
    st[tag] = {"lastReviewed": TODAY.isoformat(), "declineCount": 0,
               "nextEligible": (TODAY + datetime.timedelta(days=TAG_THRESHOLD_DAYS)).isoformat()}
    _save_tag_state(st)
    print(f"🏷  Banked tag '{tag}' for {TAG_THRESHOLD_DAYS}d. {reward()}")


def cmd_tag_later(tag):
    st = _load_tag_state()
    s = st.get(tag, {})
    d = int(s.get("declineCount", 0) or 0) + 1
    s["declineCount"] = d
    s["nextEligible"] = (TODAY + datetime.timedelta(days=7 * d)).isoformat()
    st[tag] = s
    _save_tag_state(st)
    print(f"⏰ Tag '{tag}' snoozed {7 * d}d (decline #{d}; no auto-flip for vocabulary).")


def cmd_tag_retire(tag):
    """Remove a tag from _tags.md and scrub _tag_links.md lines referencing it.
    FAIL CLOSED: refuses with carriers, without the engine, or if validation breaks."""
    if _ms is None:
        print("tag-retire refused: taxonomy engine unavailable (cannot validate)", file=sys.stderr)
        sys.exit(2)
    inv = _tag_inventory()
    entry = next((c for c in (inv or []) if c[0] == tag), None)
    if inv is None or entry is None:
        print(f"tag-retire refused: '{tag}' not an active tag (or catalog unavailable)", file=sys.stderr)
        sys.exit(2)
    if entry[2] > 0:
        print(f"tag-retire refused: '{tag}' still has {entry[2]} carriers — retag them first "
              f"(grep 'tags:.*{tag}' over the store)", file=sys.stderr)
        sys.exit(2)
    tags_p, links_p = MEMDIR / "_tags.md", MEMDIR / "_tag_links.md"
    old_tags = tags_p.read_text()
    old_links = links_p.read_text() if links_p.exists() else None
    line_re = re.compile(r"^- " + re.escape(tag) + r"\s+[—-]\s")
    new_tags = "\n".join(ln for ln in old_tags.split("\n") if not line_re.match(ln))
    _ms.write_atomic(tags_p, new_tags)
    if old_links is not None:
        new_links = "\n".join(ln for ln in old_links.split("\n")
                              if f"`{tag}`" not in ln)
        _ms.write_atomic(links_p, new_links)
    errs = _ms.validate(MEMDIR)
    if errs:
        _ms.write_atomic(tags_p, old_tags)
        if old_links is not None:
            _ms.write_atomic(links_p, old_links)
        print("tag-retire rolled back — validation failed: " + "; ".join(errs), file=sys.stderr)
        sys.exit(2)
    _ms.rebuild(MEMDIR)
    st = _load_tag_state()
    st.pop(tag, None)
    _save_tag_state(st)
    print(f"🗑  Tag '{tag}' retired from the vocabulary (links scrubbed, catalog rebuilt).")


def cmd_tag_status():
    inv = _tag_inventory()
    if inv is None:
        print("tag inventory unavailable (engine or catalog missing)", file=sys.stderr)
        sys.exit(2)
    st = _load_tag_state()
    print(f"{'tag':36} {'carriers':>8} {'cond':>10} {'reviewed':>12} {'next':>12}")
    print("-" * 84)
    for tag, _, n in sorted(inv, key=lambda c: (c[2] != 0, -c[2], c[0])):
        s = st.get(tag, {})
        print(f"{tag:36} {n:>8} {_tag_condition(n):>10} "
              f"{s.get('lastReviewed', '-'):>12} {s.get('nextEligible', '-'):>12}")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "offer"
    arg = sys.argv[2] if len(sys.argv) > 2 else None
    dispatch = {
        "offer":   lambda: cmd_offer(),
        "play":    lambda: cmd_play(arg),
        "status":  lambda: cmd_status(),
        "keep":    lambda: cmd_keep(arg),
        "refresh": lambda: cmd_refresh(arg),
        "later":   lambda: cmd_later(arg),
        "toss":    lambda: cmd_toss(arg),
        "flip":    lambda: cmd_flip(arg),
        "tag-keep":   lambda: cmd_tag_keep(arg),
        "tag-later":  lambda: cmd_tag_later(arg),
        "tag-retire": lambda: cmd_tag_retire(arg),
        "tag-status": lambda: cmd_tag_status(),
    }
    fn = dispatch.get(cmd)
    if fn is None:
        print(f"unknown command: {cmd}", file=sys.stderr)
        sys.exit(2)
    fn()


if __name__ == "__main__":
    main()
