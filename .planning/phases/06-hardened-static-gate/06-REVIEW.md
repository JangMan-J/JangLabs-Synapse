---
phase: 06-hardened-static-gate
reviewed: 2026-06-13T00:00:00Z
depth: standard
files_reviewed: 2
files_reviewed_list:
  - lib/memory_surface.py
  - tests/memory_surface/test_write_triggers.py
findings:
  critical: 0
  warning: 3
  info: 2
  total: 5
status: clean
resolution:
  WR-01: resolved-by-documentation + corpus-deferral (two-tier membership comment above LOW_SIGNAL_COMMANDS; Tier-B validated in Phase 7 CAL-03; no member removed)
  WR-02: fixed (command tokens normalized via strip().lower() to match read-path _norm before the membership test)
  WR-03: fixed (added no-over-block PASS guards git+wpctl and bare wpctl; plus WR-02 deny fixtures Git and " git ")
  IN-01: skipped (non-actionable polish — D-05 intent already covered across two tests)
  IN-02: skipped (non-actionable polish — combined deny message wording acceptable)
  fix_commits:
    - 61a9969 fix(06-01) WR-02/WR-03
    - cfbb9a5 docs(06-01) WR-01
---

# Phase 6: Code Review Report

**Reviewed:** 2026-06-13
**Depth:** standard
**Files Reviewed:** 2
**Status:** clean (all warnings resolved — see frontmatter `resolution`)

## Summary

Scope: the new `LOW_SIGNAL_COMMANDS` set and the broadened deny predicate in
`_check_triggers`'s specificity gate (`lib/memory_surface.py`), plus the 11-fixture
`LowSignalCommandGate` test class (`tests/memory_surface/test_write_triggers.py`).
Commits `ecfc57d` (RED fixtures) and `1910be1` (GREEN implementation).

