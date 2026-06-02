#!/usr/bin/env python3
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

Frontmatter contract (per memory file):
  lastReviewed:  ISO date of last "still true" confirmation.
  declineCount:  consecutive Laters since last keep/refresh.
  nextEligible:  ISO date before which no offer fires for this file.

Missing fields are tolerated: lastReviewed falls back to file mtime,
declineCount to 0, nextEligible to lastReviewed.
"""
import datetime
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
    top, meta = {}, {}
    in_meta = False
    for raw in m.group(1).splitlines():
        if not raw.strip():
            continue
        if raw[0] in (" ", "\t"):          # indented -> child of metadata:
            if in_meta and ":" in raw:
                k, v = raw.strip().split(":", 1)
                meta[k.strip()] = v.strip()
            continue
        if ":" not in raw:
            continue
        k, v = raw.split(":", 1)
        k, v = k.strip(), v.strip()
        if k == "metadata":
            in_meta = True
        else:
            in_meta = False
            top[k] = v
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
        "description": top.get("description", "(no description)").strip().strip('"').strip("'"),
    }


def offer_score(s):
    if s["overdue"] == 0:
        return 0.0
    rate = BASE_OFFER_RATE * (1 + s["overdue"] / 30) * (1 + 0.2 * s["declines"])
    return min(MAX_OFFER_RATE, rate)


def pick_candidate():
    candidates = []
    for p in memory_files():
        s = state(p)
        if s["overdue"] == 0:
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
    return f"""<memory-review-offer mode="round" name="{name}">
🎰 MEMORY ROULETTE — the wheel landed on: {name}

  📜 {desc}
  ⏱  Last reviewed: {s['days_since']} days ago (overdue by {s['overdue']})
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
    path, s = pick_candidate()
    if path is None or s is None:
        return
    forced = s["declines"] >= DECLINE_THRESHOLD
    if not forced and random.random() > offer_score(s):
        return
    print(render_offer(path, s, forced_flip=forced))


def cmd_play(name=None):
    if name:
        path = MEMDIR / f"{name}.md"
        if not path.exists():
            print(f"no such memory: {name}", file=sys.stderr)
            sys.exit(2)
        s = state(path)
    else:
        cands = [(p, state(p)) for p in memory_files()]
        cands.sort(key=lambda c: -c[1]["overdue"])
        if not cands or cands[0][1]["overdue"] == 0:
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
        rows.append((p.stem, s["days_since"], s["overdue"],
                     s["declines"], s["next_eligible"].isoformat(),
                     offer_score(s)))
    rows.sort(key=lambda r: (-r[2], -r[3]))
    print(f"{'name':38} {'age':>4} {'over':>5} {'decl':>5} "
          f"{'next':>12} {'p(offer)':>9}")
    print("-" * 80)
    for r in rows:
        print(f"{r[0]:38} {r[1]:>4} {r[2]:>5} {r[3]:>5} "
              f"{r[4]:>12} {r[5]:>9.3f}")


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
    }
    fn = dispatch.get(cmd)
    if fn is None:
        print(f"unknown command: {cmd}", file=sys.stderr)
        sys.exit(2)
    fn()


if __name__ == "__main__":
    main()
