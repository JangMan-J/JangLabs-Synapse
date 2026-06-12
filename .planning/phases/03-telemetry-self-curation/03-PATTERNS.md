# Phase 3: Telemetry & Self-Curation — Pattern Map

**Mapped:** 2026-06-12
**Files analyzed:** 8 (5 modified, 3 new/extended)
**Analogs found:** 8 / 8

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `hooks/memory-recall.sh` | hook | event-driven (fire + append) | `hooks/memory-recall.sh` itself (extend) | self — extend existing |
| `hooks/memory-catalog-refresh.sh` | hook | event-driven (Read arm) | `hooks/memory-catalog-refresh.sh` itself (extend) | self — extend existing |
| `hooks/memory-base-floor.sh` | hook | event-driven (SessionStart + trigger) | `hooks/memory-base-floor.sh` itself (extend) | self — extend existing |
| `settings.global.fragment.json` | config | — | existing `PostToolUse` `Edit\|Write\|MultiEdit` block | exact config pattern |
| `lib/memory_surface.py` — `maintenance()` subcommand | service | batch (JSONL read + frontmatter mutate) | `rebuild()` in same file (lines 698–760) | role-match |
| `lib/memory_surface.py` — `_telemetry_stats()` helper | utility | transform | `path_tag_hits()` (lines 1086+) | partial |
| `lib/_review_game.py` | utility | — | n/a — deprecation header only, no logic change | n/a |
| `tests/memory_surface/test_phase3.py` | test | — | `tests/memory_surface/test_phase3.py` itself (extend) | self — extend existing |

---

## Pattern Assignments

### `hooks/memory-recall.sh` — D-33/D-34/D-35/D-36 (telemetry append)

**Analog:** Self — extend `hooks/memory-recall.sh`.

**Current post-Python jq extraction pattern** (lines 95–100 — the block to EXTEND, not replace):
```bash
_post=$(printf '%s' "$resp" | jq -r '
  ((.results // []) | length | tostring),
  ([(.results // [])[].id // empty] | join(" ")),
  (.surfaceText // "" | @base64)
' 2>/dev/null || true)
{ IFS= read -r n; IFS= read -r ids; IFS= read -r _surface_b64; } <<< "$_post"
```

**Extended 5-line read pattern** (replace the above; adds `_qid` and `_mems_json` as lines 4–5; keeps ONE jq spawn per T-02-13/CORE-04 constraint):
```bash
_post=$(printf '%s' "$resp" | jq -r '
  ((.results // []) | length | tostring),
  ([(.results // [])[].id // empty] | join(" ")),
  (.surfaceText // "" | @base64),
  (.queryId // ""),
  ([(.results // [])[] | {id: .id, mems: [.evidenceTuples[]? |
    {id: .id, tag: .tag, type: .trigger_type, val: .matched_value}]}] | @json)
' 2>/dev/null || true)
{ IFS= read -r n; IFS= read -r ids; IFS= read -r _surface_b64;
  IFS= read -r _qid; IFS= read -r _mems_json; } <<< "$_post"
```

**Telemetry append block** (insert AFTER line 139 `jq -cn ... exit 0`, BEFORE `exit 0`; D-33 fail-open: write AFTER emission with `|| true`):
```bash
# D-33/D-34/D-35: telemetry fire event — after emission, fail-open
if [ -n "$_qid" ]; then
  _tel_ts=$(date -u +%FT%TZ 2>/dev/null || true)
  _tel_conf=$(printf '%s' "$resp" | jq -r '.confidence // "low"' 2>/dev/null || true)
  _tel_line=$(printf '{"ts":"%s","qid":"%s","mems":%s,"conf":"%s"}' \
    "$_tel_ts" "$_qid" "${_mems_json:-[]}" "${_tel_conf:-low}")
  _tel="$STORE/_recall_telemetry.jsonl"
  # D-35: size-gated rotation at ~1MB, one .1 generation; mv is atomic on same fs
  if [ -f "$_tel" ] && [ "$(stat -c%s "$_tel" 2>/dev/null || echo 0)" -ge 1048576 ]; then
    mv "$_tel" "${_tel}.1" 2>/dev/null || true
  fi
  printf '%s\n' "$_tel_line" >> "$_tel" || true
fi
```

