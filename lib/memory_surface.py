#!/usr/bin/env python3
"""memory_surface.py — taxonomy validation + catalog engine for tag-routed memory surfacing.

The SINGLE gated Python entry point for the memory hooks (the harness forbids per-tool-call
python; hooks cheap-gate in shell, then call this once). Phase 1 subcommands implemented here:

    validate      check taxonomy (_tags.md + _tag_links.md) integrity
    rebuild       regenerate _memory_catalog.json atomically from frontmatter (never bodies)
    check-write   validate a PROPOSED memory file's frontmatter/tags before it lands

Phase 2 will add: search / link / unlink / add-tag (token extraction, canonicalization, ranking).

Self-locates the box-brain store from $HOME ('/'->'-'); NEVER hardcodes the project key — the
pre-migration `-home-jangman` hardcode is exactly what broke the review-offer hook before.
Frontmatter parse/generate mirror _review_game.py's nested-metadata layout EXACTLY (see
[[misfire-restored-tool-read-ok-but-write-corrupts-on-format-drift]]) and additionally read the
block-list `tags:` form that _review_game.py's line parser silently drops.
"""
import datetime
import fnmatch
import hashlib
import json
import os
import re
import sys
import time
from collections import Counter
from pathlib import Path

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
TAG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,39}$")
META_ORDER = ["node_type", "type", "tags", "triggers", "originSessionId",
              "lastReviewed", "declineCount", "nextEligible"]
FACET_HEADS = ("domain", "tool", "pattern")

# ---------------------------------------------------------------- grammar constants (Plan 01-01)
PLACEMENTS = ("box", "project", "either")
GRAMMAR_FIELDS = ("gloss", "placement", "commands", "paths", "args", "synonyms", "related")

# ---------------------------------------------------------------- triggers constants (Plan 01-02)
TRIGGER_FIELDS = ("commands", "paths", "args", "synonyms")
BROAD_GLOBS = {"*", "**", "/**", "~/**"}
TRIGGER_SCHEMA_HINT = """\
triggers:
  commands: [tool-name, other-command]   # observable CLI commands
  paths: [~/.config/app/**]              # paths touched/read/written
  args: [domain-specific-arg]            # non-generic subcommand or argument
  synonyms: [alternative-name]           # query-token aliases (optional)

At least one behavioral evidence field (commands, paths, or args) must be non-empty.
Generic verbs alone (restart, start, stop, status, enable, disable, etc.) do not qualify.
Overly-broad globs alone (~/** or **) do not qualify.
Example:
  triggers:
    commands: [wpctl, pw-record]
    paths: [~/.config/pipewire/**]
    args: [set-volume]
    synonyms: [wireplumber]
"""

# ---------------------------------------------------------------- dedup constants (Plan 01-03)
# Conservative threshold — blocks only near-certain duplicates; pinned by contract tests.
# Adjust fixtures, never loosen this value silently (D-11, D-12).
DEDUP_BACKSTOP_THRESHOLD = 0.85

# Stopwords stripped from descriptions before the bag-of-words cosine (WR-02): without
# this, single-tag overlap (0.6) plus pure function-word/domain-noise cosine overlap
# ("a", "about", "on this box", "memory", ...) pushed DISTINCT memories past 0.85.
# English function words + store-domain noise words that appear in nearly every
# memory description and carry no subject signal.
DEDUP_STOPWORDS = frozenset((
    "a", "an", "the", "this", "that", "these", "those", "it", "its",
    "is", "are", "was", "be", "been",
    "on", "in", "at", "of", "to", "for", "with", "from", "by", "via", "and", "or", "as",
    "how", "what", "when", "where", "why", "which",
    "use", "using", "used", "about", "into", "vs",
    "box", "memory", "memories", "note", "notes", "lesson", "lessons",
))

# ---------------------------------------------------------------- write-context budget (Plan 01-03)
# 500-char headroom under the 10,000-char additionalContext cap (D-08).
WRITE_CONTEXT_BUDGET = 9500

# Relevance floor for dedup candidates shown in the write-context composite (WR-06):
# candidates scoring below this are noise — presenting zero-similarity memories as
# consolidation targets invites wrong consolidation and burns composite budget.
# Well below the 0.85 backstop; advisory section only, so a low floor is safe.
DEDUP_CANDIDATE_FLOOR = 0.2


# ---------------------------------------------------------------- store location
def resolve_memdir(explicit=None):
    if explicit:
        return Path(explicit)
    env = os.environ.get("MEMORY_SURFACE_DIR")
    if env:
        return Path(env)
    key = str(Path.home()).replace("/", "-")
    return Path.home() / ".claude" / "projects" / key / "memory"


# ---------------------------------------------------------------- frontmatter
def _parse_flow_tags(value):
    value = value.strip()
    if value.startswith("[") and value.endswith("]"):
        value = value[1:-1]
    return [t.strip().strip('"').strip("'") for t in value.split(",") if t.strip()]


def parse_frontmatter(text):
    """Return (top, meta, body). `meta['tags']` is a list (flow OR block form). Other meta
    values are raw strings. Top-level keeps name/description. Mirrors _review_game.py, plus
    block-list tag reading."""
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}, {}, text
    body = text[m.end():]
    lines = m.group(1).split("\n")
    top, meta = {}, {}
    in_meta = False
    i = 0
    while i < len(lines):
        raw = lines[i]
        if not raw.strip():
            i += 1
            continue
        if raw[0] in (" ", "\t"):                      # indented -> metadata child
            if in_meta:
                s = raw.strip()
                if s.startswith("- "):                 # stray block item (consumed via tags)
                    i += 1
                    continue
                if ":" in s:
                    k, v = s.split(":", 1)
                    k, v = k.strip(), v.strip()
                    if k == "tags":
                        if v:
                            meta["tags"] = _parse_flow_tags(v)
                            i += 1
                            continue
                        tags, j = [], i + 1            # block list on following lines
                        while j < len(lines):
                            li = lines[j]
                            ls = li.strip()
                            if li.startswith("  ") and ls.startswith("- "):
                                tags.append(ls[2:].strip().strip('"').strip("'"))
                                j += 1
                            elif not ls:
                                j += 1
                            else:
                                break
                        meta["tags"] = tags
                        i = j
                        continue
                    if k == "triggers" and not v:
                        # Peek-forward: consume sub-keys indented strictly DEEPER than
                        # the 'triggers:' line itself (WR-03: hardcoding the canonical
                        # 2-space metadata indent swallowed sibling keys when metadata
                        # children used a deeper — still valid YAML — indent).
                        # Unknown sub-keys are kept in the dict — validation rejects them.
                        trig_indent = len(raw) - len(raw.lstrip())
                        triggers = {}
                        j = i + 1
                        while j < len(lines):
                            sub = lines[j]
                            if not sub.strip():
                                j += 1
                                continue
                            # A line indented strictly deeper than 'triggers:' is a sub-key
                            if (sub[:1] in (" ", "\t") and
                                    len(sub) - len(sub.lstrip()) > trig_indent):
                                ss = sub.strip()
                                if ":" in ss:
                                    sk, sv = ss.split(":", 1)
                                    sk, sv = sk.strip(), sv.strip()
                                    if sk:
                                        triggers[sk] = _parse_flow_tags(sv) if sv else []
                                j += 1
                            else:
                                break
                        meta["triggers"] = triggers
                        i = j
                        continue
                    meta[k] = v
            i += 1
            continue
        if ":" not in raw:                             # top-level
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
    return top, meta, body


def generate_frontmatter(top, meta, body):
    """Re-emit preserving nested metadata + field order; tags as a flow list (canonical,
    matching _review_game.py). Unknown top/meta keys preserved in original order."""
    out = []
    for k in ("name", "description"):
        if k in top:
            out.append(f"{k}: {top[k]}")
    for k, v in top.items():
        if k not in ("name", "description"):
            out.append(f"{k}: {v}")
    out.append("metadata:")

    def emit(k, v):
        if k == "tags":
            tv = v if isinstance(v, list) else _parse_flow_tags(str(v))
            out.append(f"  tags: [{', '.join(tv)}]")
        elif k == "triggers" and isinstance(v, dict):
            out.append("  triggers:")
            for tf in TRIGGER_FIELDS:
                if tf in v and v[tf]:
                    vals = v[tf] if isinstance(v[tf], list) else [str(v[tf])]
                    out.append(f"    {tf}: [{', '.join(vals)}]")
                elif tf in v:
                    out.append(f"    {tf}: []")
        else:
            out.append(f"  {k}: {v}")

    seen = set()
    for k in META_ORDER:
        if k in meta:
            emit(k, meta[k])
            seen.add(k)
    for k, v in meta.items():
        if k not in seen:
            emit(k, v)
    return "---\n" + "\n".join(out) + "\n---\n" + body


# ---------------------------------------------------------------- taxonomy parsers
def parse_tags_md(path):
    """Live faceted grammar: '## domain|tool|pattern' headings, '- tag — gloss' (em-dash)
    lines. Plus optional '## Denylist' and '## Policy overrides' sections (same line grammar)."""
    active, deny, overrides = {}, {}, set()
    if not path.exists():
        return {"active": active, "deny": deny, "overrides": overrides}
    section = None
    line_re = re.compile(r"^- ([a-z0-9][a-z0-9-]{1,39})\s+[—-]\s+(.+)$")
    for raw in path.read_text().split("\n"):
        h = raw.strip()
        if h.startswith("## "):
            n = h[3:].strip().lower()
            if n.startswith("denylist"):
                section = "deny"
            elif n.startswith("policy overrides"):
                section = "override"
            elif any(n.startswith(f) for f in FACET_HEADS):
                section = "active"
            else:
                section = None
            continue
        m = line_re.match(raw)
        if not m:
            continue
        tag, rest = m.group(1), m.group(2)
        if section == "active":
            active[tag] = rest
        elif section == "deny":
            deny[tag] = rest
        elif section == "override":
            overrides.add(tag)
    return {"active": active, "deny": deny, "overrides": overrides}


def parse_tag_links(path):
    """P6 backtick grammar: ## Synonyms ('- `a` = `b` - reason'), ## Distinctions
    ('- `a` != `b` - reason'), ## Path Tags ('- `pat` -> `t1`, `t2` [@ strong|weak] [; reason'])."""
    syn, dist, paths = [], [], []
    if not path.exists():
        return {"synonyms": syn, "distinctions": dist, "path_tags": paths}
    section = None
    for raw in path.read_text().split("\n"):
        h = raw.strip()
        if h.startswith("## "):
            section = {"synonyms": "syn", "distinctions": "dist",
                       "path tags": "path"}.get(h[3:].strip().lower())
            continue
        if not raw.startswith("- "):
            continue
        if section == "syn":
            m = re.match(r"^- `([a-z0-9-]+)` = `([a-z0-9-]+)`(?:\s+-\s+(.*))?$", raw)
            if m:
                syn.append((m.group(1), m.group(2), m.group(3) or ""))
        elif section == "dist":
            m = re.match(r"^- `([a-z0-9-]+)` != `([a-z0-9-]+)`(?:\s+-\s+(.*))?$", raw)
            if m:
                dist.append((m.group(1), m.group(2), m.group(3) or ""))
        elif section == "path":
            m = re.match(r"^- `([^`]+)`\s*->\s*(.+?)(?:\s+@\s+(strong|weak))?(?:\s+;\s+(.*))?$", raw)
            if m:
                tags = re.findall(r"`([a-z0-9-]+)`", m.group(2))
                paths.append((m.group(1), tags, m.group(3) or "strong", m.group(4) or ""))
    return {"synonyms": syn, "distinctions": dist, "path_tags": paths}


def parse_grammar_md(path):
    """Parse _grammar.md into {tag: {facet, gloss, placement, commands, paths, args,
    synonyms, related, _unknown_fields}}.

    Scanner extends the parse_tags_md() pattern (D-02): H2 sets active facet,
    H3 opens an entry, field lines fill it.  Array fields are parsed via the
    _parse_flow_tags() strip-brackets/split-comma/strip-quotes approach.
    Missing file returns {} (fail-open, matching every existing parser).
    """
    if not Path(path).exists():
        return {}
    result = {}
    active_facet = None
    active_tag = None

    def _new_entry():
        return {
            "facet": active_facet,
            "gloss": "",
            "placement": "either",
            "commands": [],
            "paths": [],
            "args": [],
            "synonyms": [],
            "related": [],
            "_unknown_fields": [],
        }

    for raw in Path(path).read_text().split("\n"):
        h = raw.strip()
        if h.startswith("## "):
            # H2 — facet heading (domain/tool/pattern); ignore spec H2 sections
            n = h[3:].strip().lower()
            if any(n.startswith(f) for f in FACET_HEADS):
                active_facet = n
            else:
                active_facet = n   # still record so bad-facet validation works
            active_tag = None
            continue
        if h.startswith("### "):
            # H3 — tag entry start
            tag = h[4:].strip()
            active_tag = tag
            result[active_tag] = _new_entry()
            result[active_tag]["facet"] = active_facet
            continue
        if active_tag is None:
            continue
        if ":" not in raw:
            continue
        k, v = raw.split(":", 1)
        k, v = k.strip(), v.strip()
        if not k:
            continue
        if k == "gloss":
            result[active_tag]["gloss"] = v
        elif k == "placement":
            result[active_tag]["placement"] = v if v else "either"
        elif k in ("commands", "paths", "args", "synonyms", "related"):
            result[active_tag][k] = _parse_flow_tags(v) if v else []
        else:
            result[active_tag]["_unknown_fields"].append(k)
    return result


