#!/usr/bin/env bash
# End-to-end hook fixture for the extended write hooks (plan 01-04).
# Tests the full detect/deny/allow/fail-open matrix including widened detection (D-14),
# composite injection (D-08), --target enforcement (D-09, D-15), and fail-open posture
# (D-18).  Runs hooks against a fixture store (MEMORY_SURFACE_DIR) — never touches the
# live store.
#
# Run: tests/memory_surface/test_write_hooks.sh
# RED state: dark-memory deny (D-14+D-15) and widened injection (D-14) cases MUST FAIL
# against the current hooks, which only watch the box store.  All other cases should pass.
set -u

LAB=$(cd "$(dirname "$0")/../.." && pwd)
CTX="$LAB/hooks/memory-write-context.sh"
GUARD="$LAB/hooks/memory-write-guard.sh"

command -v jq >/dev/null 2>&1 || { echo "jq required"; exit 2; }

# ── Fixture store setup ──────────────────────────────────────────────────────
FIX=$(mktemp -d)
trap 'rm -rf "$FIX" "$ISOCTX" "$ISOGUARD"' EXIT
ISOCTX=$(mktemp -d)
ISOGUARD=$(mktemp -d)

# Seed _tags.md with one known tag that has placement=box in the grammar
cat > "$FIX/_tags.md" << 'TAGS_EOF'
# tags
## domain
- claude-harness — this box's Claude Code hooks, fingerprint, statusline, memory
- git — git version control workflow
## tool
## Denylist
## Policy overrides
TAGS_EOF

# Seed _grammar.md with box-placement tags — the placement gate reads this
cat > "$FIX/_grammar.md" << 'GRAMMAR_EOF'
# Unified Trigger Grammar — fixture store

Version: v0 (test fixture)
Status: test

---

## domain