**Dedup mark pattern** (lines 116–133 — copy for the Read arm's dedup mark check in catalog-refresh):
```bash
DD="${XDG_RUNTIME_DIR:-$HOME/.cache}/claude-memory-recall"
MARK="$DD/m_${id//[^A-Za-z0-9._-]/_}"
if [ -f "$MARK" ] && [ -n "$(find "$MARK" -mmin -15 2>/dev/null)" ]; then
  # live mark = confirmed read-after-fire
fi
```

---

### `hooks/memory-catalog-refresh.sh` — D-37/D-38 (Read-signal arm)

**Analog:** Self — extend `hooks/memory-catalog-refresh.sh`.

**Existing TYPE-detection arm pattern** (lines 61–67 — copy this structure for the Read arm):
```bash
base=${abs##*/}
case "$base" in
  _tags.md|_tag_links.md) TYPE=taxonomy ;;
  _grammar.md) TYPE=grammar ;;
  MEMORY.md|_*) exit 0 ;;
  *) TYPE=memory ;;
esac
```

**Read-signal arm** (insert AFTER `IS_STORE_FILE` check at line 59, BEFORE the `base=` line — must `exit 0` to prevent falling through to `python3 "$ENGINE" rebuild`):
```bash
# D-37: Read-signal arm — detect read-after-fire via live dedup mark
tool=$(printf '%s' "$input" | jq -r '.tool_name // empty' 2>/dev/null || true)
if [ "$tool" = "Read" ]; then
  if [ "$IS_STORE_FILE" -eq 1 ]; then
    base_r=${abs##*/}
    case "$base_r" in
      MEMORY.md|_*) ;;   # infra files — no signal
      *.md)
        stem="${base_r%.md}"
        DD="${XDG_RUNTIME_DIR:-$HOME/.cache}/claude-memory-recall"
        MARK="$DD/m_${stem//[^A-Za-z0-9._-]/_}"
        if [ -f "$MARK" ] && [ -n "$(find "$MARK" -mmin -15 2>/dev/null)" ]; then
          _rs_ts=$(date -u +%FT%TZ 2>/dev/null || true)
          printf '{"ts":"%s","id":"%s","signal":"read"}\n' "$_rs_ts" "$stem" \
            >> "$STORE/_recall_telemetry.jsonl" || true
        fi ;;
    esac
  fi
  exit 0   # D-37: Read events NEVER trigger rebuild
fi
```

**Current settings fragment PostToolUse block** (reference for the new Read matcher addition — same structure, new matcher value):
```json
{
  "type": "command",
  "command": "~/.claude/hooks/memory-catalog-refresh.sh",
  "matcher": "Edit|Write|MultiEdit"
}
```
New block to ADD alongside it (same hook, new matcher):
```json
{
  "type": "command",
  "command": "~/.claude/hooks/memory-catalog-refresh.sh",
  "matcher": "Read"
}
```

---

### `hooks/memory-base-floor.sh` — D-40/D-44 (maintenance trigger + summary)

**Analog:** Self — extend `hooks/memory-base-floor.sh`.

**Current body construction** (lines 56–67 — inject maintenance BEFORE `body=` at line 56):
```bash
body=$(head -n 200 -- "$ROUTER" 2>/dev/null) || exit 0
[ -n "$body" ] || exit 0
body=${body//base-memory-floor/base-memory_floor}

floor=$(printf '<base-memory-floor store="%s">\n...\n%s\n</base-memory-floor>' "$BRAIN" "$body")

jq -cn --arg ctx "$floor" \
  '{hookSpecificOutput:{hookEventName:"SessionStart",additionalContext:$ctx}}'
exit 0
```

**Maintenance trigger insertion** (insert BEFORE the `body=` line; D-40 trigger + D-44 summary capture):
```bash
# D-40: maintenance trigger — run when telemetry has grown >= 50 records since last pass
_maint_summary=""
TELEMETRY_FILE="$BRAIN/_recall_telemetry.jsonl"
STATE_FILE="$BRAIN/_maintenance_state.json"
if [ -f "$TELEMETRY_FILE" ] && command -v python3 >/dev/null 2>&1; then
  _cur_lines=$(wc -l < "$TELEMETRY_FILE" 2>/dev/null || echo 0)
  _last_line=$(python3 -c "
import json, sys
try:
    d = json.loads(open('$STATE_FILE').read())
    print(d.get('lastPassLine', 0))
except: print(0)
" 2>/dev/null || echo 0)
  _new_records=$(( ${_cur_lines:-0} - ${_last_line:-0} ))
  if [ "${_new_records:-0}" -ge 50 ]; then
    SELF_FLOOR=$(readlink -f "$0" 2>/dev/null || printf '%s' "$0")
    ENGINE_FLOOR="$(dirname "$SELF_FLOOR")/../lib/memory_surface.py"
    if [ -r "$ENGINE_FLOOR" ]; then
      # D-40: hard timeout; fail open; must not block SessionStart > ~2s
      _maint_out=$(timeout 2 python3 "$ENGINE_FLOOR" maintenance 2>/dev/null || true)
      [ -n "$_maint_out" ] && _maint_summary="$_maint_out"
    fi
  fi
fi
```

**Summary injection into floor block** (append to `$body` before the floor printf; D-44):
```bash
if [ -n "$_maint_summary" ]; then
  body="${body}

Maintenance ($(date +%Y-%m-%d)): ${_maint_summary}"
fi
```

---

### `lib/memory_surface.py` — `maintenance()` subcommand (D-40–D-43, D-45, D-47/D-48)

**Analog:** `rebuild()` function (lines 698–760) for structural pattern; `load_config()` (lines 1032–1042) for config access; `write_atomic()` (lines 498–504) for frontmatter writes; `generate_frontmatter()` (lines 200–235) for mutation.

**`rebuild()` structure to copy** (lines 698–760 — iterate `_memory_files()`, parse frontmatter, build output, write atomically):
```python
def rebuild(memdir):
    # ... load config, parse grammar
    for p in _memory_files(memdir):
        raw = p.read_text()
        top, meta, body = parse_frontmatter(raw)
        # ... process
    write_atomic(catalog_path, json.dumps(catalog, ...))
```

**`load_config()` pattern** (lines 1032–1042 — all thresholds must be read from config, never hard-coded):
```python
def load_config(memdir):
    cfg = dict(DEFAULT_CONFIG)
    p = memdir / "_memory_surface_config.json"
    if p.exists():
        try:
            user = json.loads(p.read_text())
            if isinstance(user, dict):
                cfg.update(user)
        except (json.JSONDecodeError, OSError):
            pass   # malformed config -> safe defaults
    return cfg
```

**`generate_frontmatter()` pattern** (lines 200–235 — MUST use this for D-42 `declineCount` mutations; NOT `_review_game.py`'s writer which silently drops `triggers:`):
```python
def generate_frontmatter(top, meta, body):
    # ... rebuilds full frontmatter preserving triggers: block
    return "---\n" + "\n".join(out) + "\n---\n" + body
```

**`write_atomic()` pattern** (lines 498–504 — atomic write via tmp + os.replace; ensures no partial frontmatter on timeout kill):
```python
def write_atomic(path, text):
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
```

**New `maintenance()` function pattern** (from RESEARCH.md Pattern 3, lines 463–512 — full structure):
```python
def maintenance(memdir, shadow=False):
    """Run the automated maintenance pass (D-40–D-43).

    shadow=True: compute promote/demote list without writing (D-45 validation).
    Returns {promoted, demoted, zero_fire, summary} dict.
    Outputs summary line to stdout for base-floor.sh capture.
    """
    cfg = load_config(memdir)
    promote_thresh = cfg.get("promoteThreshold", 0.4)
    demote_thresh = cfg.get("demoteThreshold", 0.05)
    window_days = cfg.get("telemetryWindowDays", 30)

    tel_path = memdir / "_recall_telemetry.jsonl"
    fires, reads = _read_telemetry(tel_path, window_days)  # -> {memory_id: count}

    promoted, demoted, zero_fire = [], [], []
    for p in _memory_files(memdir):
        stem = p.stem
        fire_count = fires.get(stem, 0)
        read_count = reads.get(stem, 0)

        # D-43: zero-fire floor — never demote zero-fire memories
        if fire_count == 0:
            zero_fire.append(stem)
            continue

        rate = read_count / fire_count
        if rate >= promote_thresh:
            promoted.append(stem)
            if not shadow:
                _apply_score_delta(p, memdir, direction="promote")
        elif rate <= demote_thresh:
            demoted.append(stem)
            if not shadow:
                _apply_score_delta(p, memdir, direction="demote")  # increments declineCount

    summary = f"{len(demoted)} demoted, {len(promoted)} promoted"
    # D-44: output summary line for base-floor.sh capture
    if not shadow:
        print(summary)
        _update_maintenance_state(memdir)
    return {"promoted": promoted, "demoted": demoted,
            "zero_fire": zero_fire, "summary": summary}
```

**`_read_telemetry()` helper — parse JSONL for fires and reads in window**:
```python
def _read_telemetry(tel_path, window_days):
    """Parse _recall_telemetry.jsonl; return ({id: fire_count}, {id: read_count}).
    Only includes records within the last window_days.
    """
    import datetime
    fires, reads = {}, {}
    if not tel_path.exists():
        return fires, reads
    cutoff = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=window_days)
    for line in tel_path.read_text().splitlines():
        try:
            rec = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        # fire record: has "qid" and "mems"
        if "qid" in rec:
            try:
                ts = datetime.datetime.fromisoformat(rec["ts"].rstrip("Z") + "+00:00")
            except (KeyError, ValueError):
                continue
            if ts < cutoff:
                continue
            for mem in (rec.get("mems") or []):
                mid = mem.get("id", "")
                if mid:
                    fires[mid] = fires.get(mid, 0) + 1
        # read-signal record: has "signal": "read"
        elif rec.get("signal") == "read":
            mid = rec.get("id", "")
            if mid:
                reads[mid] = reads.get(mid, 0) + 1
    return fires, reads
```

**`_maintenance_state.json` tracking** (addresses RESEARCH.md open question Q10 / D-40 "since last pass"):
```python
def _update_maintenance_state(memdir):
    """Update _maintenance_state.json with current line count and timestamp."""
    tel_path = memdir / "_recall_telemetry.jsonl"
    state_path = memdir / "_maintenance_state.json"
    cur_lines = sum(1 for _ in tel_path.open()) if tel_path.exists() else 0
    state = {
        "lastPassLine": cur_lines,
        "lastPassTs": datetime.datetime.now(datetime.UTC).isoformat(),
    }
    write_atomic(state_path, json.dumps(state))
```

**`_apply_score_delta()` — D-42 frontmatter mutation via engine writer only**:
```python
def _apply_score_delta(p, memdir, direction):
    """Increment or clear declineCount in frontmatter (D-42).
    MUST use generate_frontmatter(), NEVER _review_game.py's write_frontmatter()
    (which silently drops triggers: — Pitfall D).
    """
    raw = p.read_text()
    top, meta, body = parse_frontmatter(raw)
    try:
        count = int(str(meta.get("declineCount", 0)).strip() or 0)
    except ValueError:
        count = 0
    if direction == "demote":
        meta["declineCount"] = str(count + 1)
    else:  # promote
        meta["declineCount"] = "0"
    write_atomic(p, generate_frontmatter(top, meta, body))
```

**CLI dispatch pattern** (search for `elif cmd == ` in memory_surface.py — new `maintenance` and `maintenance-shadow` subcommands follow the same `if cmd == "rebuild":` shape at the bottom of the file):
```python
elif cmd == "maintenance":
    result = maintenance(memdir)
    # summary already printed to stdout inside maintenance()
elif cmd == "maintenance-shadow":
    result = maintenance(memdir, shadow=True)
    print(json.dumps(result))
```

---

### `lib/_review_game.py` — D-46 (deprecation header only)

**Analog:** n/a — only a header comment is added; no logic changes.

**Pattern:** Add at the top of the file, after the shebang/docstring but before all imports:
```python
# DEPRECATED (Phase 3, 2026-06-12): Memory Roulette retired.
# Human curation replaced by automated telemetry-driven maintenance pass (memory_surface.py).
# The `offer` subcommand's hook registration has been removed from settings.global.fragment.json.
# Physical deletion of this file is deferred to Phase 4.
```

---

### `tests/memory_surface/test_phase3.py` — contract tests for Phase 3 behavior

**Analog:** `tests/memory_surface/test_phase3.py` itself (extend) + `test_routing_contract.py` (lines 126–158) for the fixture/make_store pattern.

**Hook invocation pattern** (lines 30–34 of test_phase3.py — reuse for telemetry test harness):
```python
def run_hook(hook, event, store, xdg):
    env = dict(os.environ, MEMORY_SURFACE_DIR=str(store), XDG_RUNTIME_DIR=str(xdg))
    p = subprocess.run([str(hook)], input=json.dumps(event), capture_output=True,
                       text=True, env=env)
    return p.returncode, p.stdout, p.stderr
```

**Fixture store builder pattern** (test_routing_contract.py lines 155–158 — make_store with temp dir + rebuild; reuse for maintenance tests):
```python
def make_store(tmp, tags=TAGS_MD, links=LINKS_MD, grammar=GRAMMAR_MD,
               memories=None, config=None):
    """Write fixture files into tmp and call rebuild(). Returns tmp path."""
```

**Contract test class structure** (test_phase3.py lines 37–45 — setUp/tearDown with temp store and xdg):
```python
class Recall(unittest.TestCase):
    def setUp(self):
        self.store = Path(tempfile.mkdtemp())
        t2.make_store(self.store)
        self.xdg = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.store, ignore_errors=True)
        shutil.rmtree(self.xdg, ignore_errors=True)
```

**New test classes needed** (follow the above structure; named constants for all pinned thresholds):
- `class TelemetryAppend` — tests for D-33/D-34/D-35/D-36: fire appends valid JSONL; fail-open on write error; rotation at 1MB; record schema has ts/qid/mems/conf.
- `class ReadSignal` — tests for D-37/D-38: Read of a store file with a live dedup mark appends `{signal:"read"}`; Read without live mark does NOT append; Read does NOT trigger rebuild.
- `class MaintenancePass` — tests for D-40/D-41/D-42/D-43: zero-fire floor (never demoted); fired-but-never-read at ≤0.05 is demoted; read_rate ≥0.4 is promoted; shadow mode returns list without writing; declineCount incremented exactly 1; triggers: block preserved after declineCount write (Pitfall D).
- `class ShadowValidation` — tests for D-45: no memory with `lastReviewed` set and declineCount=0 appears in the shadow demote list (validates the rare-critical floor against real store state).

---

## Shared Patterns

### Fail-open pattern
**Source:** `hooks/memory-recall.sh` throughout (e.g. `|| exit 0`, `|| true`, `2>/dev/null`)
**Apply to:** All three hooks; every new telemetry write; the maintenance trigger in base-floor.sh
```bash
# Any operation that could fail must exit 0 / use || true
some_command 2>/dev/null || true
printf '%s\n' "$line" >> "$file" || true
timeout 2 python3 "$ENGINE" maintenance 2>/dev/null || true
```

### Quiet-on-success pattern
**Source:** `hooks/memory-catalog-refresh.sh` (exit 0 at line 88; stderr only for actionable errors)
**Apply to:** All hook extensions — no output on the happy path
```bash
exit 0  # always; stderr only for actionable failures
```

### Store location pattern
**Source:** `hooks/memory-recall.sh` lines 27–31
**Apply to:** New telemetry append in memory-recall.sh (already has STORE); base-floor.sh (uses BRAIN which is the same path)
```bash
KEY=$(printf '%s' "$HOME" | tr '/' '-')
STORE="${MEMORY_SURFACE_DIR:-$HOME/.claude/projects/$KEY/memory}"; STORE=${STORE%/}
```

### Config-via-load_config() pattern
**Source:** `lib/memory_surface.py` lines 1032–1042
**Apply to:** All new maintenance pass thresholds (promoteThreshold, demoteThreshold, telemetryWindowDays, maintenanceTriggerCount, rotationSizeBytes)

### write_atomic() + generate_frontmatter() pattern
**Source:** `lib/memory_surface.py` lines 200–235 and 498–504
**Apply to:** All D-42 frontmatter mutations; never use `_review_game.py`'s `write_frontmatter()`

### TDD commit pattern
**Source:** `tests/memory_surface/` discipline described in CONTEXT.md Established Patterns
**Apply to:** All new test classes: `test(03-XX): RED` commit first, then `feat(03-XX): GREEN` commit

---

## No Analog Found

None — all Phase 3 files are extensions of existing Phase 2 components with strong analogs.

---

## Metadata

**Analog search scope:** `hooks/`, `lib/`, `tests/memory_surface/`, `settings.global.fragment.json`
**Files scanned:** 7 source files read in full
**Pattern extraction date:** 2026-06-12