def validate_grammar(memdir):
    """Validate _grammar.md against the spec-defined schema rules (D-03).

    Returns a list of error strings (same shape as validate()).  Empty list = clean.
    Exit 0 if clean; exit 2 if errors (mirrored by CLI validate-grammar subcommand).

    Rules enforced:
    - Tag name must match TAG_RE
    - Gloss must be non-empty
    - Placement must be in PLACEMENTS (default 'either' for absent — not an error)
    - At least one behavioral evidence pattern across commands+paths+args (synonyms alone fail)
    - Every related: entry must reference a tag defined in this file
    - Unknown field names are errors
    - Facet must be in FACET_HEADS
    """
    grammar = parse_grammar_md(Path(memdir) / "_grammar.md")
    if not grammar:
        return []                                   # missing file -> fail open (no errors)
    errors = []
    all_tags = set(grammar.keys())
    for tag, entry in grammar.items():
        # Tag name shape
        if not TAG_RE.match(tag):
            errors.append(
                f"grammar tag '{tag}' is malformed (must match ^[a-z0-9][a-z0-9-]{{1,39}}$)"
            )
        # Facet must be in FACET_HEADS
        facet = (entry.get("facet") or "").lower()
        if facet not in FACET_HEADS:
            errors.append(
                f"grammar tag '{tag}' has unknown facet '{facet}' "
                f"(must be one of {FACET_HEADS})"
            )
        # Gloss must be non-empty
        if not (entry.get("gloss") or "").strip():
            errors.append(
                f"grammar tag '{tag}' has an empty gloss; every tag must have a "
                f"one-line meaning (gloss: ...)"
            )
        # Placement must be valid (absent already defaults to 'either' in parser)
        placement = entry.get("placement", "either")
        if placement not in PLACEMENTS:
            errors.append(
                f"grammar tag '{tag}' has invalid placement '{placement}' "
                f"(must be one of {PLACEMENTS})"
            )
        # Evidence requirement: at least one behavioral trigger across commands/paths/args
        has_evidence = (
            bool(entry.get("commands")) or
            bool(entry.get("paths")) or
            bool(entry.get("args"))
        )
        if not has_evidence:
            errors.append(
                f"grammar tag '{tag}' has no behavioral evidence patterns "
                f"(commands, paths, and args are all empty); synonyms alone do not qualify — "
                f"a tag without observable triggers cannot exist (D-03)"
            )
        # Related references must be defined tags in this file
        for ref in (entry.get("related") or []):
            if ref and ref not in all_tags:
                errors.append(
                    f"grammar tag '{tag}' has related: '{ref}' which is not defined "
                    f"in _grammar.md (undefined related tag)"
                )
        # Unknown field names
        for uf in (entry.get("_unknown_fields") or []):
            errors.append(
                f"grammar tag '{tag}' has unknown field '{uf}' "
                f"(recognized fields: {GRAMMAR_FIELDS})"
            )
    return errors


def synonym_map(synonyms):
    """alias -> canonical (left side is canonical)."""
    return {alias: canon for (canon, alias, _) in synonyms}


# ---------------------------------------------------------------- validation
def validate(memdir):
    tags = parse_tags_md(memdir / "_tags.md")
    links = parse_tag_links(memdir / "_tag_links.md")
    active = set(tags["active"])
    errors = []
    for t in sorted(active):
        if t in tags["deny"] and t not in tags["overrides"]:
            errors.append(f"active tag '{t}' is denylisted without a '## Policy overrides' entry")
    syn_pairs = set()
    alias_to_canon = {}
    for (c, a, _) in links["synonyms"]:
        if c not in active:                            # left=canonical must be a real tag;
            errors.append(f"synonym canonical '{c}' is not an active tag")
        if a in alias_to_canon and alias_to_canon[a] != c:   # §18: one synonym set per tag
            errors.append(f"tag '{a}' is an alias in multiple synonym sets "
                          f"('{alias_to_canon[a]}' and '{c}')")
        alias_to_canon[a] = c
        syn_pairs.add(frozenset((c, a)))               # right=alias is a free query token
    for (a, b, _) in links["distinctions"]:
        for t in (a, b):
            if t not in active:
                errors.append(f"distinction references unknown tag '{t}'")
        if frozenset((a, b)) in syn_pairs:
            errors.append(f"'{a}'/'{b}' are both a synonym and a distinction")
    for (pat, ptags, _, _) in links["path_tags"]:
        for t in ptags:
            if t not in active:
                errors.append(f"path-tag `{pat}` references unknown tag '{t}'")
    return errors


# ---------------------------------------------------------------- catalog
def _memory_files(memdir):
    for p in sorted(memdir.glob("*.md")):
        if p.name == "MEMORY.md" or p.name.startswith("_"):
            continue
        yield p


def fingerprint(memdir):
    h = hashlib.sha256()
    for name in ("_tags.md", "_tag_links.md", "_grammar.md"):   # _grammar.md added (Pitfall 6)
        p = memdir / name
        h.update(f"{name}:{p.stat().st_mtime_ns if p.exists() else 0}\0".encode())
    for p in _memory_files(memdir):
        h.update(f"{p.name}:{p.stat().st_mtime_ns}\0".encode())
    return "sha256:" + h.hexdigest()[:32]


def write_atomic(path, text):
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


# ---------------------------------------------------------------- trigger-index compiler (Plan 02-01)

# Tokens extracted from body text for D-29(b) mechanical fallback.
# Regex for backtick-quoted command tokens.
_BACKTICK_RE = re.compile(r"`([^`]+)`")
# Regex for path-like tokens (starts with ~ or /).
_PATHLIKE_RE = re.compile(r"(?:~|/)[A-Za-z0-9._/-]{3,}")
# Inline stopwords for derived-token noise filter (generic tool names that appear in
# nearly every memory body and carry no routing signal beyond GENERIC_BASH/GENERIC_VERBS).
_DERIVED_STOPWORDS = frozenset((
    "sudo", "doas", "pkexec", "env",    # privilege/runner
    "sh", "bash", "zsh", "fish",        # shells
    "python", "python3", "python2",     # interpreters
    "make", "cmake", "ninja",           # build tools
    "true", "false", "echo", "printf",  # builtins
))
# Token validity pattern: must look like a real command/binary name.
_TOKEN_RE = re.compile(r"^[a-z0-9][a-z0-9._+-]{2,31}$")


def derive_fallback_triggers(name, description, body):
    """D-29(b): extract concrete routing tokens from memory name/description/body text.

    Returns {"commands": [...], "paths": [...]} — sorted, deterministic, capped:
    - ≤6 commands, ≤4 paths
    - command tokens: backtick-quoted tokens matching _TOKEN_RE, excluding GENERIC_BASH,
      GENERIC_VERBS, _DERIVED_STOPWORDS
    - path tokens: path-like strings (starting with ~ or /) from body and description
    """
    combined = "\n".join(filter(None, [name, description, body]))

    # Extract backtick-quoted command tokens
    cmd_candidates = set()
    for tok in _BACKTICK_RE.findall(combined):
        tok = tok.strip()
        if not _TOKEN_RE.match(tok):
            continue
        if tok in GENERIC_BASH or tok in GENERIC_VERBS or tok in _DERIVED_STOPWORDS:
            continue
        cmd_candidates.add(tok)

    # Extract path-like tokens
    path_candidates = set()
    for tok in _PATHLIKE_RE.findall(combined):
        tok = tok.rstrip("/.,;)")  # strip trailing punctuation
        if len(tok) >= 5:         # must be a non-trivial path
            path_candidates.add(tok)

    return {
        "commands": sorted(cmd_candidates)[:6],
        "paths": sorted(path_candidates)[:4],
    }


def compile_trigger_index(grammar, memories_meta):
    """Build the triggerIndex inverted tables from grammar + per-memory triggers (D-21/D-25).

    Args:
        grammar: dict from parse_grammar_md() — {tag: {commands, paths, args, synonyms, ...}}
        memories_meta: list of (stem, meta, body_text) tuples for all valid memories.
            meta is the parsed frontmatter metadata dict (includes tags, triggers if present).
            body_text is the full file body used for D-29(b) fallback derivation.

    Returns (triggerIndex, recallVocab, routable_stems_set).

    triggerIndex shape:
        {byCommand: {cmd: [entry, ...]}, byPath: {expanded_path: [entry, ...]},
         byArg: {arg: [entry, ...]}, bySynonym: {syn: [entry, ...]},
         byMemoryId: {stem: [entry, ...]}}
    Each entry: {source: "tag"|"memory"|"memory-derived", id, trigger_type, pattern}

    recallVocab shape:
        {active: [grammar tag names], aliases: {synonym: tag}}
    """
    by_command = {}
    by_path = {}
    by_arg = {}
    by_synonym = {}
    by_memory_id = {}

    def _add(bucket, key, entry):
        bucket.setdefault(key, []).append(entry)

    # Compile grammar-level entries (D-21, source="tag")
    for tag, spec in grammar.items():
        for cmd in sorted(spec.get("commands", [])):
            if cmd:
                e = {"source": "tag", "id": tag, "trigger_type": "command", "pattern": cmd}
                _add(by_command, cmd, e)
        for syn in sorted(spec.get("synonyms", [])):
            if syn:
                e = {"source": "tag", "id": tag, "trigger_type": "synonym", "pattern": syn}
                _add(by_synonym, syn, e)
        for arg in sorted(spec.get("args", [])):
            if arg:
                e = {"source": "tag", "id": tag, "trigger_type": "arg", "pattern": arg}
                _add(by_arg, arg, e)
        for pat in sorted(spec.get("paths", [])):
            if pat:
                expanded = _expand(pat)
                e = {"source": "tag", "id": tag, "trigger_type": "path", "pattern": pat}
                _add(by_path, expanded, e)

    # Grammar tag set for coverage check
    grammar_tags = set(grammar.keys())

    # Compile per-memory entries (D-25, source="memory" or "memory-derived")
    for stem, meta, name, description, body_text in memories_meta:
        tags = meta.get("tags", []) or []
        has_grammar_coverage = any(t in grammar_tags for t in tags)
        triggers = meta.get("triggers", None)

        if triggers is not None:
            # Memory has explicit triggers: block — fold into index (D-25, source="memory")
            mem_entries = []
            for cmd in sorted(triggers.get("commands", []) or []):
                if cmd:
                    e = {"source": "memory", "id": stem, "trigger_type": "command", "pattern": cmd}
                    _add(by_command, cmd, e)
                    mem_entries.append(e)
            for syn in sorted(triggers.get("synonyms", []) or []):
                if syn:
                    e = {"source": "memory", "id": stem, "trigger_type": "synonym", "pattern": syn}
                    _add(by_synonym, syn, e)
                    mem_entries.append(e)
            for arg in sorted(triggers.get("args", []) or []):
                if arg:
                    e = {"source": "memory", "id": stem, "trigger_type": "arg", "pattern": arg}
                    _add(by_arg, arg, e)
                    mem_entries.append(e)
            for pat in sorted(triggers.get("paths", []) or []):
                if pat:
                    expanded = _expand(pat)
                    e = {"source": "memory", "id": stem, "trigger_type": "path", "pattern": pat}
                    _add(by_path, expanded, e)
                    mem_entries.append(e)
            if mem_entries:
                by_memory_id[stem] = sorted(mem_entries,
                                             key=lambda e: (e["trigger_type"], e["pattern"]))

        elif not has_grammar_coverage:
            # No grammar coverage, no triggers: → D-29(b) mechanical fallback
            derived = derive_fallback_triggers(name, description, body_text)
            derived_entries = []
            for cmd in derived.get("commands", []):
                e = {"source": "memory-derived", "id": stem, "trigger_type": "command",
                     "pattern": cmd}
                _add(by_command, cmd, e)
                derived_entries.append(e)
            for pat in derived.get("paths", []):
                expanded = _expand(pat)
                e = {"source": "memory-derived", "id": stem, "trigger_type": "path",
                     "pattern": pat}
                _add(by_path, expanded, e)
                derived_entries.append(e)
            if derived_entries:
                by_memory_id[stem] = sorted(derived_entries,
                                             key=lambda e: (e["trigger_type"], e["pattern"]))

    # Build recallVocab (D-21)
    aliases = {}
    for tag, spec in grammar.items():
        for syn in (spec.get("synonyms", []) or []):
            if syn:
                aliases[syn] = tag

    recall_vocab = {
        "active": sorted(grammar_tags),
        "aliases": aliases,
    }

    trigger_index = {
        "byCommand": by_command,
        "byPath": by_path,
        "byArg": by_arg,
        "bySynonym": by_synonym,
        "byMemoryId": by_memory_id,
    }

    # Compute routable stems
    routable = set()
    for stem, meta, name, description, body_text in memories_meta:
        tags = meta.get("tags", []) or []
        if any(t in grammar_tags for t in tags):
            routable.add(stem)  # D-29(a): tag-level grammar coverage
        elif stem in by_memory_id:
            routable.add(stem)  # D-29(b): has derived or explicit entries

    return trigger_index, recall_vocab, routable


# ---------------------------------------------------------------- maintenance pass (Phase 3, Plan 02)