### claude-harness
gloss: this box's Claude Code hooks, fingerprint, statusline, memory
placement: box
commands: [claude]
paths: [~/.claude/**]
args: []
synonyms: [claude-code]
related: []

### git
gloss: git version control workflow
placement: either
commands: [git]
paths: []
args: []
synonyms: []
related: []
GRAMMAR_EOF

printf '# tag links\n## Synonyms\n## Distinctions\n## Path Tags\n' > "$FIX/_tag_links.md"

# Seed one existing memory for dedup context (catalog needed by engine)
cat > "$FIX/existing-lesson.md" << 'MEM_EOF'
---
name: existing-lesson
description: "existing memory about claude hooks behavior"
metadata:
  node_type: memory
  type: feedback
  tags: [claude-harness]
  triggers:
    commands: [claude]
    paths: [~/.claude/hooks/]
    args: []
    synonyms: []
---
Existing memory body.
MEM_EOF

# Build catalog so dedup layer works
python3 "$LAB/lib/memory_surface.py" rebuild --memory-dir "$FIX" >/dev/null 2>&1 || true

export MEMORY_SURFACE_DIR="$FIX"

# ── Helper functions ─────────────────────────────────────────────────────────
mkwrite() {
    # mkwrite <file_path> <content> [<cwd>]
    local fp="$1" c="$2" cwd="${3:-/tmp}"
    jq -cn --arg fp "$fp" --arg c "$c" --arg cwd "$cwd" \
        '{tool_name:"Write",cwd:$cwd,tool_input:{file_path:$fp,content:$c}}'
}
mkedit() {
    # mkedit <file_path> <new_string>
    local fp="$1" ns="$2"
    jq -cn --arg fp "$fp" --arg ns "$ns" \
        '{tool_name:"Edit",cwd:"/tmp",tool_input:{file_path:$fp,new_string:$ns}}'
}

pass=0; fail=0
rc_is() {
    local label="$1" want="$2" got="$3"
    if [ "$want" = "$got" ]; then
        echo "  PASS $label"
        pass=$((pass + 1))
    else
        echo "  FAIL $label (want rc=$want got rc=$got)"
        fail=$((fail + 1))
    fi
}
assert_contains() {
    local label="$1" needle="$2" haystack="$3"
    if printf '%s' "$haystack" | grep -qF "$needle"; then
        echo "  PASS $label"
        pass=$((pass + 1))
    else
        echo "  FAIL $label (expected to contain: $needle)"
        echo "       actual: $(printf '%s' "$haystack" | head -c 200)"
        fail=$((fail + 1))
    fi
}
assert_empty() {
    local label="$1" val="$2"
    if [ -z "$val" ]; then
        echo "  PASS $label"
        pass=$((pass + 1))
    else
        echo "  FAIL $label (expected empty, got: $(printf '%s' "$val" | head -c 100))"
        fail=$((fail + 1))
    fi
}
assert_nonempty() {
    local label="$1" val="$2"
    if [ -n "$val" ]; then
        echo "  PASS $label"
        pass=$((pass + 1))
    else
        echo "  FAIL $label (expected non-empty)"
        fail=$((fail + 1))
    fi
}

# ── Memory content fixtures ───────────────────────────────────────────────────

# Valid box-store memory WITH triggers (should be allowed by guard)
GOOD_BOX='---
name: test-memory
description: "a test memory about claude hooks"
metadata:
  node_type: memory
  type: feedback
  tags: [claude-harness]
  triggers:
    commands: [claude]
    paths: [~/.claude/hooks/]
    args: []
    synonyms: []
---
Body text.'

# Box-store memory WITHOUT triggers (should be denied by guard — D-09)
NO_TRIGGERS_BOX='---
name: test-memory
description: "a test memory about claude hooks"
metadata:
  node_type: memory
  type: feedback
  tags: [claude-harness]
---
Body text.'

# Memory with only box-placement tags (should be denied when written to a repo memory/ path — D-15)
BOX_TAGS_CONTENT='---
name: dark-memory-test
description: "a memory about claude harness hooks that belongs in the box store"
metadata:
  node_type: memory
  type: feedback
  tags: [claude-harness]
  triggers:
    commands: [claude]
    paths: [~/.claude/hooks/]
    args: []
    synonyms: []
---
This should land in the box store, not a repo memory/ dir.'

# Memory with non-box-placement tags (ambiguous — should be allowed when written to a repo memory/ path)
AMBIGUOUS_CONTENT='---
name: git-lesson
description: "a lesson about git workflow"
metadata:
  node_type: memory
  type: feedback
  tags: [git]
  triggers:
    commands: [git]
    paths: []
    args: [push, pull]
    synonyms: []
---
Some git lesson.'

# ── GUARD tests ───────────────────────────────────────────────────────────────
echo "── GUARD: box-store deny (D-09) ──"
# D-09: full Write of box memory content WITHOUT triggers → exit 2, stderr contains "triggers:"
stderr_out=$(mkwrite "$FIX/new-memory.md" "$NO_TRIGGERS_BOX" | "$GUARD" 2>&1 >/dev/null); got_rc=$?
rc_is "GUARD deny no-triggers -> rc=2 (D-09)" 2 "$got_rc"
assert_contains "GUARD deny stderr contains 'triggers:' (D-09)" "triggers:" "$stderr_out"

echo "── GUARD: box-store allow (D-09) ──"
# Same content WITH valid triggers → exit 0, no output.
# Target is a NEW file sharing a tag with the existing fixture memory but with a
# DISTINCT description — the dedup backstop must NOT fire (WR-02 contract: single-tag
# overlap plus stopword-level description overlap is not a near-certain duplicate).
out=$(mkwrite "$FIX/new-distinct-memory.md" "$GOOD_BOX" | "$GUARD" 2>&1); got_rc=$?
rc_is "GUARD allow with triggers, new distinct file -> rc=0 (D-09, WR-02)" 0 "$got_rc"
assert_empty "GUARD allow: no output on valid write (D-09)" "$out"
# Consolidation into the existing file is also allowed (backstop is new-file-only)
out=$(mkwrite "$FIX/existing-lesson.md" "$GOOD_BOX" | "$GUARD" 2>&1); got_rc=$?
rc_is "GUARD allow consolidation into existing file -> rc=0 (D-11)" 0 "$got_rc"

echo "── GUARD: dark-memory deny (D-14+D-15) ──"
# D-14+D-15: Write to <somerepo>/memory/lesson.md with box-placement tags → exit 2,
# stderr contains the correct store path (MEMORY_SURFACE_DIR fixture in test; live box store in prod).
# The engine calls resolve_memdir() which honors MEMORY_SURFACE_DIR, so in test context the
# deny reason names the fixture store path.
# NOTE: This case FAILS (RED) against the current hooks because they only check the box store.
REPO_MEM_TARGET="$LAB/memory/dark-memory-probe.md"
stderr_out=$(mkwrite "$REPO_MEM_TARGET" "$BOX_TAGS_CONTENT" | "$GUARD" 2>&1 >/dev/null); got_rc=$?
rc_is "GUARD dark-memory box-tags deny -> rc=2 (D-14+D-15)" 2 "$got_rc"
# The deny reason should name the store path (fixture dir here; live box store path in production)
# and explain the placement error — check for "box-placement" which appears in all deny reasons
assert_contains "GUARD deny stderr contains placement explanation (D-15)" "box-placement" "$stderr_out"

echo "── GUARD: ambiguous placement allow (D-15) ──"
# D-15: same repo memory/ target, but tags unknown to grammar or non-box placement → exit 0
OTHER_REPO_MEM="$LAB/memory/ambiguous-memory.md"
out=$(mkwrite "$OTHER_REPO_MEM" "$AMBIGUOUS_CONTENT" | "$GUARD" 2>&1); got_rc=$?
rc_is "GUARD ambiguous tags -> rc=0 (D-15)" 0 "$got_rc"

echo "── GUARD: infra exemptions (D-14) ──"
# D-14: writes targeting _grammar.md / _tags.md / MEMORY.md are never gated as memories
out=$(mkwrite "$FIX/_grammar.md" "# grammar update" | "$GUARD" 2>&1); got_rc=$?
rc_is "GUARD _grammar.md exempt -> rc=0 (D-14)" 0 "$got_rc"
out=$(mkwrite "$FIX/_tags.md" "# tags update" | "$GUARD" 2>&1); got_rc=$?
rc_is "GUARD _tags.md exempt -> rc=0 (D-14)" 0 "$got_rc"
out=$(mkwrite "$FIX/MEMORY.md" "# Memory index" | "$GUARD" 2>&1); got_rc=$?
rc_is "GUARD MEMORY.md exempt -> rc=0 (D-14)" 0 "$got_rc"

echo "── GUARD: proposed taxonomy/grammar content validated (WR-04) ──"
# A full Write whose PROPOSED content corrupts the taxonomy is denied BEFORE it lands
# (the old gate validated the on-disk file, so corrupting Writes passed the only blocker).
BROKEN_PROPOSED_TAGS='# tags
## domain
- config — broken on purpose
## Denylist
- config — too generic
## Policy overrides'
stderr_out=$(mkwrite "$FIX/_tags.md" "$BROKEN_PROPOSED_TAGS" | "$GUARD" 2>&1 >/dev/null); got_rc=$?
rc_is "GUARD corrupting _tags.md Write denied -> rc=2 (WR-04)" 2 "$got_rc"
assert_contains "GUARD corrupting Write stderr names the error (WR-04)" "denylisted" "$stderr_out"
# A VALID full Write still passes (re-write the current content)
GOOD_PROPOSED_TAGS=$(cat "$FIX/_tags.md")
out=$(mkwrite "$FIX/_tags.md" "$GOOD_PROPOSED_TAGS" | "$GUARD" 2>&1); got_rc=$?
rc_is "GUARD valid _tags.md Write allowed -> rc=0 (WR-04)" 0 "$got_rc"
# Same for grammar: a proposed entry with empty gloss + bogus placement + no evidence -> deny
BROKEN_PROPOSED_GRAMMAR='## domain

### broken-tag
gloss:
placement: nowhere
commands: []
paths: []
args: []
synonyms: []
related: []'
stderr_out=$(mkwrite "$FIX/_grammar.md" "$BROKEN_PROPOSED_GRAMMAR" | "$GUARD" 2>&1 >/dev/null); got_rc=$?
rc_is "GUARD corrupting _grammar.md Write denied -> rc=2 (WR-04)" 2 "$got_rc"

echo "── GUARD: taxonomy gate is path-scoped (CR-02) ──"
# A file that merely SHARES a taxonomy basename outside the store is NOT gated —
# even when the box-store taxonomy is currently invalid (the exact state where the
# unscoped gate used to false-deny unrelated files).
cp "$FIX/_tags.md" "$FIX/_tags.md.bak"
cat > "$FIX/_tags.md" << 'BROKEN_TAGS_EOF'
# tags
## domain
- config — broken on purpose
## Denylist
- config — too generic
## Policy overrides
BROKEN_TAGS_EOF
OUTSIDE=$(mktemp -d)
out=$(mkwrite "$OUTSIDE/_tags.md" "# unrelated tags file" | "$GUARD" 2>&1); got_rc=$?
rc_is "GUARD out-of-store _tags.md not gated -> rc=0 (CR-02)" 0 "$got_rc"
assert_empty "GUARD out-of-store _tags.md: silent (CR-02)" "$out"
out=$(mkwrite "$OUTSIDE/_grammar.md" "# unrelated grammar file" | "$GUARD" 2>&1); got_rc=$?
rc_is "GUARD out-of-store _grammar.md not gated -> rc=0 (CR-02)" 0 "$got_rc"
# The IN-store taxonomy edit IS still gated while the on-disk taxonomy is broken
stderr_out=$(mkedit "$FIX/_tags.md" "tweak" | "$GUARD" 2>&1 >/dev/null); got_rc=$?
rc_is "GUARD in-store _tags.md edit still gated -> rc=2 (CR-02)" 2 "$got_rc"
mv "$FIX/_tags.md.bak" "$FIX/_tags.md"
rm -rf "$OUTSIDE"

echo "── GUARD: Edit fail-open ──"
# Edit event (no .content) on a box memory → exit 0
out=$(mkedit "$FIX/new-memory.md" "updated text" | "$GUARD" 2>&1); got_rc=$?
rc_is "GUARD Edit fail-open -> rc=0" 0 "$got_rc"

echo "── CONTEXT: box-store inject (D-08) ──"
# D-08: Write of box-store memory → exit 0, stdout is JSON with additionalContext containing "triggers:"
# NOTE: Current hook injects _tags.md vocabulary, not the engine composite.
# The GREEN state requires "triggers:" to be present in additionalContext.
out=$(mkwrite "$FIX/new-memory.md" "$GOOD_BOX" | "$CTX" 2>/dev/null); got_rc=$?
rc_is "CONTEXT box-store inject -> rc=0 (D-08)" 0 "$got_rc"
# The composite from the engine should contain "triggers:" (schema hint)
ac=$(printf '%s' "$out" | jq -r '.hookSpecificOutput.additionalContext // empty' 2>/dev/null || true)
assert_nonempty "CONTEXT box-store: additionalContext non-empty (D-08)" "$ac"
assert_contains "CONTEXT box-store: additionalContext contains 'triggers:' (D-08)" "triggers:" "$ac"

echo "── CONTEXT: widened inject — repo memory/ (D-14) ──"
# D-14: Write to a repo memory/ path (non-infra) → exit 0 with additionalContext
# (guidance reaches mis-placed writes too).
# NOTE: This case FAILS (RED) against the current hooks since they only watch the box store.
out=$(mkwrite "$LAB/memory/some-lesson.md" "$BOX_TAGS_CONTENT" | "$CTX" 2>/dev/null); got_rc=$?
rc_is "CONTEXT widened inject -> rc=0 (D-14)" 0 "$got_rc"
ac=$(printf '%s' "$out" | jq -r '.hookSpecificOutput.additionalContext // empty' 2>/dev/null || true)
assert_nonempty "CONTEXT widened: additionalContext non-empty for repo memory/ write (D-14)" "$ac"

echo "── CONTEXT: non-memory silence ──"
# Write to a random .md outside any store/memory dir → exit 0, empty stdout
out=$(mkwrite "/tmp/random-doc.md" "some content" | "$CTX" 2>/dev/null); got_rc=$?
rc_is "CONTEXT non-memory -> rc=0" 0 "$got_rc"
assert_empty "CONTEXT non-memory: silent (empty stdout)" "$out"

echo "── CONTEXT: _grammar.md infra-exempt (D-14) ──"
# A Write event targeting $STORE/_grammar.md should produce NO additionalContext injection
out=$(mkwrite "$FIX/_grammar.md" "# grammar content" | "$CTX" 2>/dev/null); got_rc=$?
rc_is "CONTEXT _grammar.md infra-exempt -> rc=0 (D-14)" 0 "$got_rc"
assert_empty "CONTEXT _grammar.md: no injection (infra exempt)" "$out"

echo "── Fail-open matrix (D-18) ──"

# D-18: .surface-disabled present → exit 0 silent (both hooks)
touch "$FIX/.surface-disabled"
out_guard=$(mkwrite "$FIX/mem.md" "$NO_TRIGGERS_BOX" | "$GUARD" 2>&1); rc_guard=$?
out_ctx=$(mkwrite "$FIX/mem.md" "$GOOD_BOX" | "$CTX" 2>/dev/null); rc_ctx=$?
rc_is "GUARD kill-switch -> rc=0 (D-18)" 0 "$rc_guard"
rc_is "CONTEXT kill-switch -> rc=0 (D-18)" 0 "$rc_ctx"
rm -f "$FIX/.surface-disabled"

# D-18: engine unreachable → fail open on both hooks (copy hook to isolated dir without lib/)
cp "$GUARD" "$ISOGUARD/g.sh"; chmod +x "$ISOGUARD/g.sh"
out=$(mkwrite "$FIX/mem.md" "$NO_TRIGGERS_BOX" | "$ISOGUARD/g.sh" 2>&1); got_rc=$?
rc_is "GUARD engine-unreadable -> rc=0 (D-18)" 0 "$got_rc"

cp "$CTX" "$ISOCTX/c.sh"; chmod +x "$ISOCTX/c.sh"
out=$(mkwrite "$FIX/mem.md" "$GOOD_BOX" | "$ISOCTX/c.sh" 2>/dev/null); got_rc=$?
rc_is "CONTEXT engine-unreadable -> rc=0 (D-18)" 0 "$got_rc"

# D-18: malformed JSON on stdin → both hooks exit 0
printf 'not-json' | "$GUARD" >/dev/null 2>&1; got_rc=$?
rc_is "GUARD malformed JSON -> rc=0 (D-18)" 0 "$got_rc"
printf 'not-json' | "$CTX" >/dev/null 2>&1; got_rc=$?
rc_is "CONTEXT malformed JSON -> rc=0 (D-18)" 0 "$got_rc"

# ── Summary ──────────────────────────────────────────────────────────────────
echo
echo "RESULT: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