The core change is correct and minimal. I verified empirically (not by reading the
SUMMARY's claims):

- **Predicate correctness (focus #2): CONFIRMED.** `all(c in (GENERIC_VERBS |
  LOW_SIGNAL_COMMANDS) for c in cmds)` denies only when there are commands, no args, no
  non-broad paths, AND every command is generic-or-low-signal. `{commands:[git,wpctl]}`
  → rc 0 (passes, because `wpctl ∉` either set so `all()` is False). `{commands:[wpctl]}`
  → rc 0. `{commands:[git]}` → rc 2. `{commands:[git],args:[commit]}` → rc 0.
  `{commands:[git],paths:["~/.config/foo/**"]}` → rc 0. An arg or a specific path always
  rescues.
- **Additivity / disjointness (focus #3): CONFIRMED.** `LOW_SIGNAL_COMMANDS.isdisjoint(
  GENERIC_VERBS)` is True; intersection is empty. The generic-verb-only and broad-glob-only
  arms are byte-for-byte unchanged except the shared message string. The `:1684`
  arg-strength use of `GENERIC_VERBS` is untouched. Full file: 45 passed.
- **Message quality (focus #4): ADEQUATE.** The message names the offending command(s)
  (`sorted(cmds)`), retains the literal "generic" (keeps the regression assertion green),
  and gives actionable guidance ("add a distinguishing arg … or a specific path").

The findings below are about the **membership false-denial surface (focus #1)** — the real
risk for a blocking gate — plus a case-normalization bypass and two test-coverage gaps. No
BLOCKER: every denial the gate now produces is defensible against the read-path's own
signal model (see WR-01), and no PASS case regressed. But the membership rationale is
weaker than the SUMMARY claims for ~12 of the 21 members, and the gate is trivially
bypassable by casing.

## Warnings

### WR-01: `LOW_SIGNAL_COMMANDS` membership splits into two tiers; the 12 "weak-signal" members carry a genuine (if small) false-denial surface

**File:** `lib/memory_surface.py:1568-1572`
**Issue:** The 21 members are NOT uniformly defensible as "low routing signal," and the
distinction matters for a blocking gate. Cross-referencing the read-path matcher splits
them cleanly:

- **9 members are also in `GENERIC_BASH`** (`awk, cat, cd, find, grep, head, ls, sed,
  tail`) — line 1558. The read path (`tokenize`/`_check_triggers` consumers, lines 498
  and 1675) strips these as *no-signal* before any routing. A bare trigger on one of these
  would route **nothing** anyway, so denying it at write time is fully consistent and
  unambiguously correct. These are the safe core.
- **12 members are NOT in `GENERIC_BASH`** (`git, python, python3, bash, sh, cp, mv, rm,
  mkdir, echo, chmod, touch`). For these the read path emits `add(base, "command", "weak")`
  (line 1678) — a real, if weak, routing signal. A memory legitimately *about one of these
  commands itself* (e.g. a memory about `git` submodule mechanics with no single narrowing
  subcommand; about `python` venv/invocation conventions on this box; about `chmod`/exec-bit
  semantics; about `rm` safety habits) would, before Phase 6, route on the bare command —
  and is now **denied at write time**. That is the precise false-denial the D-01
  "when in doubt leave it OUT" bar is meant to prevent.

Concretely: the test file's own `FIXTURE_GRAMMAR_MD` declares the `git` tool-tag domain
with `commands: [git]` and nothing else (lines 80-87). The grammar models bare `git` as a
routable domain, yet a memory whose triggers mirror that declared domain is now denied.
The most plausible real-world false-denials are **`git`** (the motivating case is genuine
noise, but "a memory about git itself, narrowed only by being git-tagged" is a real
counter-case) and **`python`/`python3`** (box-specific Python invocation memories are
common in this very project).

**Why it matters:** This is a blocking gate (rc 2). A wrong DENY blocks a legitimate memory
write. The deny is *recoverable* (the author adds an arg/path per T-06-02), so this is not
a BLOCKER — but the SUMMARY's claim that all 21 are equally "defensibly low-signal" is not
supported by the read-path evidence, and the design's stated bar was "when in doubt, leave
it OUT."

**Fix:** Two acceptable resolutions; pick one and record the rationale:
1. (Preferred, lowest risk) Document the two tiers in the comment so the membership
   rationale survives, and accept the 12 weak-signal members as a deliberate
   stop-the-noise tradeoff — but only after confirming against the live corpus that no
   existing memory is a bare-command-only trigger on one of the 12 (this is exactly what
   CAL-03 will prove in Phase 7; cross-reference it here):
   ```python
   # Two tiers: {awk,cat,cd,find,grep,head,ls,sed,tail} are ALSO in GENERIC_BASH and
   # carry zero read-path signal (denying a bare one routes nothing). The rest
   # ({git,python,...}) carry a WEAK read-path "command" signal; denying them bare is a
   # deliberate noise-reduction tradeoff (CAL-03 confirms no existing memory trips it).
   ```
2. Narrow the seed to the 9 `GENERIC_BASH`-overlapping members for v1.1 and defer the
   12 weak-signal ones to the corpus-aware tier (Phase 8 / ENF), where a *measured*
   collision count (not a static blocklist) justifies denying a bare `git`. This is the
   most conservative reading of "when in doubt, leave it OUT" and aligns with the design's
   own two-tier "block the degenerate, guide the weak" posture.

### WR-02: Deny gate is case- and whitespace-sensitive; `Git`/` git` bypass it while still over-firing at the read path

**File:** `lib/memory_surface.py:1364`
**Issue:** The predicate tests raw membership: `all(c in (GENERIC_VERBS |
LOW_SIGNAL_COMMANDS) for c in cmds)`. Command tokens are not normalized. Verified:
`{commands:[git]}` → rc 2 (denied), but `{commands:[Git]}` → rc 0 and `{commands:[" git"]}`
→ rc 0 (both pass). Yet the **read path** tokenizes commands via
`re.findall(r"[a-z0-9][a-z0-9-]*", …lower())` and lowercases (lines 1690, 1713-1724), so a
trigger stored as `Git` is normalized to `git` at match time and **over-fires exactly the
same noise the gate exists to stop**. The hardening guarantee is therefore trivially
(even accidentally — a capitalized command name) circumvented.

**Why it matters:** A blocking gate whose contract is "bare low-signal command is denied"
silently fails to deny `Git`/`GIT`/` git`, defeating its purpose for non-lowercase input
while the read-path still treats those as the same over-firing token. Not a BLOCKER (it is
an evasion, not a false-denial, and lowercase is the overwhelmingly common authoring form),
but it weakens the guarantee the phase claims to deliver.

**Fix:** Normalize the command tokens the same way the read path does before the membership
test, so the gate's notion of a command matches the matcher's:
```python
norm_cmds = {c.strip().lower() for c in cmds}
all_low_signal = all(c in (GENERIC_VERBS | LOW_SIGNAL_COMMANDS) for c in norm_cmds)
```
(Keep the original `cmds` for the message so the author sees what they actually wrote.)

### WR-03: New test class omits the two most important regression guards for a blocking gate — the no-over-block PASS cases

**File:** `tests/memory_surface/test_write_triggers.py:705-816` (`LowSignalCommandGate`)
**Issue:** The class pins the deny cases and the two rescue cases (git+arg, git+path) well,
but it does NOT pin the two behaviors that protect against the gate becoming a
false-denial machine in the future (focus #2 and #5):

1. **No mixed low-signal + real-command PASS test.** Nothing asserts
   `{commands:[git, wpctl]}` → rc 0. This is the exact property that breaks if someone ever
   changes `all()` to `any()` or merges the sets — the single most dangerous regression for
   a blocking gate, and it is unguarded.
2. **No "real domain command alone still passes" guard.** Nothing in the new class asserts
   `{commands:[wpctl]}` → rc 0 (a real, non-low-signal command is not over-blocked). Other
   classes use `wpctl` fixtures, but `LowSignalCommandGate` — the class whose job is to pin
   *this* contract — does not assert the no-over-block direction. T-06-01 in the plan's
   threat model explicitly calls out "a too-broad predicate falsely denies a legitimate
   single-command memory"; that threat has no fixture.

**Why it matters:** QC-02 / contract-test discipline says fixtures pin the contract in
*both* directions. The deny direction is well covered; the "must NOT deny" direction — the
false-denial threat the whole membership-bar debate is about — is under-pinned.

**Fix:** Add two methods to `LowSignalCommandGate`, driving `_check_triggers` directly
(matching the WR-01/WR-03 vocabulary-shape pattern already in the file):
```python
def test_mixed_low_signal_plus_real_command_passes(self):
    """A real domain command alongside a low-signal one rescues the set (no over-block)."""
    rc, msg = ms._check_triggers({"commands": ["git", "wpctl"], "paths": [],
                                  "args": [], "synonyms": []})
    self.assertEqual(rc, 0, f"git+wpctl must pass — wpctl is real signal; msg: {msg!r}")

