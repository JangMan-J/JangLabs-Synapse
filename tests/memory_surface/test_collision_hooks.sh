#!/usr/bin/env bash
# End-to-end hook fixture for the corpus-aware collision enforcement (ENF, ADR-0017).
# Proves the hook->engine plumbing carries the new deny (rc 2 + reason) and the collision
# composite. Isolated fixture store (own MEMORY_SURFACE_DIR), low floor, a NON-low-signal
# command so the static gate passes and the projection tier is reached. Never touches the
# live store.
#
# Run: tests/memory_surface/test_collision_hooks.sh
set -u

LAB=$(cd "$(dirname "$0")/../.." && pwd)
CTX="$LAB/hooks/memory-write-context.sh"
GUARD="$LAB/hooks/memory-write-guard.sh"
ENGINE="$LAB/lib/memory_surface.py"
command -v jq >/dev/null 2>&1 || { echo "jq required"; exit 2; }

FIX=$(mktemp -d)
trap 'rm -rf "$FIX"' EXIT

cat > "$FIX/_tags.md" << 'TAGS_EOF'
# tags
## tool
- container — container tooling (docker/compose)
## Denylist
## Policy overrides
TAGS_EOF

cat > "$FIX/_grammar.md" << 'GRAMMAR_EOF'
# Unified Trigger Grammar — fixture store
Version: v0 (test fixture)
Status: test

---

## tool

### container
gloss: container tooling docker and compose
placement: either
commands: [docker]
paths: []
args: [compose]
synonyms: []
related: []
GRAMMAR_EOF

printf '# tag links\n## Synonyms\n## Distinctions\n## Path Tags\n' > "$FIX/_tag_links.md"
printf '{"collisionGuideFloor": 1}\n' > "$FIX/_memory_surface_config.json"

# Two memories tagged container -> a bare {commands:[docker]} co-fires with both (2 > floor 1).
for n in a b; do
  cat > "$FIX/mem-cnt-$n.md" << MEM_EOF
---
name: mem-cnt-$n
description: "container memory $n"
metadata:
  node_type: memory
  type: feedback
  tags: [container]
  triggers:
    commands: [docker]
    paths: []
    args: []
---
body $n
MEM_EOF
done

python3 "$ENGINE" rebuild --memory-dir "$FIX" >/dev/null 2>&1 || true
export MEMORY_SURFACE_DIR="$FIX"

mkwrite() {
    jq -cn --arg fp "$1" --arg c "$2" \
        '{tool_name:"Write",cwd:"/tmp",tool_input:{file_path:$fp,content:$c}}'
}
content() {
    # content <args-list-or-empty>  -> proposed memory with commands:[docker] + given args
    printf -- '---\nname: mem-proposed\ndescription: "x"\nmetadata:\n  node_type: memory\n  type: feedback\n  tags: [container]\n  triggers:\n    commands: [docker]\n    args: [%s]\n---\nbody\n' "$1"
}

pass=0; fail=0
ok()   { echo "  PASS $1"; pass=$((pass+1)); }
no()   { echo "  FAIL $1"; fail=$((fail+1)); }
rc_is() { [ "$2" = "$3" ] && ok "$1" || { no "$1 (want rc=$2 got rc=$3)"; }; }
has()   { printf '%s' "$3" | grep -qF "$2" && ok "$1" || no "$1 (missing: $2)"; }
empty() { [ -z "$2" ] && ok "$1" || no "$1 (expected empty: $(printf '%s' "$2"|head -c80))"; }

FP="$FIX/mem-proposed.md"

# 1. GUARD denies the degenerate write (commands:[docker], no args) end-to-end.
mkwrite "$FP" "$(content '')" | "$GUARD" 2>"$FIX/e" 1>/dev/null; rc=$?
err=$(cat "$FIX/e")
rc_is "GUARD denies degenerate write (rc 2)" 2 "$rc"
has   "GUARD deny names the over-fire" "over-fire" "$err"

# 2. GUARD allows a write with a contributing routable arg (compose) -> guide, not block.
mkwrite "$FP" "$(content 'compose')" | "$GUARD" 2>"$FIX/e" 1>/dev/null; rc=$?
err=$(cat "$FIX/e")
rc_is "GUARD allows contributing-arg write (rc 0)" 0 "$rc"
empty "GUARD allow path quiet on stderr (QC-04)" "$err"

# 3. CONTEXT injects collision guidance for the broad write.
out=$(mkwrite "$FP" "$(content '')" | "$CTX" 2>/dev/null)
ac=$(printf '%s' "$out" | jq -r '.hookSpecificOutput.additionalContext // empty' 2>/dev/null)
has "CONTEXT injects collision pre-warning (degenerate)" "WILL BE DENIED" "$ac"
has "CONTEXT names a co-firing memory" "mem-cnt-a" "$ac"

echo
echo "collision-hooks: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
