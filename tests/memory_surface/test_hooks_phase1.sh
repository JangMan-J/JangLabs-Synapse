#!/usr/bin/env bash
# Regression suite for the 3 Phase-1 memory hooks. Runs them against a fixture store
# (MEMORY_SURFACE_DIR) — never touches the live store. Covers the contract AND every
# adversarial-review fix (../ false-deny, engine-unreadable fail-open, trailing slash,
# unset HOME, symlinked taxonomy, top-level tags). Run: tests/memory_surface/test_hooks_phase1.sh
set -u
LAB=$(cd "$(dirname "$0")/../.." && pwd)
CTX="$LAB/hooks/memory-write-context.sh"
GUARD="$LAB/hooks/memory-write-guard.sh"
REFRESH="$LAB/hooks/memory-catalog-refresh.sh"
command -v jq >/dev/null 2>&1 || { echo "jq required"; exit 2; }

FIX=$(mktemp -d)
LABSRC=$(mktemp -d)            # stands in for an external symlink target
trap 'rm -rf "$FIX" "$LABSRC"' EXIT
write_tags() {
  cat > "$1" <<'EOF'
# tags
## domain
- nvidia — GPU vendor
- kde — KDE desktop
## tool
- git — version control
## Denylist
- config — too generic
## Policy overrides
EOF
}
write_tags "$FIX/_tags.md"
printf '# tag links\n## Synonyms\n## Distinctions\n## Path Tags\n' > "$FIX/_tag_links.md"
export MEMORY_SURFACE_DIR="$FIX"

mkwrite() { jq -cn --arg fp "$1" --arg c "$2" '{tool_name:"Write",cwd:"/tmp",tool_input:{file_path:$fp,content:$c}}'; }
mkedit()  { jq -cn --arg fp "$1" --arg ns "$2" '{tool_name:"Edit",cwd:"/tmp",tool_input:{file_path:$fp,new_string:$ns}}'; }
GOOD='---
name: m
description: "x"
metadata:
  node_type: memory
  type: feedback
  tags: [nvidia, kde]
---
b'
BAD='---
name: m
description: "x"
metadata:
  node_type: memory
  type: feedback
  tags: [nvidia, totally-bogus]
---
b'

pass=0; fail=0
rc_is() { if [ "$2" = "$3" ]; then echo "  ✓ $1"; pass=$((pass+1)); else echo "  ✗ $1 (want $2 got $3)"; fail=$((fail+1)); fi; }

echo "── context ──"
out=$(mkwrite "$FIX/n.md" "$GOOD" | "$CTX"); rc_is "memory write -> 0" 0 $?
echo "$out" | jq -e '.hookSpecificOutput.additionalContext|test("nvidia")' >/dev/null && { echo "  ✓ injects vocab"; pass=$((pass+1)); } || { echo "  ✗ no vocab"; fail=$((fail+1)); }
out=$(mkwrite "/tmp/x.md" "x" | "$CTX"); rc_is "off-store silent" 0 $?; [ -z "$out" ] && pass=$((pass+1)) || { echo "  ✗ leaked"; fail=$((fail+1)); }

echo "── guard: core contract ──"
mkwrite "$FIX/n.md" "$GOOD" | "$GUARD" >/dev/null 2>&1; rc_is "valid Write allowed" 0 $?
mkwrite "$FIX/n.md" "$BAD"  | "$GUARD" >/dev/null 2>&1; rc_is "bad-tag Write denied" 2 $?
mkedit  "$FIX/n.md" "free text" | "$GUARD" >/dev/null 2>&1; rc_is "Edit fails open" 0 $?
mkwrite "$FIX/_tags.md" "x" | "$GUARD" >/dev/null 2>&1; rc_is "valid taxonomy allowed" 0 $?
touch "$FIX/.surface-disabled"; mkwrite "$FIX/n.md" "$BAD" | "$GUARD" >/dev/null 2>&1; rc_is "kill-switch disables" 0 $?; rm -f "$FIX/.surface-disabled"

echo "── guard: review-fix regressions ──"
# ../ escape: a path textually under store but climbing out must NOT be gated (no false-deny).
mkwrite "$FIX/../escape.md" "$BAD" | "$GUARD" >/dev/null 2>&1; rc_is "../ escape NOT false-denied" 0 $?
mkjson_rel=$(jq -cn --arg fp "../escape.md" --arg c "$BAD" --arg cwd "$FIX" '{tool_name:"Write",cwd:$cwd,tool_input:{file_path:$fp,content:$c}}')
printf '%s' "$mkjson_rel" | "$GUARD" >/dev/null 2>&1; rc_is "relative ../ + cwd=store NOT false-denied" 0 $?
# engine unreadable -> fail OPEN even on a bad-tag write (copy hook so ../lib is absent)
ISO=$(mktemp -d); cp "$GUARD" "$ISO/g.sh"; chmod +x "$ISO/g.sh"
mkwrite "$FIX/n.md" "$BAD" | "$ISO/g.sh" >/dev/null 2>&1; rc_is "engine-unreadable fails OPEN" 0 $?; rm -rf "$ISO"
# trailing-slash MEMORY_SURFACE_DIR still gates (deny not silently disabled)
MEMORY_SURFACE_DIR="$FIX/" mkwrite_out=$(mkwrite "$FIX/n.md" "$BAD"); echo "$mkwrite_out" | MEMORY_SURFACE_DIR="$FIX/" "$GUARD" >/dev/null 2>&1; rc_is "trailing-slash store still denies" 2 $?
# unset HOME -> quiet fail-open (no 'unbound variable', exit 0)
err=$(mkwrite "$FIX/n.md" "$GOOD" | env -u HOME MEMORY_SURFACE_DIR="$FIX" "$GUARD" 2>&1 >/dev/null); rc_is "unset HOME exits 0" 0 $?; [ -z "$err" ] && { echo "  ✓ no stderr on unset HOME"; pass=$((pass+1)); } || { echo "  ✗ stderr leak: $err"; fail=$((fail+1)); }
# symlinked taxonomy still gates as in-store (canonicalization keeps it lexical)
printf '# tag links\n## Synonyms\n## Distinctions\n## Path Tags\n' > "$LABSRC/_tag_links.md"
rm -f "$FIX/_tag_links.md"; ln -s "$LABSRC/_tag_links.md" "$FIX/_tag_links.md"
mkwrite "$FIX/_tag_links.md" "x" | "$GUARD" >/dev/null 2>&1; rc_is "symlinked taxonomy still gated (allowed, valid)" 0 $?

echo "── refresh ──"
printf '%s' "$GOOD" > "$FIX/landed.md"; rm -f "$FIX/_memory_catalog.json"
mkwrite "$FIX/landed.md" "$GOOD" | "$REFRESH" >/dev/null 2>&1; rc_is "memory write -> 0" 0 $?
[ -f "$FIX/_memory_catalog.json" ] && { echo "  ✓ catalog built"; pass=$((pass+1)); } || { echo "  ✗ no catalog"; fail=$((fail+1)); }
ISO=$(mktemp -d); cp "$REFRESH" "$ISO/r.sh"; chmod +x "$ISO/r.sh"
err=$(mkwrite "$FIX/_tags.md" "x" | "$ISO/r.sh" 2>&1 >/dev/null); rc_is "engine-unreadable refresh quiet+0" 0 $?; [ -z "$err" ] && { echo "  ✓ no leak"; pass=$((pass+1)); } || { echo "  ✗ leak: $err"; fail=$((fail+1)); }; rm -rf "$ISO"

echo
echo "RESULT: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