def _read_telemetry(tel_path, window_days):
    """Parse _recall_telemetry.jsonl (+ its .1 rotation generation); return
    ({id: fire_count}, {id: read_count}).

    Only includes records within the last window_days (rectangular window — D-41).
    Fire records have a "qid" key; read records have signal=="read".
    Session records ({signal:"session"}) and malformed lines are silently skipped.
    Supports both ISO-8601 UTC strings (e.g. '2026-06-12T10:00:00Z') and epoch integers.

    WR-04: the .1 generation is read FIRST (chronologically older) so a 1MB
    rotation does not strand pre-rotation read signals while fresh fires for
    the same memories accumulate in the new file (read_rate biased toward 0).
    The window filter discards out-of-window records either way; total size is
    bounded at ~2MB (one _TEL_MAX per generation).
    """
    fires, reads = {}, {}
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=window_days)
    for p in (tel_path.with_name(tel_path.name + ".1"), tel_path):
        try:
            if not p.exists():
                continue
            text = p.read_text()
        except OSError:
            continue
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            # Parse timestamp (defensive: ISO-8601 or epoch integer)
            ts_raw = rec.get("ts", "")
            try:
                if isinstance(ts_raw, (int, float)):
                    ts = datetime.datetime.fromtimestamp(ts_raw, tz=datetime.timezone.utc)
                else:
                    ts = datetime.datetime.fromisoformat(str(ts_raw).rstrip("Z") + "+00:00")
            except (ValueError, TypeError, OSError):
                ts = None
            # Fire record: has "qid" key
            if "qid" in rec:
                if ts is None or ts < cutoff:
                    continue
                for mem in (rec.get("mems") or []):
                    mid = mem.get("id", "")
                    if mid:
                        fires[mid] = fires.get(mid, 0) + 1
            # Read-signal record: has signal == "read"
            elif rec.get("signal") == "read":
                # Read signals: apply window only if ts is parseable; otherwise skip
                if ts is not None and ts < cutoff:
                    continue
                mid = rec.get("id", "")
                if mid:
                    reads[mid] = reads.get(mid, 0) + 1
            # Other records (signal:"session", unknown) silently skipped
    return fires, reads


def _evidence_stats(tel_path):
    """Return (session_days, span_days) across ALL telemetry records, including
    the .1 rotation generation when present (WR-04).

    session_days: number of DISTINCT calendar days (UTC) carrying at least one
    {signal:"session"} SessionStart marker (03-02 Block 1). Dedupe-per-day
    (WR-03): the hook appends a marker on EVERY SessionStart event — including
    resume/clear/compact re-fires — so the raw marker count is inflated; one
    busy working day could satisfy a >=10 "sessions" guard in hours and reopen
    the premature-decay window. Counting distinct days makes the leg mean
    sustained observation. Markers with unparseable ts are dropped (they
    cannot be assigned a day).
    span_days: days between the oldest parseable ts anywhere in the file and now.

    The D-41 window caps the LOOKBACK for rate computation; this measures whether
    enough observation exists AT ALL. Without it, the pass demotes fired-but-unread
    memories hours after telemetry first ships — an artifact of the system's youth,
    not evidence of memory uselessness (the premature-demotion class caught live
    on 2026-06-12: 22 demotions from <1 day of data).
    Fail-open: missing/unreadable file -> (0, 0.0).
    """
    session_days, oldest = set(), None
    # WR-04: include the .1 rotation generation — without it every rotation
    # resets session-day count and span to ~zero, silently suspending
    # self-curation for up to 30 days while the window re-accumulates.
    for p in (tel_path.with_name(tel_path.name + ".1"), tel_path):
        try:
            if not p.exists():
                continue
            text = p.read_text()
        except OSError:
            continue
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            ts_raw = rec.get("ts", "")
            try:
                if isinstance(ts_raw, (int, float)):
                    ts = datetime.datetime.fromtimestamp(ts_raw, tz=datetime.timezone.utc)
                else:
                    ts = datetime.datetime.fromisoformat(str(ts_raw).rstrip("Z") + "+00:00")
            except (ValueError, TypeError, OSError):
                continue
            if rec.get("signal") == "session":
                session_days.add(ts.date())
            if oldest is None or ts < oldest:
                oldest = ts
    if oldest is None:
        return len(session_days), 0.0
    span = (datetime.datetime.now(datetime.timezone.utc) - oldest).total_seconds() / 86400.0
    return len(session_days), max(span, 0.0)


