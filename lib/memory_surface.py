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
[[fumble-restored-tool-read-ok-but-write-corrupts-on-format-drift]]) and additionally read the
block-list `tags:` form that _review_game.py's line parser silently drops.
"""
import datetime
import hashlib
import json
import os
import re
import sys
from pathlib import Path

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
TAG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,39}$")
META_ORDER = ["node_type", "type", "tags", "originSessionId",
              "lastReviewed", "declineCount", "nextEligible"]
FACET_HEADS = ("domain", "tool", "method-pattern")


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
    """Live faceted grammar: '## domain|tool|method-pattern' headings, '- tag — gloss' (em-dash)
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
    for (c, a, _) in links["synonyms"]:
        if c not in active:                            # left=canonical must be a real tag;
            errors.append(f"synonym canonical '{c}' is not an active tag")
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
    for name in ("_tags.md", "_tag_links.md"):
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


def rebuild(memdir):
    tags = parse_tags_md(memdir / "_tags.md")
    active = set(tags["active"])
    smap = synonym_map(parse_tag_links(memdir / "_tag_links.md")["synonyms"])
    memories, invalid, tag_index = [], [], {}
    for p in _memory_files(memdir):
        top, meta, _ = parse_frontmatter(p.read_text())
        mtags = meta.get("tags", []) or []
        bad = [t for t in mtags if t not in active]
        if bad:
            invalid.append({"file": p.name, "error": f"unknown tags: {sorted(set(bad))}"})
            continue
        canon = sorted({smap.get(t, t) for t in mtags})
        desc = (top.get("description", "") or "").strip().strip('"').strip("'")
        memories.append({
            "id": p.stem, "file": p.name, "path": str(p),
            "name": top.get("name", p.stem), "description": desc,
            "type": meta.get("type", ""), "tags": mtags, "canonicalTags": canon,
        })
        for t in canon:
            tag_index.setdefault(t, []).append(p.stem)
    catalog = {
        "schemaVersion": 1,
        "sourceFingerprint": fingerprint(memdir),
        "generated": datetime.date.today().isoformat(),
        "activeTags": sorted(active),
        "memories": memories,
        "tagToMemoryIds": tag_index,
        "invalidMemories": invalid,
    }
    write_atomic(memdir / "_memory_catalog.json",
                 json.dumps(catalog, indent=1, ensure_ascii=False) + "\n")
    return catalog


# ---------------------------------------------------------------- check-write
def _closest(tag, active, n=3):
    def score(a):
        if a.startswith(tag[:3]) or tag.startswith(a[:3]):
            common = len(set(tag) & set(a))
            return (1, common)
        return (0, len(set(tag) & set(a)))
    return [a for a, _ in sorted(((a, score(a)) for a in active),
                                 key=lambda x: x[1], reverse=True)[:n]]


def check_write(memdir, content):
    tags = parse_tags_md(memdir / "_tags.md")
    active = set(tags["active"])
    top, meta, _ = parse_frontmatter(content)
    if "tags" in top:                                  # tags MUST nest under metadata: else they
        return 2, ("memory tags must be nested under 'metadata:' — found a top-level 'tags' key; "
                   "move it under the metadata: block so the tags are validated.")
    mtags = meta.get("tags", []) or []
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
        return 2, f"memory tag '{t}' is {why}{hint}. Add it to _tags.md first if it is genuinely new."
    return 0, ""


# ---------------------------------------------------------------- CLI
def _arg(flag, default=None):
    return sys.argv[sys.argv.index(flag) + 1] if flag in sys.argv else default


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
    if cmd == "rebuild":
        cat = rebuild(memdir)
        if cat["invalidMemories"]:
            print(json.dumps({"invalidMemories": cat["invalidMemories"]}), file=sys.stderr)
        return 0
    if cmd == "check-write":
        cf = _arg("--content-file")
        content = Path(cf).read_text() if cf else sys.stdin.read()
        rc, msg = check_write(memdir, content)
        if rc:
            print(msg)
        return rc
    print(f"unknown command: {cmd!r}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