def test_real_command_alone_passes(self):
    """A non-low-signal command alone must NOT be denied (false-denial guard, T-06-01)."""
    rc, msg = ms._check_triggers({"commands": ["wpctl"], "paths": [],
                                  "args": [], "synonyms": []})
    self.assertEqual(rc, 0, f"bare 'wpctl' must pass; msg: {msg!r}")
```

## Info

### IN-01: Disjoint-sets property is asserted, but no test pins that the predicate UNIONS them (D-05 intent only half-covered)

**File:** `tests/memory_surface/test_write_triggers.py:712-727`
**Issue:** `test_low_signal_commands_disjoint_from_generic_verbs` pins that the two sets are
distinct (the "stay separate" half of D-05). But D-05 has two halves: the sets stay
distinct AND the predicate unions them so generic-verb denial still works alongside
low-signal denial. The union half is implicitly covered by `test_generic_verb_only_still_
denied`, so this is not a gap in behavior — just an observation that the D-05 *intent*
(two sets, unioned only in the predicate) is verified across two tests rather than named in
one. No action required; noting for traceability.
**Fix:** Optional — a one-line comment in the disjoint test pointing to the generic-verb
regression test as the "union still works" companion.

### IN-02: Deny message says "generic or low-signal commands" but lists members without indicating which bucket each falls in

**File:** `lib/memory_surface.py:1366-1372`
**Issue:** For a mixed set like `{commands:[restart, git]}` the message reads "contains only
generic or low-signal commands (git, restart)" — the author cannot tell that `restart` is
the generic verb and `git` the low-signal command. Minor; the actionable guidance ("add a
distinguishing arg or path") is the same regardless, so this does not impair recovery.
**Fix:** Optional polish — leave as-is; the combined wording is acceptable and the fix
(per-token labeling) would add complexity for negligible author benefit.

---

_Reviewed: 2026-06-13_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
