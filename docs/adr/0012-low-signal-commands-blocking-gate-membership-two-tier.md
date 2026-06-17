# The LOW_SIGNAL_COMMANDS blocking-gate membership is a two-tier defensibility split, with the 12 weak-signal members discharged by a live-corpus check

**Status:** accepted

The write-guard's static degenerate-blocker tier denies a trigger set whose only behavioral evidence is a bare low-signal command. That set, `LOW_SIGNAL_COMMANDS`, has **21 members**, and shipping all 21 in the *blocking* gate was a deliberate, contested trade-off — not a uniform "all defensibly low-signal" set. The set splits into two tiers of materially different defensibility:

- **Tier A — 9 members** (`awk`, `cat`, `cd`, `find`, `grep`, `head`, `ls`, `sed`, `tail`) are also in `GENERIC_BASH` and carry **zero** read-path signal. Denying them bare routes nothing — unambiguously safe.
- **Tier B — 12 members** (`git`, `python`, `python3`, `bash`, `sh`, `cp`, `mv`, `rm`, `mkdir`, `echo`, `chmod`, `touch`) emit a real-but-**weak** read-path `command` signal. Denying a memory legitimately *about* one of those commands is a genuine false-denial risk that the design's own "when in doubt leave it OUT" bar argued against.

The reviewed alternative was to narrow the blocking gate to the 9 Tier-A members and defer the 12 to a corpus-aware tier. The decision to **keep all 21** was justified only by a forward corpus check: a live-store validation proved that **no** existing trigger-bearing memory is a bare-Tier-B-command-only trigger (the zero-co-fire memories have cmd-axis = 0; the lone outlier is path-axis). So the 12 weak-signal members false-deny nothing *today*. That live-corpus validation is what discharges the false-denial risk and makes the 21-member blocking set defensible.

## Considered Options

- **Block only the 9 Tier-A (`GENERIC_BASH`) members; defer the 12 Tier-B to a later corpus-aware tier.** Rejected only after the live-corpus check — it is the safer-by-default choice, but the live store showed the 12 false-deny nothing today.
- **Block all 21 in the static gate (chosen), discharged by the live-corpus check.** Maximizes noise reduction; the false-denial risk on the 12 is empirically zero against the current store.
- **Make the whole set corpus-aware (look up co-fires before denying).** Rejected for this tier: it is meant to be the static, corpus-free degenerate blocker; corpus awareness belongs in the projection tier (ADR-0015).

## Consequences

- The blocking set is wider (21) than a strict "zero-signal-only" gate (9) would be; the extra 12 are a deliberate noise-reduction trade-off, not an accident.
- The false-denial safety of the 12 Tier-B members is contingent on the live corpus — if a future memory is legitimately a bare-Tier-B-command-only trigger, this decision must be revisited (re-run the live-corpus check).
- Adding any narrowing arg or non-broad path rescues a set; the gate denies only the bare degenerate case.