def _apply_score_delta(p, memdir, direction):
    """Increment or clear declineCount in frontmatter (D-42).

    MUST use generate_frontmatter(), NEVER _review_game.py's deprecated writer
    (which silently drops triggers: — Pitfall D).
    direction: 'demote' -> declineCount += 1; 'promote' -> declineCount = '0'.
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


def _update_maintenance_state(memdir):
    """Write _maintenance_state.json with current telemetry line count and ISO UTC timestamp."""
    tel_path = memdir / "_recall_telemetry.jsonl"
    state_path = memdir / "_maintenance_state.json"
    try:
        with tel_path.open() as _f:
            cur_lines = sum(1 for _ in _f)
    except OSError:
        cur_lines = 0
    state = {
        "lastPassLine": cur_lines,
        "lastPassTs": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    write_atomic(state_path, json.dumps(state))


_MAINT_LOCK_STALE_SECS = 300   # a pass runs <2s (hook cap); anything older is a corpse


def _acquire_maintenance_lock(memdir):
    """Best-effort exclusive advisory lock for the non-shadow maintenance pass (WR-02).

    O_CREAT|O_EXCL on _maintenance_state.json.lock. Returns the lock Path on
    success, None when another pass holds a fresh lock OR on any error (fail
    open by SKIPPING mutations — never by running unlocked). A stale lock
    left by a killed pass (older than _MAINT_LOCK_STALE_SECS) is reclaimed.
    """
    lock_path = memdir / "_maintenance_state.json.lock"
    for _ in range(2):                  # one retry after a stale-lock reclaim
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            return lock_path
        except FileExistsError:
            try:
                age = time.time() - lock_path.stat().st_mtime
            except OSError:
                continue                # lock vanished between open and stat — retry create
            if age <= _MAINT_LOCK_STALE_SECS:
                return None             # fresh lock: a concurrent pass is running
            try:
                lock_path.unlink()      # stale corpse — reclaim, then retry create
            except OSError:
                return None
        except OSError:
            return None                 # unwritable store etc. — mutations would fail anyway
    return None


def _release_maintenance_lock(lock_path):
    try:
        lock_path.unlink()
    except OSError:
        pass


def _recheck_threshold(memdir):
    """Re-derive the hook's D-40 threshold decision under the lock (WR-02).

    Mirrors memory-base-floor.sh Block 2, including the rotation-reset rule
    (negative delta -> all current lines count as new). Closes the hook's
    read-then-act race: two near-simultaneous SessionStarts both pass the
    shell gate, but the lock serializes the spawns and the later one
    re-checks against the state the first one just advanced — and skips.
    Fail-open direction is SKIP (False): the cost of a wrong skip is one
    deferred pass; the cost of a wrong run is a doubled declineCount.
    """
    try:
        cfg = load_config(memdir)
        thresh = int(cfg.get("maintenanceTriggerCount", 50))
        try:
            with (memdir / "_recall_telemetry.jsonl").open() as f:
                cur = sum(1 for _ in f)
        except OSError:
            cur = 0
        try:
            last = int(json.loads(
                (memdir / "_maintenance_state.json").read_text()
            ).get("lastPassLine", 0) or 0)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            last = 0
        new = cur - last
        if new < 0:
            new = cur                   # rotation-reset (same rule as the hook)
        return new >= thresh
    except Exception:  # noqa: BLE001 — fail open by skipping
        return False


def maintenance(memdir, shadow=False, recheck=False):
    """Run the automated maintenance pass (D-40/D-41/D-42/D-43).

    shadow=True: compute promote/demote/zero_fire without writing any file (D-45).
    recheck=True: re-verify the D-40 trigger threshold under the lock before
    mutating (WR-02 — the CLI sets this for hook-spawned passes via
    --recheck-threshold; direct API callers default to an unconditional pass).
    Returns {promoted, demoted, zero_fire, summary, insufficient_evidence} dict.
    Non-shadow prints the summary line to stdout (for memory-base-floor.sh capture).
    Wraps all internal errors to fail open — no exception propagates to the caller.

    Concurrency (WR-02): non-shadow passes serialize on an O_EXCL advisory
    lock (_maintenance_state.json.lock). The loser skips silently — no print,
    no mutation — so two simultaneous SessionStarts cannot double-increment
    declineCount for one logical pass period.

    D-43 rare-critical floor: memories with ZERO fires in the telemetry window are
    NEVER demoted. Only fired-but-never-read memories decay. The guard precedes all
    rate computation to avoid ZeroDivisionError.

    Minimum-evidence guard: NON-SHADOW mutations require >=minEvidenceSessions
    distinct session-DAYS (WR-03: markers deduped per calendar day, so re-fire
    inflation cannot satisfy the leg) OR >=minEvidenceDays observed span (same standard as D-47
    seat governance). Shadow mode still computes the would-be lists for D-45
    diagnostics but carries insufficient_evidence=True so consumers know the
    real pass would defer.
    """
    lock_path = None
    try:
        if not shadow:
            lock_path = _acquire_maintenance_lock(memdir)
            if lock_path is None:
                # Another pass holds the lock — the loser exits silently (WR-02).
                return {"promoted": [], "demoted": [], "zero_fire": [],
                        "summary": "", "insufficient_evidence": False,
                        "skipped": "lock-held"}
            if recheck and not _recheck_threshold(memdir):
                return {"promoted": [], "demoted": [], "zero_fire": [],
                        "summary": "", "insufficient_evidence": False,
                        "skipped": "threshold-unmet"}
        cfg = load_config(memdir)
        promote_thresh = cfg.get("promoteThreshold", 0.4)
        demote_thresh = cfg.get("demoteThreshold", 0.05)
        window_days = cfg.get("telemetryWindowDays", 30)
        min_sessions = cfg.get("minEvidenceSessions", 10)
        min_days = cfg.get("minEvidenceDays", 30)

        tel_path = memdir / "_recall_telemetry.jsonl"
        session_days, span_days = _evidence_stats(tel_path)
        evidence_ok = (session_days >= min_sessions) or (span_days >= min_days)
        if not evidence_ok and not shadow:
            summary = (f"insufficient evidence ({session_days} session-days, "
                       f"{span_days:.1f}d observed; mutations deferred until "
                       f">={min_sessions} session-days or >={min_days}d)")
            print(summary)
            _update_maintenance_state(memdir)
            return {"promoted": [], "demoted": [], "zero_fire": [],
                    "summary": summary, "insufficient_evidence": True}

        fires, reads = _read_telemetry(tel_path, window_days)

        # WR-01 claim-then-mutate: advance _maintenance_state.json BEFORE applying
        # any mutation. A pass killed mid-loop (2s hook timeout, transient OSError)
        # then LOSES one pass instead of REPLAYING it next SessionStart — the
        # fail-safe direction. Replaying re-increments declineCount for every
        # already-demoted memory each session until the failure clears (the
        # 22-demotion class via partial-pass replay).
        if not shadow:
            _update_maintenance_state(memdir)

        promoted, demoted, zero_fire = [], [], []
        for p in _memory_files(memdir):
            stem = p.stem
            fire_count = fires.get(stem, 0)
            read_count = reads.get(stem, 0)

            # D-43: zero-fire floor — never demote zero-fire memories.
            # This guard PRECEDES rate computation to avoid ZeroDivisionError.
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
                    _apply_score_delta(p, memdir, direction="demote")

        summary = f"{len(demoted)} demoted, {len(promoted)} promoted"
        if not shadow:
            print(summary)
            # state already claimed before the mutation loop (WR-01)
            # CUR-05: seat governance runs with the same telemetry, same D-40 cadence
            try:
                seats(memdir)
            except Exception:  # noqa: BLE001 — fail open; seat errors must not block maintenance
                pass
        return {"promoted": promoted, "demoted": demoted,
                "zero_fire": zero_fire, "summary": summary,
                "insufficient_evidence": not evidence_ok}
    except Exception:  # noqa: BLE001 — fail open; engine errors must not block SessionStart
        return {"promoted": [], "demoted": [], "zero_fire": [], "summary": "0 demoted, 0 promoted",
                "insufficient_evidence": False}
    finally:
        if lock_path is not None:
            _release_maintenance_lock(lock_path)


# ---------------------------------------------------------------- Seat governance (D-47/D-48)

# Match ](stem.md) — robust to nested brackets in link titles (e.g. [[Misfire] ...](stem.md))
_SEAT_LINK_RE = re.compile(r"\]\(([^/)]+)\.md\)")


def _parse_seat_stems(memdir):
    """Parse router seat stems from MEMORY.md (shared parsing rule with seat_probes.py).

    Scans the '## Always-relevant entries' section for markdown-link targets
    matching '*.md' basenames (no slashes — store-relative only).
    Returns list of stem strings (filename without .md extension).
    """
    mem_md = memdir / "MEMORY.md"
    if not mem_md.exists():
        return []
    stems = []
    in_section = False
    for line in mem_md.read_text().splitlines():
        stripped = line.strip()
        if stripped.startswith("## Always-relevant"):
            in_section = True
            continue
        if in_section:
            if stripped.startswith("## "):
                break
            m = _SEAT_LINK_RE.search(stripped)
            if m:
                stems.append(m.group(1))  # group 1 = stem (without .md)
    return stems


def _write_pending_block(memdir, proposals):
    """Write or remove the PENDING-SEAT-CHANGES block at the top of MEMORY.md (D-48).

    proposals: list of strings like 'DEMOTE: stem.md — reason' or 'PROMOTE: stem.md — reason'.
    When proposals is empty, any existing pending block is stripped (idempotent removal).
    The rest of MEMORY.md is byte-identical before and after (never truncated or rewritten).

    This is the ONLY sanctioned writer of MEMORY.md in the engine; it must stay surgical.
    Never accessed via _memory_files() — MEMORY.md is excluded from that iterator by design.
    """
    mem_md = memdir / "MEMORY.md"
    if not mem_md.exists():
        return

    current = mem_md.read_text()
    # Strip any existing pending block (delimiter-bounded, greedy to end of first -->)
    stripped = re.sub(
        r"<!-- PENDING-SEAT-CHANGES.*?-->[\n]*",
        "",
        current,
        flags=re.DOTALL,
    )

    if not proposals:
        # No proposals: write back stripped content (removes stale block if any)
        if stripped != current:
            write_atomic(mem_md, stripped)
        return

    # Build new pending block
    today = datetime.date.today().isoformat()
    lines = [f"<!-- PENDING-SEAT-CHANGES (automated, {today}) — review and delete this block to approve:"]
    for p in proposals:
        lines.append(f"  {p}")
    lines.append("-->")
    block = "\n".join(lines) + "\n"

    write_atomic(mem_md, block + stripped)


def seats(memdir):
    """Seat governance engine subcommand (CUR-05, D-47/D-48).

    Reads the probe sidecar (_seat_probe_results.json) and telemetry to build
    demote/promote proposals, then writes the PENDING-SEAT-CHANGES block to
    MEMORY.md (or removes it when no proposals).

    Dual D-47 gate for demotion:
    (a) probe sidecar shows covered:true for the seat
    (b) telemetry shows fire_count >= 1 for the seat in the window
    AND the evidence window is met (>= minEvidenceSessions OR >= minEvidenceDays).
    Missing probe sidecar → zero demotions (fail-safe, T-03-24).

    Promote candidates: non-seat memories with fire_count >= seatPromoteMinFires
    AND read_rate >= promoteThreshold (in-window, window-gated).

    Returns a result dict; always exception-proof (exit 0, no exception to caller).
    """
    try:
        cfg = load_config(memdir)
        window_days = cfg.get("telemetryWindowDays", 30)
        min_sessions = cfg.get("minEvidenceSessions", 10)
        min_days = cfg.get("minEvidenceDays", 30)
        promote_thresh = cfg.get("promoteThreshold", 0.4)
        seat_promote_min_fires = cfg.get("seatPromoteMinFires", 5)

        # Read evidence window stats (distinct session-days + span)
        tel_path = memdir / "_recall_telemetry.jsonl"
        session_days, span_days = _evidence_stats(tel_path)
        evidence_ok = (session_days >= min_sessions) or (span_days >= min_days)

        if not evidence_ok:
            result = {
                "demote": [],
                "promote": [],
                "reason": (
                    f"window unmet ({session_days} session-days, {span_days:.1f}d span; "
                    f"need >={min_sessions} session-days or >={min_days}d)"
                ),
                "evidence_ok": False,
            }
            # Still attempt to remove a stale pending block when window unmet
            _write_pending_block(memdir, [])
            return result

        # Load probe sidecar
        probe_path = memdir / "_seat_probe_results.json"
        if not probe_path.exists():
            result = {
                "demote": [],
                "promote": [],
                "reason": "no-probe-results",
                "evidence_ok": True,
            }
            # Remove stale pending block if any
            _write_pending_block(memdir, [])
            return result

        try:
            probe_data = json.loads(probe_path.read_text())
        except (json.JSONDecodeError, OSError):
            result = {
                "demote": [],
                "promote": [],
                "reason": "probe-sidecar-unreadable",
                "evidence_ok": True,
            }
            _write_pending_block(memdir, [])
            return result

        probe_results = probe_data.get("results", {})
        seat_stems = set(_parse_seat_stems(memdir))

        # Read windowed telemetry
        fires, reads = _read_telemetry(tel_path, window_days)

        # Build demote proposals: D-47 dual gate
        demote_proposals = []
        demote_stems = []
        for stem, probe_r in probe_results.items():
            covered = probe_r.get("covered", False)
            fire_count = fires.get(stem, 0)
            read_count = reads.get(stem, 0)
            if covered and fire_count >= 1:
                rate = read_count / fire_count if fire_count else 0.0
                payload_ref = (probe_r.get("payload") or {}).get("tool_input", {})
                cmd_or_path = (payload_ref.get("command") or payload_ref.get("file_path") or "?")
                demote_proposals.append(
                    f"DEMOTE: {stem}.md — fired {fire_count}x in window, "
                    f"read {read_count}x (read_rate={rate:.2f}), "
                    f"probe payload: {cmd_or_path!r}"
                )
                demote_stems.append(stem)

        # Build promote proposals: non-seat memories meeting criteria
        promote_proposals = []
        promote_stems = []
        for p in _memory_files(memdir):
            stem = p.stem
            if stem in seat_stems:
                continue  # seats are demote candidates, not promote candidates here
            fire_count = fires.get(stem, 0)
            read_count = reads.get(stem, 0)
            if fire_count >= seat_promote_min_fires:
                rate = read_count / fire_count
                if rate >= promote_thresh:
                    promote_proposals.append(
                        f"PROMOTE: {stem}.md — fired {fire_count}x, "
                        f"read {read_count}x (read_rate={rate:.2f} >= {promote_thresh})"
                    )
                    promote_stems.append(stem)

        # Write pending block (or remove if no proposals)
        all_proposals = demote_proposals + promote_proposals
        _write_pending_block(memdir, all_proposals)

        return {
            "demote": demote_stems,
            "promote": promote_stems,
            "reason": None,
            "evidence_ok": True,
        }
    except Exception:  # noqa: BLE001 — fail open
        return {"demote": [], "promote": [], "reason": "internal-error", "evidence_ok": False}


def rebuild(memdir):
    tags = parse_tags_md(memdir / "_tags.md")
    active = set(tags["active"])
    # Synonym map now derived from grammar (same vocabulary as recallVocab.aliases — principle 6).
    # _tag_links.md synonyms are legacy; parse_tag_links() is still used by write-path (validate,
    # link, unlink, add_tag) and retires with those files in a later phase.
    grammar_pre = parse_grammar_md(memdir / "_grammar.md")
    smap = {syn: tag for tag, spec in grammar_pre.items()
            for syn in (spec.get("synonyms", []) or []) if syn}
    memories, invalid, tag_index = [], [], {}
    # Collect per-memory metadata tuples for the trigger-index compiler
    memories_meta = []   # (stem, meta, name, description, body_text)
    for p in _memory_files(memdir):
        raw = p.read_text()
        top, meta, body = parse_frontmatter(raw)
        mtags = meta.get("tags", []) or []
        bad = [t for t in mtags if t not in active]
        if bad:
            invalid.append({"file": p.name, "error": f"unknown tags: {sorted(set(bad))}"})
            continue
        canon = sorted({smap.get(t, t) for t in mtags})
        desc = (top.get("description", "") or "").strip().strip('"').strip("'")
        name = top.get("name", p.stem)
        try:
            decline = int(str(meta.get("declineCount", 0)).strip() or 0)
        except ValueError:
            decline = 0
        memories.append({
            "id": p.stem, "file": p.name, "path": str(p),
            "name": name, "description": desc,
            "type": meta.get("type", ""), "tags": mtags, "canonicalTags": canon,
            "lastReviewed": (meta.get("lastReviewed", "") or "").strip(),
            "declineCount": decline,
        })
        memories_meta.append((p.stem, meta, name, desc, body))
        for t in canon:
            tag_index.setdefault(t, []).append(p.stem)

    # Compile trigger index from grammar + per-memory triggers + mechanical fallback (D-21/D-25/D-29)
    # Reuse grammar_pre parsed above for smap (single parse, single vocabulary — principle 6).
    grammar = grammar_pre
    trigger_index, recall_vocab, routable_ids = compile_trigger_index(grammar, memories_meta)

    # Routability report (D-23)
    all_valid_ids = [m["id"] for m in memories]
    unroutable = sorted([mid for mid in all_valid_ids if mid not in routable_ids])
    if unroutable:
        print(f"UNROUTABLE ({len(unroutable)}): {', '.join(unroutable)}", file=sys.stderr)
    routability_report = {
        "unroutableCount": len(unroutable),
        "unroutableIds": unroutable,
    }

    catalog = {
        "schemaVersion": 1,
        "sourceFingerprint": fingerprint(memdir),
        "generatedAt": datetime.date.today().isoformat(),
        "memoryDir": str(memdir),
        "activeTags": sorted(active),
        "memories": memories,
        "tagToMemoryIds": tag_index,
        "invalidMemories": invalid,
        # Phase 2 additions (additive — D-30 no dark window)
        "triggerIndex": trigger_index,
        "recallVocab": recall_vocab,
        "routabilityReport": routability_report,
    }
    write_atomic(memdir / "_memory_catalog.json",
                 json.dumps(catalog, indent=1, ensure_ascii=False) + "\n")
    return catalog


# ---------------------------------------------------------------- check-write
def _check_triggers(triggers):
    """Validate a triggers dict for shape and specificity (D-09, D-10).

    Returns (rc, reason):
      rc 0 — triggers are valid
      rc 2 — deny; reason string includes TRIGGER_SCHEMA_HINT

    Checks in order:
      1. Must be a dict of string lists (shape)
      2. All field names must be in TRIGGER_FIELDS (D-04 vocabulary)
      3. At least one behavioral evidence field (commands/paths/args) non-empty (D-09)
      4. Specificity gate: generic-only commands with no specific args/paths → deny (D-10)
    """
    if not isinstance(triggers, dict):
        return 2, (
            "triggers must be a dict (the 'triggers:' block under metadata:).\n"
            + TRIGGER_SCHEMA_HINT
        )
    # Unknown field names check (D-04 vocabulary)
    unknown = [k for k in triggers if k not in TRIGGER_FIELDS]
    if unknown:
        return 2, (
            f"triggers block has unknown field(s): {', '.join(sorted(unknown))}. "
            f"Allowed fields are: {', '.join(TRIGGER_FIELDS)}.\n"
            + TRIGGER_SCHEMA_HINT
        )
    # Field values must be lists of strings
    for field in TRIGGER_FIELDS:
        val = triggers.get(field, [])
        if not isinstance(val, list):
            return 2, (
                f"triggers.{field} must be a list of strings (got {type(val).__name__}).\n"
                + TRIGGER_SCHEMA_HINT
            )
        for item in val:
            if not isinstance(item, str):
                return 2, (
                    f"triggers.{field} must contain only strings.\n"
                    + TRIGGER_SCHEMA_HINT
                )
    # Evidence requirement: at least one of commands/paths/args must be non-empty
    cmds = [c for c in triggers.get("commands", []) if c]
    paths = [p for p in triggers.get("paths", []) if p]
    args = [a for a in triggers.get("args", []) if a]
    if not cmds and not paths and not args:
        return 2, (
            "triggers block has no behavioral evidence: commands, paths, and args are all "
            "empty. At least one must be non-empty (synonyms alone do not qualify — "
            "a memory with no observable behavioral trigger cannot be routed).\n"
            + TRIGGER_SCHEMA_HINT
        )
    # Specificity gate (D-10): generic-only commands with no qualifying paths/args.
    # Breadth, not spelling (WR-03 iter 2): set membership cannot close the broad-glob
    # class — /home/**, $HOME/**, and ~user/** all subsume the denied ~/**. For any
    # recursive glob (.../**) compute its expanded non-wildcard root and treat the
    # pattern as broad when that root sits at or above the home directory. The literal
    # set still catches the bare * / ** / ~ / ~/ forms. Expansion is local to this
    # gate (os.path.expandvars + expanduser, which also handles ~user) so the routing
    # path's _expand() stays untouched.
    home = str(Path.home())
    broad_literals = ({_expand(g).rstrip("/") for g in BROAD_GLOBS}
                      | {home, "/", ""})

    def _is_broad(pat):
        p = os.path.expanduser(os.path.expandvars(pat)).rstrip("/")
        if p in broad_literals:
            return True
        if p.endswith("/**"):
            root = p[:-3]
            # Non-wildcard root: cut at the first wildcard char, then back to the
            # last completed path component (so /home/*/** roots at /home).
            for i, ch in enumerate(root):
                if ch in "*?[":
                    root = root[:root.rfind("/", 0, i + 1) + 1]
                    break
            root = root.rstrip("/") or "/"
            if root == "/" or home == root or home.startswith(root + "/"):
                return True
        return False

    non_broad_paths = [p for p in paths if not _is_broad(p)]
    if cmds and not args and not non_broad_paths:
        all_generic = all(c in GENERIC_VERBS for c in cmds)
        if all_generic:
            return 2, (
                f"triggers.commands contains only generic verbs "
                f"({', '.join(sorted(cmds))}) with no specific args or "
                f"domain-specific paths. Generic verbs provide no routing signal — "
                f"add at least one domain-specific command, arg, or path.\n"
                + TRIGGER_SCHEMA_HINT
            )
    # Broad-glob-only: the ONLY behavioral evidence is broad globs
    if not cmds and not args and paths and not non_broad_paths:
        return 2, (
            f"triggers.paths consists only of overly-broad glob(s) "
            f"({', '.join(paths)}) that match the entire home directory (no domain "
            f"signal). Use a specific path pattern (e.g. ~/.config/pipewire/**).\n"
            + TRIGGER_SCHEMA_HINT
        )
    return 0, ""


def _classify_target(target, memdir):
    """Classify the write target to determine which checks to apply.

    Returns one of:
      'box'           — target is None (default) or resolves under the box-brain store
      'project-store' — path contains a /.claude/projects/ segment followed by /memory/
      'repo-memory'   — path has a /memory/ component with a non-infra .md basename
      'other'         — none of the above

    Plan 01-03: extended 'other' into project-store / repo-memory branches (D-13/D-15).
    Pure string/Path logic on realpath-normalized target (T-01-07 path-escape prevention).
    """
    if target is None:
        return "box"
    # Lexically normalize both paths for prefix comparison
    try:
        norm_target = os.path.realpath(os.path.normpath(os.path.expanduser(str(target))))
    except (TypeError, ValueError):
        return "other"
    try:
        norm_memdir = os.path.realpath(os.path.normpath(str(memdir)))
    except (TypeError, ValueError):
        return "other"
    # Box-store: under memdir (or is memdir)
    if norm_target == norm_memdir or norm_target.startswith(norm_memdir + os.sep):
        return "box"
    # Project-store: path contains /.claude/projects/ ... /memory/
    # Use forward-slash check after splitting on os.sep to be portable
    parts = norm_target.replace("\\", "/").split("/")
    if ".claude" in parts:
        idx = parts.index(".claude")
        if (idx + 1 < len(parts) and parts[idx + 1] == "projects" and
                "memory" in parts[idx + 2:]):
            return "project-store"
    # Repo-memory: has a /memory/ path component with a non-infra .md basename
    basename = os.path.basename(norm_target)
    if (basename.endswith(".md") and
            not basename.startswith("_") and
            basename != "MEMORY.md" and
            "/memory/" in norm_target.replace("\\", "/")):
        return "repo-memory"
    return "other"


def _closest(tag, active, n=3):
    def score(a):
        if a.startswith(tag[:3]) or tag.startswith(a[:3]):
            common = len(set(tag) & set(a))
            return (1, common)
        return (0, len(set(tag) & set(a)))
    return [a for a, _ in sorted(((a, score(a)) for a in active),
                                 key=lambda x: x[1], reverse=True)[:n]]


def check_write(memdir, content, target=None):
    # Only apply structured checks when content has YAML frontmatter (---...---).
    # Content without frontmatter is not a memory file — fail open (existing behavior).
    has_frontmatter = bool(FRONTMATTER_RE.match(content))
    top, meta, _ = parse_frontmatter(content)
    mtags = meta.get("tags", []) or []
    # Classify FIRST (CR-01): the box taxonomy has no authority over foreign stores
    # (D-15), so legacy tag validation must not run for non-box targets.
    store_class = _classify_target(target, memdir)
    if store_class == "box":
        # --- Box-store branch ---
        tags = parse_tags_md(memdir / "_tags.md")
        active = set(tags["active"])
        if "tags" in top:                              # tags MUST nest under metadata: else they
            return 2, ("memory tags must be nested under 'metadata:' — found a top-level 'tags' "
                       "key; move it under the metadata: block so the tags are validated.")
        # triggers must also nest under metadata: (parity with top-level tags: rejection)
        if "triggers" in top:
            return 2, ("memory triggers must be nested under 'metadata:' — found a top-level "
                       "'triggers' key; move it under the metadata: block.\n"
                       + TRIGGER_SCHEMA_HINT)
        for t in mtags:
            if not TAG_RE.match(t):
                why = "malformed (must match ^[a-z0-9][a-z0-9-]{1,39}$)"
            elif t in tags["deny"] and t not in tags["overrides"]:
                why = "denylisted (too generic); use a specific tag or add a Policy override"
            elif t not in active:
                why = "not in _tags.md"
            else:
                continue
            close = _closest(t, active)
            hint = f"; closest active: {', '.join(close)}" if close else ""
            return 2, (f"memory tag '{t}' is {why}{hint}. "
                       f"Add it to _tags.md first if it is genuinely new.")
        # Structured checks only when content has frontmatter
        if not has_frontmatter:
            return 0, ""
        # D-09: triggers required for full Writes to the box store
        triggers = meta.get("triggers")
        if triggers is None:
            return 2, (
                "box-store memory write requires a 'triggers:' block under metadata: "
                "(D-09: triggers must be embedded at write time).\n"
                + TRIGGER_SCHEMA_HINT
            )
        rc, reason = _check_triggers(triggers)
        if rc:
            return rc, reason
        # D-11 Layer 2: dedup backstop — only for NEW files (target exists → overwrite/consolidation allowed)
        if target is not None and not Path(target).exists():
            desc = (top.get("description", "") or "").strip().strip('"').strip("'")
            candidates = dedup_candidates(memdir, mtags, desc, top_n=1)
            if candidates:
                best_score, best_mem = candidates[0]
                if best_score >= DEDUP_BACKSTOP_THRESHOLD:
                    existing_path = best_mem.get("path", "")
                    existing_id = best_mem.get("id", "")
                    return 2, (
                        f"memory appears to duplicate {existing_id!r}; "
                        f"consolidate into {existing_path} instead of creating a new file."
                    )
    elif store_class in ("project-store", "repo-memory"):
        # --- Non-box branch (D-15 placement gate) ---
        # Skip legacy tag validation and triggers requirement — no grammar authority
        # over foreign stores (CR-01: tag validation now runs ONLY in the box branch
        # above). ONLY run the placement gate: deny only when ALL grammar-known tags
        # carry placement='box'.
        if not has_frontmatter:
            return 0, ""
        grammar = parse_grammar_md(Path(memdir) / "_grammar.md")
        if grammar:
            # Collect tags that are known to the grammar
            known_tags = [t for t in mtags if t in grammar]
            if known_tags:
                # Placement gate: all known tags carry placement='box' → deny
                all_box = all(
                    grammar[t].get("placement", "either") == "box"
                    for t in known_tags
                )
                if all_box:
                    # Self-healing: tell the model where to write it
                    correct_store = str(resolve_memdir())
                    basename = os.path.basename(target) if target else "memory-filename.md"
                    return 2, (
                        f"this memory's tags ({', '.join(sorted(known_tags))}) are "
                        f"box-placement; write it to {correct_store}/{basename} instead. "
                        f"Box-general facts belong in the box-brain store "
                        f"(route by SUBJECT: box-general → {correct_store})."
                    )
        # Any other combination (unknown tags, mixed placement, project/either hints) → allow
    # 'other' targets: unchanged pass-through (no grammar authority, no gate)
    return 0, ""


# ================================================================ Phase 2: search engine
# ---------------------------------------------------------------- config (§17)
DEFAULT_CONFIG = {
    "schemaVersion": 1, "enabled": True, "mode": "advisory",
    "requiredMode": "strict-high-confidence", "maxResults": 3, "maxRequiredReads": 2,
    "maxDescriptionChars": 220, "maxBlockChars": 4000, "dedupeTtlSeconds": 900,
    "obligationTtlSeconds": 1800, "confidenceHighThreshold": 10,
    "confidenceMediumThreshold": 6, "requireAllRequiredReads": False, "debug": False,
}


def load_config(memdir):
    cfg = dict(DEFAULT_CONFIG)
    p = memdir / "_memory_surface_config.json"
    if p.exists():
        try:
            user = json.loads(p.read_text())
            if isinstance(user, dict):
                cfg.update(user)
        except (json.JSONDecodeError, OSError):
            pass                                       # malformed config -> safe defaults
    return cfg


# ---------------------------------------------------------------- token extraction (§11)
GENERIC_BASH = {"ls", "pwd", "cd", "cat", "sed", "awk", "grep", "rg",
                "find", "head", "tail", "wc", "jq"}
GENERIC_TWO = {"git status", "git diff"}
# Content-light subcommand verbs (service/pkg managers): never worth the one strong-argument
# slot — `systemctl restart pipewire` must yield `pipewire`, not `restart`.
GENERIC_VERBS = {"restart", "start", "stop", "status", "enable", "disable", "reload",
                 "list", "show", "info", "help", "version", "get", "set",
                 "add", "install", "remove", "update", "upgrade"}
INSTALLERS = {"pacman", "paru", "yay", "pip", "pip3", "npm", "pnpm", "yarn", "cargo", "apt"}
UNIT_RE = re.compile(r"\.(service|socket|timer|target|mount|path|scope)$")
_ENVVAR_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")    # leading VAR=val env assignment
_PRIVILEGE = {"sudo", "doas", "pkexec"}
_RUNNER_VALUE_FLAGS = {"-u", "-g", "--user", "--group", "-p", "-C", "-r", "-t", "-h"}


def _pkgname(a):
    return re.split(r"[=<>@~!]", a, maxsplit=1)[0]      # strip a version specifier (nvidia=550.1)


def _norm(s):
    s = (s or "").strip().lower()
    return s if TAG_RE.match(s) else None


def _expand(pat):
    if pat == "~":
        return str(Path.home())
    if pat.startswith("~/"):
        return str(Path.home()) + pat[1:]
    return pat


def _abspath(path, cwd):
    if path.startswith("~"):
        return _expand(path)
    if path.startswith("/"):
        return path
    return (cwd.rstrip("/") + "/" + path) if cwd else path


def path_tag_hits(abspath, path_tags):
    """(tags, strength) for path-tag rules matching abspath. fnmatch.fnmatchcase; recursive
    ** only as a trailing /** suffix (§7)."""
    hits = []
    for (pat, tags, strength, _) in path_tags:
        p = _expand(pat)
        if p.endswith("/**"):
            prefix = p[:-3]
            if abspath == prefix or abspath.startswith(prefix + "/"):
                hits.append((tags, strength))
        elif "**" in p:
            continue                                   # ** is sanctioned ONLY as a trailing /** (§7)
        elif fnmatch.fnmatchcase(abspath, p):
            hits.append((tags, strength))
    return hits


def extract_tokens(event, active, aliases, path_tags, memdir):
    """Per-tool evidence extraction (§11). Returns {tokens, pathRuleTags, paths}: tokens is a
    list of {value, kind, strength}; pathRuleTags is the set of tags emitted by matched path
    rules; paths is the list of canonicalized absolute paths used for byPath lookup in search()."""
    tool = event.get("tool_name", "") or ""
    ti = event.get("tool_input", {}) or {}
    cwd = event.get("cwd", "") or ""
    seen, tokens, path_rule_tags = set(), [], set()
    abs_paths = []   # collect canonicalized abspaths for byPath lookup in search()

    def add(value, kind, strength):
        v = _norm(value)
        if v and (v, kind) not in seen:
            seen.add((v, kind))
            tokens.append({"value": v, "kind": kind, "strength": strength})

    def add_path(raw):
        ap = _abspath(raw, cwd)
        if ap not in abs_paths:          # collect unique abspaths
            abs_paths.append(ap)
        for tags, _ in path_tag_hits(ap, path_tags):
            path_rule_tags.update(tags)
        base = ap.rsplit("/", 1)[-1]
        stem = base.rsplit(".", 1)[0] if "." in base[1:] else base   # keep leading-dot names (.bashrc)
        add(stem.lstrip("."), "path", "weak")
        for comp in ap.split("/"):
            add(comp.lstrip("."), "path", "weak")

    if tool == "Bash":
        # \n is a command separator in shell exactly like ';' — multiline Bash is the
        # norm in Claude Code, so without it the 2nd..Nth commands' basenames would be
        # swallowed as "arguments" of the first line's command (WR-03).
        for seg in re.split(r"\s*(?:;|&&|\|\||\||\n)\s*", ti.get("command", "") or ""):
            words = [w.strip("\"'") for w in seg.split()]           # strip surrounding quotes
            saw_runner = False                                     # drop privilege/env runner + its flags
            while words:
                w = words[0]
                if w in _PRIVILEGE or w == "env":
                    words, saw_runner = words[1:], True
                elif _ENVVAR_RE.match(w):
                    words = words[1:]                              # VAR=val (with or without a runner)
                elif saw_runner and w in _RUNNER_VALUE_FLAGS:
                    words = words[2:]                              # runner flag + value (sudo -u bob)
                elif saw_runner and w.startswith("-"):
                    words = words[1:]                              # valueless runner flag (sudo -i)
                else:
                    break
            if not words:
                continue
            base = words[0].rsplit("/", 1)[-1]
            is_generic = base in GENERIC_BASH or " ".join(words[:2]) in GENERIC_TWO
            installer = base in INSTALLERS
            if not is_generic:
                add(base, "command", "weak")
            for ptags, _ in path_tag_hits(base, path_tags):        # slash-free patterns are
                path_rule_tags.update(ptags)                       # command-basename rules (§7)
            args = [w for w in words[1:] if not w.startswith("-")]
            if not is_generic and not installer:
                for a in args:                                     # first content-bearing arg only;
                    if a.lower() in GENERIC_VERBS:                 # generic/installer first-arg isn't strong
                        continue
                    add(a, "argument", "strong")
                    break
            if not is_generic:
                for a in args:                                     # any arg that IS a known tag/alias
                    v = a.strip().lower()                          # is strong evidence wherever it sits
                    if v in active or v in aliases:
                        add(v, "argument", "strong")
            if installer:
                pkgs = args[1:] if (args and args[0] in ("install", "add", "i", "remove", "rm")) else args
                for a in pkgs:
                    add(_pkgname(a), "package", "weak")            # version specifier stripped
            for w in words:
                if UNIT_RE.search(w):
                    add(UNIT_RE.sub("", w.rsplit("/", 1)[-1]), "unit", "strong")
                if w.startswith("/") or w.startswith("~/"):
                    add_path(w)
    elif tool == "Read":
        p = ti.get("file_path") or ti.get("path") or ""
        if p:
            add_path(p)
    elif tool in ("Edit", "Write", "MultiEdit"):
        p = ti.get("file_path") or ti.get("path") or ""
        ap = _abspath(p, cwd) if p else ""
        if ap and not (ap == str(memdir) or ap.startswith(str(memdir) + "/")):
            add_path(p)                                # memory writes route to write hooks, not recall
    elif tool == "WebSearch":
        # findall (not \W+ split) so hyphenated tags like 'plasma-compositor' survive intact
        for w in re.findall(r"[a-z0-9][a-z0-9-]*", (ti.get("query", "") or "").lower()):
            if w in active or w in aliases:
                add(w, "tag", "strong")
    elif tool == "WebFetch":
        for w in re.findall(r"[a-z0-9][a-z0-9-]*", (ti.get("url", "") or "").lower()):
            if w in active or w in aliases:            # host + path tokens; known tags/aliases only
                add(w, "tag", "strong")
    elif tool.startswith("mcp__") and "context7" in tool:
        for key in ("libraryName", "context7CompatibleLibraryID", "libraryId", "query"):
            val = ti.get(key)
            if val:
                for w in re.findall(r"[a-z0-9][a-z0-9-]*", str(val).lower()):
                    if w in active or w in aliases:
                        add(w, "tag", "strong")        # a library that IS a known tag = strong signal
                    else:
                        add(w, "package", "weak")
    return {"tokens": tokens, "pathRuleTags": path_rule_tags, "paths": abs_paths}


# ---------------------------------------------------------------- queryHash (§15)
def query_hash(tool_name, canonical_tags, strong_tokens):
    payload = "{}\0{}\0{}".format(tool_name, ",".join(sorted(canonical_tags)),
                                  ",".join(sorted(strong_tokens)))
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- ranking (§12)
TYPE_PRIORITY = {"feedback": 0, "method": 1, "project": 2, "reference": 3, "todo": 4}


def _type_boost(t):
    return 1.0 if t in ("feedback", "method") else (0.5 if t == "project" else 0.0)


def _is_stale(last_reviewed, now):
    if not last_reviewed:
        return False
    try:
        return (now - datetime.date.fromisoformat(last_reviewed[:10])).days > 180
    except ValueError:
        return False


# ---------------------------------------------------------------- surface block (§16)
def _esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _trunc_escaped(s, n):
    """Escape first, THEN truncate to <= n chars without splitting an &entity; (§16 ordering)."""
    e = _esc(s)
    if len(e) <= n:
        return e
    cut = e[:n - 1]
    amp = cut.rfind("&")
    if amp != -1 and ";" not in cut[amp:]:             # don't cut a half-written entity
        cut = cut[:amp]
    return cut.rstrip() + "…"


def surface_text(query_id, mode, confidence, results, cfg):
    maxd = cfg.get("maxDescriptionChars", 220)
    out = [f'<memory-recall query-id="{_esc(query_id)}" mode="{_esc(mode)}" '
           f'confidence="{_esc(confidence)}">', "Possible memory match for this tool call.", ""]
    for i, r in enumerate(results, 1):
        # Plan 02-02: render evidence tuples when present (D-26 _render_tuples path);
        # fall back to legacy 'matched {tags}' format for pre-flip results without tuples.
        if r.get("evidenceTuples"):
            why = _render_tuples(r["evidenceTuples"])
        else:
            why = f"matched {_esc(', '.join(r['matchedTags']))}"
        out += [f"{i}. {_esc(r['file'])}", f"   path: {_esc(r['path'])}",
                f"   why: {why}",
                f"   note: {_trunc_escaped(r['description'], maxd)}"]
    out.append("</memory-recall>")
    block = "\n".join(out)
    maxb = cfg.get("maxBlockChars", 4000)
    return block if len(block) <= maxb else block[:maxb - 14].rstrip() + "\n…(truncated)"


# ---------------------------------------------------------------- search (§10)
def _neg_date(s):
    try:
        return -datetime.date.fromisoformat(s[:10]).toordinal()
    except (ValueError, TypeError):
        return 0


def _load_catalog(memdir):
    # Missing/corrupt catalog -> fail CLOSED (None): search surfaces nothing rather than calling
    # rebuild() here, which would read memory frontmatter during a search (§19 / bodies-never-loaded).
    # Catalog freshness is the PostToolUse catalog-refresh hook's job, not search's.
    p = memdir / "_memory_catalog.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def _dedup_words(text):
    """Lowercased whitespace-split bag of words with DEDUP_STOPWORDS removed (WR-02)."""
    return Counter(w for w in (text or "").lower().split() if w not in DEDUP_STOPWORDS)


def dedup_candidates(memdir, proposed_tags, proposed_desc, top_n=5):
    """Return top-N most-similar existing memories by tag overlap + bag-of-words cosine (D-11 L1).

    Score = 0.6 * tag_overlap + 0.4 * cosine_bow, where:
      tag_overlap = Jaccard |proposed ∩ mem.tags| / max(|proposed ∪ mem.tags|, 1)
                    (symmetric — WR-02: the old asymmetric |∩|/len(proposed) let a
                    single shared tag saturate the full 0.6 against ANY existing memory)
      cosine_bow  = bag-of-words cosine on lowercased whitespace-split descriptions
                    with DEDUP_STOPWORDS removed (Counter intersection; zero
                    denominator → 0.0)

    Returns list of (score, mem) pairs sorted descending. Empty list on missing/corrupt catalog.
    Stdlib only (D-11, RESEARCH.md Pattern 4).
    """
    catalog = _load_catalog(memdir)
    if catalog is None:
        return []
    prop_tags = set(proposed_tags or [])
    prop_words = _dedup_words(proposed_desc)
    results = []
    for mem in catalog.get("memories", []):
        mem_tags = set(mem.get("tags", []) or [])
        tag_overlap = len(prop_tags & mem_tags) / max(len(prop_tags | mem_tags), 1)
        mem_words = _dedup_words(mem.get("description", ""))
        # Bag-of-words cosine: intersection-sum / (L2-norm_prop * L2-norm_mem)
        intersection = sum((prop_words & mem_words).values())
        denom_sq = (sum(v * v for v in prop_words.values()) *
                    sum(v * v for v in mem_words.values()))
        cos = intersection / (denom_sq ** 0.5) if denom_sq else 0.0
        score = 0.6 * tag_overlap + 0.4 * cos
        results.append((score, mem))
    results.sort(key=lambda x: x[0], reverse=True)
    return results[:top_n]


def _response_mode(cfg):
    # §10/§16 response-mode vocabulary is advisory|required, NOT the raw config mode string.
    return "required" if cfg.get("mode") == "strict-high-confidence" else "advisory"


def _empty_response(mode):
    return {"schemaVersion": 1, "queryId": "memq_00000000", "mode": mode, "confidence": "low",
            "tokens": [], "canonicalTags": [], "results": [], "surfaceText": ""}


# Tier weights for evidence scoring (D-27). Module constant; can be overridden via
# optional 'tierWeights' key in _memory_surface_config.json.
TIER_WEIGHTS = {"strong": 10, "medium": 6, "weak": 3}


def _match_paths(abspaths, by_path):
    """Return list of (memory_id, trigger_type, matched_value, entry) for every byPath hit.

    Applies path_tag_hits()-parity semantics (§7):
    - /** trailing suffix: prefix match (abspath == prefix OR starts with prefix + '/')
    - mid-** patterns: IGNORED (§7 sanctioned only as trailing /**)
    - exact fnmatchcase otherwise

    Patterns stored in by_path keys are already expanded (~ → home) by the compiler.
    The entry's 'pattern' field preserves the original form.
    """
    hits = []
    for stored_key, entries in by_path.items():
        # Apply expansion to stored key (already expanded by compiler, but belt-and-suspenders)
        p = _expand(stored_key)
        matched = False
        if p.endswith("/**"):
            prefix = p[:-3]
            for ap in abspaths:
                if ap == prefix or ap.startswith(prefix + "/"):
                    matched = True
                    break
        elif "**" in p:
            continue   # mid-** is not supported (§7)
        else:
            for ap in abspaths:
                if fnmatch.fnmatchcase(ap, p):
                    matched = True
                    break
        if matched:
            for entry in entries:
                hits.append((entry, abspaths))
    return hits


def _score_tuples(tuples, mem, cfg, now, tier_weights):
    """Compute score from firing tuples + type boost - stale/decline penalties (D-27).

    score = sum(tier_weights[tier] for distinct (tag, trigger_type) tuples)
          + _type_boost(mem.type)
          - 5 * stale
          - 2 * min(declineCount, 3)

    Tuples are already deduped by (tag, trigger_type) before this call.
    """
    score = 0.0
    for tup in tuples:
        tt = tup.get("trigger_type", "weak")
        # Map trigger_type to tier: command/path → strong; arg → medium; synonym → weak
        if tt in ("command", "path", "unit", "tag"):
            tier = "strong"
        elif tt in ("arg",):
            tier = "medium"
        else:
            tier = "weak"
        score += tier_weights.get(tier, tier_weights["weak"])
    score += _type_boost(mem.get("type", ""))
    stale = 1 if _is_stale(mem.get("lastReviewed", ""), now) else 0
    score -= 5 * stale
    decline = min(int(mem.get("declineCount", 0) or 0), 3)
    score -= 2 * decline
    return score


def _confidence_new(score, cfg):
    """Map score to confidence label using existing load_config threshold keys (D-27)."""
    if score >= cfg.get("confidenceHighThreshold", 10):
        return "high"
    if score >= cfg.get("confidenceMediumThreshold", 6):
        return "medium"
    return "low"


def _render_tuples(tuples):
    """Render evidence tuples as '{tag} ← {trigger_type}:{matched_value}' joined by '; '.

    The ← marker is the probe assertion token (D-32). Each field is _esc()-escaped.
    Capped at 3 tuples per memory to keep the surface block compact.
    """
    parts = []
    for t in tuples[:3]:
        parts.append(
            f"{_esc(t['tag'])} ← {_esc(t['trigger_type'])}:{_esc(t['matched_value'])}"
        )
    return "; ".join(parts) if parts else "matched (no tuple)"


def _meets_min_candidate_new(tuples, tier_weights):
    """Surface gate: a memory surfaces only if ≥1 strong-tier tuple OR ≥2 tuples total.

    A single synonym-only (weak) match violates both conditions → SILENT (CORE-06/D-27).
    """
    if len(tuples) >= 2:
        return True
    if len(tuples) == 1:
        tt = tuples[0].get("trigger_type", "weak")
        tier = "strong" if tt in ("command", "path", "unit", "tag") else (
            "medium" if tt == "arg" else "weak"
        )
        return tier == "strong"
    return False


def search(memdir, event, now=None):
    """Trigger-index matcher (Plan 02-02/02-04, D-30 flip completed).

    Reads ONLY the precomputed catalog (triggerIndex + recallVocab + tagToMemoryIds).
    NEVER calls parse_tags_md / parse_tag_links — those are write-path only after the flip.
    NEVER calls rebuild() — missing/corrupt catalog returns _empty_response() (fail-closed).
    """
    # ---- Guard prologue (copy verbatim from legacy search, D-28) ----
    now = now or datetime.date.today()
    cfg = load_config(memdir)
    rmode = _response_mode(cfg)
    if not cfg.get("enabled", True) or cfg.get("mode") == "disabled" \
            or (memdir / ".surface-disabled").exists():
        return _empty_response(rmode)
    catalog = _load_catalog(memdir)
    if catalog is None:                  # missing/corrupt catalog -> fail closed (never rebuild)
        return _empty_response(rmode)

    # ---- Read routing tables from catalog (never from _tags.md/_tag_links.md) ----
    vocab = catalog.get("recallVocab", {})
    active = set(vocab.get("active", []))
    aliases = vocab.get("aliases", {})
    index = catalog.get("triggerIndex", {})
    tag_to_mids = catalog.get("tagToMemoryIds", {})

    # ---- Merge optional tierWeights config override ----
    tw = dict(TIER_WEIGHTS)
    config_tw = cfg.get("tierWeights")
    if isinstance(config_tw, dict):
        tw.update(config_tw)

    # ---- Token extraction (empty path_tags — path routing now via byPath in matcher) ----
    ext = extract_tokens(event, active, aliases, [], memdir)
    tokens = ext["tokens"]
    abs_paths = ext.get("paths", [])

    # ---- One-pass matcher over both levels (D-25) ----
    # hits[memory_id] = list of {tag, trigger_type, matched_value} tuples
    hits = {}

    def _add_hit(mid, tag, trigger_type, matched_value):
        key = (tag, trigger_type)
        existing = hits.setdefault(mid, [])
        # Dedup by (tag, trigger_type) per memory
        if not any(t["tag"] == tag and t["trigger_type"] == trigger_type for t in existing):
            existing.append({"tag": tag, "trigger_type": trigger_type,
                             "matched_value": matched_value})

    by_command = index.get("byCommand", {})
    by_arg = index.get("byArg", {})
    by_synonym = index.get("bySynonym", {})
    by_path = index.get("byPath", {})
    by_memory_id = index.get("byMemoryId", {})

    for tok in tokens:
        v = tok["value"]
        kind = tok["kind"]

        # command/unit → byCommand (strong)
        if kind in ("command", "unit"):
            for entry in by_command.get(v, []):
                _mid = entry["id"]
                _tag = entry["id"]  # tag field = id (memory id or grammar tag id)
                if entry.get("source") == "tag":
                    # Tag-source: expand to all memories with this grammar tag
                    _tag = entry["id"]  # grammar tag name
                    for mid in tag_to_mids.get(_tag, []):
                        _add_hit(mid, _tag, "command", v)
                else:
                    # memory/memory-derived source: direct route
                    _add_hit(_mid, _mid, "command", v)
            # Also bySynonym for units (plan spec)
            if kind == "unit":
                for entry in by_synonym.get(v, []):
                    _mid = entry["id"]
                    if entry.get("source") == "tag":
                        _tag = entry["id"]
                        for mid in tag_to_mids.get(_tag, []):
                            _add_hit(mid, _tag, "synonym", v)
                    else:
                        _add_hit(_mid, _mid, "synonym", v)

        # argument → grammar tag-name match → strong; byArg → medium; bySynonym → weak
        elif kind == "argument":
            # Strong: value is a grammar tag name
            if v in active:
                for mid in tag_to_mids.get(v, []):
                    _add_hit(mid, v, "tag", v)
            # Medium: byArg hit
            for entry in by_arg.get(v, []):
                _mid = entry["id"]
                if entry.get("source") == "tag":
                    _tag = entry["id"]
                    for mid in tag_to_mids.get(_tag, []):
                        _add_hit(mid, _tag, "arg", v)
                else:
                    _add_hit(_mid, _mid, "arg", v)
            # Weak: bySynonym hit
            for entry in by_synonym.get(v, []):
                _mid = entry["id"]
                if entry.get("source") == "tag":
                    _tag = entry["id"]
                    for mid in tag_to_mids.get(_tag, []):
                        _add_hit(mid, _tag, "synonym", v)
                else:
                    _add_hit(_mid, _mid, "synonym", v)

        # tag (WebSearch/WebFetch/context7) → strong tag-name match; bySynonym → weak
        elif kind == "tag":
            if v in active:
                for mid in tag_to_mids.get(v, []):
                    _add_hit(mid, v, "tag", v)
            elif v in aliases:
                canon = aliases[v]
                for mid in tag_to_mids.get(canon, []):
                    _add_hit(mid, canon, "synonym", v)
            # bySynonym for tag-kind tokens
            for entry in by_synonym.get(v, []):
                _mid = entry["id"]
                if entry.get("source") == "tag":
                    _tag = entry["id"]
                    for mid in tag_to_mids.get(_tag, []):
                        _add_hit(mid, _tag, "synonym", v)
                else:
                    _add_hit(_mid, _mid, "synonym", v)

        # package/path-component → byCommand/bySynonym → weak
        elif kind in ("package", "path"):
            for entry in by_command.get(v, []):
                _mid = entry["id"]
                if entry.get("source") == "tag":
                    _tag = entry["id"]
                    for mid in tag_to_mids.get(_tag, []):
                        _add_hit(mid, _tag, "synonym", v)
                else:
                    _add_hit(_mid, _mid, "synonym", v)
            for entry in by_synonym.get(v, []):
                _mid = entry["id"]
                if entry.get("source") == "tag":
                    _tag = entry["id"]
                    for mid in tag_to_mids.get(_tag, []):
                        _add_hit(mid, _tag, "synonym", v)
                else:
                    _add_hit(_mid, _mid, "synonym", v)

    # ---- Path routing: byPath via /** semantics (strong tier) ----
    for stored_key, entries in by_path.items():
        p = _expand(stored_key)
        path_matched = None
        if p.endswith("/**"):
            prefix = p[:-3]
            for ap in abs_paths:
                if ap == prefix or ap.startswith(prefix + "/"):
                    path_matched = ap
                    break
        elif "**" in p:
            continue   # mid-** not supported (§7)
        else:
            for ap in abs_paths:
                if fnmatch.fnmatchcase(ap, p):
                    path_matched = ap
                    break
        if path_matched is not None:
            for entry in entries:
                _mid = entry["id"]
                if entry.get("source") == "tag":
                    _tag = entry["id"]
                    for mid in tag_to_mids.get(_tag, []):
                        _add_hit(mid, _tag, "path", path_matched)
                else:
                    _add_hit(_mid, _mid, "path", path_matched)

    # ---- Score, gate, rank ----
    all_mems = {m["id"]: m for m in catalog.get("memories", [])}
    scored = []
    for mid, tuples in hits.items():
        if mid not in all_mems:
            continue
        mem = all_mems[mid]
        if not _meets_min_candidate_new(tuples, tw):
            continue
        score = _score_tuples(tuples, mem, cfg, now, tw)
        scored.append((score, tuples, mem))

    scored.sort(key=lambda x: (
        -x[0],
        TYPE_PRIORITY.get(x[2].get("type", ""), 9),
        _neg_date(x[2].get("lastReviewed", "")),
        x[2].get("file", "")
    ))

    top = scored[:cfg.get("maxResults", 3)]
    confidence = _confidence_new(top[0][0], cfg) if top else "low"
    strict = cfg.get("mode") == "strict-high-confidence"

    # ---- Build canonical tags + query hash ----
    canon_tags = sorted({aliases.get(t["value"], t["value"]) for t in tokens
                         if aliases.get(t["value"], t["value"]) in active}
                        | {tup["tag"] for _, tuples, _ in top
                           for tup in tuples if tup["tag"] in active})
    strong_tokens = sorted({t["value"] for t in tokens if t["strength"] == "strong"})
    qhash = query_hash(event.get("tool_name", "") or "", canon_tags, strong_tokens)
    qid = "memq_" + qhash.split(":")[1][:12]

    # ---- Assemble results with evidenceTuples ----
    results = []
    for score, tuples, mem in top:
        results.append({
            "id": mem["id"], "path": mem["path"], "file": mem["file"], "name": mem["name"],
            "description": mem["description"], "tags": mem["tags"],
            "matchedTags": sorted({tup["tag"] for tup in tuples}),
            "score": score, "mustRead": confidence == "high" and strict,
            "evidenceTuples": tuples,
        })

    return {"schemaVersion": 1, "queryId": qid, "mode": rmode, "confidence": confidence,
            "tokens": tokens, "canonicalTags": canon_tags, "results": results,
            "surfaceText": surface_text(qid, rmode, confidence, results, cfg) if results else ""}


# ---------------------------------------------------------------- taxonomy mutators
def _sanitize(s):
    """Collapse newlines/backticks so a free-text reason/description can't smuggle a new
    taxonomy line (`- \\`x\\` = \\`y\\``) or active-tag line past validation."""
    return re.sub(r"[\r\n`]+", " ", (s or "")).strip()


def _drop_pair_lines(text, a, b, op):
    """Remove any '- `x` <op> `y`' line whose backtick pair equals {a, b} (op is '=' or '!=')."""
    pat = re.compile(r"^- `([a-z0-9-]+)` " + re.escape(op) + r" `([a-z0-9-]+)`")
    return "\n".join(ln for ln in text.split("\n")
                     if not ((m := pat.match(ln)) and {m.group(1), m.group(2)} == {a, b}))


def _insert_under_heading(text, heading, line):
    """Insert `line` as the last entry under '## {heading}', creating the heading at EOF if
    absent. Returns the new text (caller writes atomically)."""
    lines = text.split("\n")
    target = "## " + heading
    hi = next((i for i, ln in enumerate(lines) if ln.strip() == target), None)
    if hi is None:
        return text.rstrip("\n") + "\n\n" + target + "\n" + line + "\n"
    last = hi
    j = hi + 1
    while j < len(lines) and not lines[j].strip().startswith("## "):
        if lines[j].strip():
            last = j
        j += 1
    lines.insert(last + 1, line)
    return "\n".join(lines)


def _mutate_then_validate(memdir, path, old_text, new_text):
    """Write new_text atomically; roll back only if it introduces a NEW validation error
    (pre-existing unrelated errors must not block an edit). Rebuild on success, and fail closed
    (rollback) if rebuild raises so the taxonomy and catalog never diverge."""
    pre = validate(memdir)                             # list — subtract by MULTIPLICITY, not set
    write_atomic(path, new_text if new_text.endswith("\n") else new_text + "\n")
    new_errs = list(validate(memdir))
    for e in pre:                                      # a duplicate new error (same string) must NOT be masked
        if e in new_errs:
            new_errs.remove(e)
    if new_errs:
        write_atomic(path, old_text)
        rc = 3 if any(("both a synonym and a distinction" in e
                       or "multiple synonym sets" in e) for e in new_errs) else 2   # §10: 3 = graph
        return rc, "validation failed (rolled back): " + "; ".join(new_errs)
    try:
        rebuild(memdir)
    except Exception as e:                             # taxonomy already written -> roll back
        write_atomic(path, old_text)
        return 2, f"rebuild failed after mutation (rolled back): {e}"
    return 0, ""


def add_tag(memdir, tag, description="", facet="tool"):
    if not TAG_RE.match(tag):
        return 2, f"tag '{tag}' is malformed"
    if facet not in FACET_HEADS:
        return 2, f"facet must be one of {FACET_HEADS}"
    desc = _sanitize(description)
    if not (6 <= len(desc.split()) <= 32):             # §6/§18: substantive 6-32-word gloss
        return 2, f"tag description must be 6-32 words (got {len(desc.split())})"
    tags = parse_tags_md(memdir / "_tags.md")
    if tag in tags["active"]:
        return 0, f"tag '{tag}' already active"
    if tag in tags["deny"] and tag not in tags["overrides"]:
        return 2, f"tag '{tag}' is denylisted; add a Policy override first"
    path = memdir / "_tags.md"
    old = path.read_text() if path.exists() else "# tags\n"
    new = _insert_under_heading(old, facet, f"- {tag} — {desc}")
    rc, msg = _mutate_then_validate(memdir, path, old, new)
    return rc, msg or f"added tag '{tag}' under '{facet}'"


def link(memdir, a, b, reason=""):
    for t in (a, b):
        if not TAG_RE.match(t):
            return 2, f"tag '{t}' is malformed"
    path = memdir / "_tag_links.md"
    old = path.read_text() if path.exists() else "# tag links\n"
    r = _sanitize(reason)
    suffix = f" - {r}" if r else ""
    cleaned = _drop_pair_lines(old, a, b, "!=")        # §7: link removes any distinction between a,b
    new = _insert_under_heading(cleaned, "Synonyms", f"- `{a}` = `{b}`{suffix}")
    rc, msg = _mutate_then_validate(memdir, path, old, new)
    return rc, msg or f"linked `{a}` = `{b}`"


def unlink(memdir, a, b, distinguish=False, reason=""):
    for t in (a, b):
        if not TAG_RE.match(t):
            return 2, f"tag '{t}' is malformed"
    path = memdir / "_tag_links.md"
    old = path.read_text() if path.exists() else "# tag links\n"
    if distinguish:
        r = _sanitize(reason)
        suffix = f" - {r}" if r else ""
        cleaned = _drop_pair_lines(old, a, b, "=")     # §7: distinguishing removes any synonym
        new = _insert_under_heading(cleaned, "Distinctions", f"- `{a}` != `{b}`{suffix}")
    else:
        new = _drop_pair_lines(old, a, b, "=")         # drop the a=b / b=a synonym edge
    rc, msg = _mutate_then_validate(memdir, path, old, new)
    verb = "distinguished" if distinguish else "unlinked"
    return rc, msg or f"{verb} `{a}` / `{b}`"


def dismiss(query_id, reason):
    # Obligation state is Phase 4 (strict mode). In Phase 2 (advisory) there is no obligation
    # to dismiss; succeed and record intent. (No-op until strict mode ships.)
    return 0, f"dismiss noted (advisory; no obligation state in Phase 2): {query_id} — {reason}"


# ---------------------------------------------------------------- MEMORY.md router (§4)
ROUTER_TEMPLATE = """# Memory router

Project memories are surfaced by the tool-call memory recall hook.
Do not skim this directory by habit.

When a `<memory-recall>` block appears, use it as project context.
Read full memory files only when the surfaced summary is action-changing.

When writing memories, use tags from `_tags.md`; add a genuinely new tag there first.
"""

_MEM_LINK_RE = re.compile(
    r"^\s*(?:[-*+]|\d+\.)\s*(?:\[\[[^\]]+\]\]|\[.*\]\([^)]+\.md\))", re.IGNORECASE)


def validate_router(path, memdir=None):
    """Validate MEMORY.md as a capped router (§4). Returns (rc, messages): rc 0 ok (maybe a
    warning), rc 2 fail. Flags a line-per-memory index — >=10 memory links AND (when the store is
    known) at least half as many links as memory files — or >40 nonblank lines;
    MEMORY_SURFACE_ALLOW_LONG_INDEX=1 lifts the 40-line cap; >20 lines warns. Catches `[text](x.md)`,
    `[[wikilink]]`, and `-`/`*`/`+`/numbered bullets (case-insensitive)."""
    p = Path(path)
    if not p.exists():
        return 0, []
    nonblank = [ln for ln in p.read_text().split("\n") if ln.strip()]
    links = [ln for ln in nonblank if _MEM_LINK_RE.match(ln)]
    n_mem = sum(1 for _ in _memory_files(memdir)) if memdir else None
    msgs, rc = [], 0
    if len(links) >= 10 and (n_mem is None or len(links) >= 0.5 * n_mem):
        rc = 2
        msgs.append(f"line-per-memory index ({len(links)} memory links) — convert to a router")
    if len(nonblank) > 40 and os.environ.get("MEMORY_SURFACE_ALLOW_LONG_INDEX") != "1":
        rc = 2
        msgs.append(f"{len(nonblank)} nonblank lines > 40 (set MEMORY_SURFACE_ALLOW_LONG_INDEX=1 to allow)")
    elif len(nonblank) > 20:
        msgs.append(f"{len(nonblank)} nonblank lines > 20 — keep the router compact")
    return rc, msgs


# ---------------------------------------------------------------- write-context composite (Plan 01-03, D-08)

def _grammar_digest(entries):
    """Compact digest: one line per tag, format 'tag: gloss [placement]', sorted by tag name.

    Used as a budget-safe fallback when the full _grammar.md artifact would push the
    composite over WRITE_CONTEXT_BUDGET (D-08 component b digest path).
    """
    lines = []
    for tag in sorted(entries.keys()):
        entry = entries[tag]
        gloss = (entry.get("gloss") or "").strip()
        placement = entry.get("placement", "either")
        lines.append(f"{tag}: {gloss} [{placement}]")
    return "\n".join(lines)


def write_context(memdir, event, target=None):
    """Build the budget-allocated write-time composite for the memory-write-context.sh hook (D-08).

    Returns a plain-text string (possibly empty) for inclusion in additionalContext.
    ALWAYS returns str; NEVER raises (fail open — a context hook must never block).

    `target`, when given, is the hook-resolved absolute path of the write (WR-05,
    mirroring check-write --target): classification then uses the SAME path the hook
    detected instead of re-deriving the raw event path against the engine's own CWD.

    Composite order (D-08):
      (a) Fixed preamble + TRIGGER_SCHEMA_HINT (trigger schema + worked example)
      (b) Grammar vocabulary (full _grammar.md if budget allows, else _grammar_digest)
      (c) Top-5 dedup candidates (box-store targets only)
      (d) Placement guidance naming the box-store path

    Returns "" for non-memory events (no .md file_path, infra file, etc.).
    """
    try:
        return _write_context_impl(memdir, event, target)
    except Exception:
        return ""


def _write_context_impl(memdir, event, target=None):
    """Internal implementation — any exception propagates to write_context() which catches all."""
    ti = (event or {}).get("tool_input") or {}
    file_path = target or ti.get("file_path") or ti.get("path") or ""
    if not file_path:
        return ""
    # No explicit target (direct caller): anchor a relative event path to the event's
    # cwd, NOT the engine process's CWD (WR-05 — the two can differ arbitrarily).
    if not target and not os.path.isabs(os.path.expanduser(file_path)):
        cwd = (event or {}).get("cwd") or ""
        if cwd:
            file_path = os.path.join(cwd, file_path)
    # Only process .md files that are not infra files (_* or MEMORY.md)
    basename = os.path.basename(file_path)
    if not basename.endswith(".md"):
        return ""
    if basename.startswith("_") or basename == "MEMORY.md":
        return ""

    # Determine if this is a box-store write (for dedup candidates and placement guidance)
    store_class = _classify_target(file_path, memdir)

    parts = []

    # --- (a) Fixed preamble + TRIGGER_SCHEMA_HINT ---
    preamble = (
        "You are writing a memory file. A metadata.triggers block derived from the work "
        "just done is REQUIRED at save time (CORE-02). Dedup candidates and placement "
        "guidance follow. Consolidate into an existing file if any candidate overlaps.\n\n"
        "REQUIRED trigger schema:\n"
        + TRIGGER_SCHEMA_HINT
    )
    parts.append(preamble)

    # --- (b) Grammar vocabulary ---
    grammar_path = Path(memdir) / "_grammar.md"
    if grammar_path.exists():
        grammar_text = grammar_path.read_text()
        # Check if full grammar + current parts fits in budget
        running = sum(len(p) for p in parts)
        if running + len(grammar_text) + 100 <= WRITE_CONTEXT_BUDGET:
            parts.append("--- Grammar Vocabulary ---\n" + grammar_text)
        else:
            # Digest fallback: one line per tag
            entries = parse_grammar_md(grammar_path)
            if entries:
                digest = _grammar_digest(entries)
                parts.append("--- Grammar Vocabulary (digest) ---\n" + digest)

    # --- (c) Dedup candidates (box-store targets only) ---
    if store_class == "box":
        # Extract proposed tags and description from content for similarity scoring
        content = ti.get("content") or ""
        proposed_tags = []
        proposed_desc = ""
        if content:
            try:
                _top, _meta, _ = parse_frontmatter(content)
                proposed_tags = _meta.get("tags", []) or []
                proposed_desc = (_top.get("description", "") or "").strip().strip('"').strip("'")
            except Exception:
                pass
        candidates = dedup_candidates(memdir, proposed_tags, proposed_desc, top_n=5)
        # Relevance floor (WR-06): drop zero/near-zero-similarity memories — without
        # this, ANY box write (even one with no content/tags) rendered five arbitrary
        # memories as consolidation targets. Section is skipped entirely when empty.
        candidates = [(s, m) for s, m in candidates if s >= DEDUP_CANDIDATE_FLOOR]
        if candidates:
            cand_lines = [
                "--- Dedup Candidates ---",
                "If this memory overlaps one of these, WRITE INTO that existing file "
                "(consolidate) instead of creating a new one:",
            ]
            for score, mem in candidates:
                mem_id = mem.get("id", "")
                mem_desc = mem.get("description", "")
                mem_path = mem.get("path", "")
                cand_lines.append(f"- {mem_id} — {mem_desc} ({mem_path})")
            parts.append("\n".join(cand_lines))

    # --- (d) Placement guidance ---
    correct_store = str(resolve_memdir())
    placement_text = (
        "--- Placement Guidance ---\n"
        f"Route by SUBJECT: box-general facts (this box, tools, hardware) → box-brain store "
        f"({correct_store}); lab/project-specific → that project's memory/ directory.\n"
        f"Box-brain store: {correct_store}"
    )
    # Add warning if this is a non-box target with box-placement tags
    if store_class in ("project-store", "repo-memory"):
        content = ti.get("content") or ""
        if content:
            try:
                _, _meta, _ = parse_frontmatter(content)
                _tags = _meta.get("tags", []) or []
                grammar = parse_grammar_md(Path(memdir) / "_grammar.md")
                if grammar:
                    known_box_tags = [t for t in _tags if t in grammar and
                                      grammar[t].get("placement", "either") == "box"]
                    if known_box_tags:
                        placement_text += (
                            f"\nWARNING: tags {known_box_tags} have box placement — "
                            f"this memory belongs at {correct_store}"
                        )
            except Exception:
                pass
    parts.append(placement_text)

    # Assemble and enforce budget
    result = "\n\n".join(parts)
    if len(result) <= WRITE_CONTEXT_BUDGET:
        return result

    # Budget overflow: rebuild with digest (replace full grammar with digest)
    parts_trimmed = []
    # Always keep preamble (a)
    parts_trimmed.append(parts[0])

    # Try digest instead of full grammar
    grammar_path = Path(memdir) / "_grammar.md"
    if grammar_path.exists():
        entries = parse_grammar_md(grammar_path)
        if entries:
            digest = _grammar_digest(entries)
            parts_trimmed.append("--- Grammar Vocabulary (digest) ---\n" + digest)

    # Re-add candidates (c) if space allows
    cand_section = next((p for p in parts if p.startswith("--- Dedup Candidates ---")), None)
    if cand_section:
        parts_trimmed.append(cand_section)

    # Always add placement guidance (d)
    parts_trimmed.append(placement_text)

    result = "\n\n".join(parts_trimmed)
    if len(result) <= WRITE_CONTEXT_BUDGET:
        return result

    # Still over budget: truncate candidate list then digest tail
    result = result[:WRITE_CONTEXT_BUDGET]
    return result


# ---------------------------------------------------------------- CLI
def _arg(flag, default=None):
    return sys.argv[sys.argv.index(flag) + 1] if flag in sys.argv else default


VALUE_FLAGS = {"--memory-dir", "--reason", "--description", "--event",
               "--content-file", "--query-id", "--facet", "--target"}


def _positionals():
    out, i, argv = [], 2, sys.argv
    while i < len(argv):
        a = argv[i]
        if a in VALUE_FLAGS:
            i += 2
        elif a.startswith("--"):
            i += 1
        else:
            out.append(a)
            i += 1
    return out


def _err(msg):
    print(msg, file=sys.stderr)
    return 2


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    memdir = resolve_memdir(_arg("--memory-dir"))
    if not memdir.is_dir():
        return 0                                       # fail open: no store, nothing to do
    if cmd == "validate":
        errs = validate(memdir)
        for e in errs:
            print(e, file=sys.stderr)
        return 0 if not errs else 2
    if cmd == "validate-grammar":
        errs = validate_grammar(memdir)
        for e in errs:
            print(e, file=sys.stderr)
        return 0 if not errs else 2
    if cmd == "rebuild":
        cat = rebuild(memdir)
        if cat["invalidMemories"]:
            print(json.dumps({"invalidMemories": cat["invalidMemories"]}), file=sys.stderr)
        return 0
    if cmd == "check-write":
        cf = _arg("--content-file")
        content = Path(cf).read_text() if cf else sys.stdin.read()
        rc, msg = check_write(memdir, content, target=_arg("--target"))
        if rc:
            print(msg)
        return rc
    if cmd == "search":
        ef = _arg("--event")
        event = json.loads((Path(ef).read_text() if ef else sys.stdin.read()) or "{}")
        print(json.dumps(search(memdir, event), ensure_ascii=False))
        return 0
    if cmd == "write-context":
        # D-08: build the budget-allocated composite for memory-write-context.sh.
        # Reads event JSON from stdin or --event FILE; prints composite to stdout.
        # --target (WR-05): hook-resolved absolute path, mirroring check-write.
        # ALWAYS returns 0, even for empty output (context hook must never block).
        ef = _arg("--event")
        try:
            raw = (Path(ef).read_text() if ef else sys.stdin.read()) or "{}"
            event = json.loads(raw)
        except (json.JSONDecodeError, OSError, TypeError):
            event = {}
        composite = write_context(memdir, event, target=_arg("--target"))
        if composite:
            sys.stdout.write(composite)
        return 0
    if cmd == "router-check":
        rc, msgs = validate_router(memdir / "MEMORY.md", memdir)
        for m in msgs:
            print(m, file=(sys.stderr if rc else sys.stdout))
        return rc
    if cmd == "router-template":
        sys.stdout.write(ROUTER_TEMPLATE)
        return 0
    if cmd == "maintenance":
        try:
            # --recheck-threshold (WR-02): hook-spawned passes re-verify the D-40
            # trigger under the lock so a concurrent/duplicate spawn no-ops.
            maintenance(memdir, recheck="--recheck-threshold" in sys.argv)
        except Exception:  # noqa: BLE001
            pass
        return 0
    if cmd == "maintenance-shadow":
        try:
            result = maintenance(memdir, shadow=True)
            print(json.dumps(result))
        except Exception:  # noqa: BLE001
            print("{}")
        return 0
    if cmd == "seats":
        try:
            result = seats(memdir)
            demote_count = len(result.get("demote", []))
            promote_count = len(result.get("promote", []))
            reason = result.get("reason")
            if reason == "no-probe-results":
                print("seats: no probe results (run seat_probes.py first)")
            elif reason and "window unmet" in reason:
                print(f"seats: {reason}")
            elif reason:
                print(f"seats: {reason}")
            else:
                print(f"seats: {demote_count} demote, {promote_count} promote proposals")
        except Exception:  # noqa: BLE001
            print("seats: error (fail-open)")
        return 0
    if cmd in ("link", "unlink", "add-tag", "dismiss"):
        pos = _positionals()
        if cmd == "link":
            if len(pos) < 2:
                return _err("usage: link <a> <b> [--reason R]")
            rc, msg = link(memdir, pos[0], pos[1], _arg("--reason", ""))
        elif cmd == "unlink":
            if len(pos) < 2:
                return _err("usage: unlink <a> <b> [--distinguish] [--reason R]")
            rc, msg = unlink(memdir, pos[0], pos[1], "--distinguish" in sys.argv, _arg("--reason", ""))
        elif cmd == "add-tag":
            if len(pos) < 1:
                return _err("usage: add-tag <tag> [--description D] [--facet domain|tool|pattern]")
            rc, msg = add_tag(memdir, pos[0], _arg("--description", ""), _arg("--facet", "tool"))
        else:
            rc, msg = dismiss(_arg("--query-id", ""), _arg("--reason", ""))
        print(msg, file=(sys.stderr if rc else sys.stdout))
        return rc
    print(f"unknown command: {cmd!r}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
