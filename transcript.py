"""
transcript.py -- a structural map-and-search tool for Claude Code's own
session .jsonl files, tailored to what an assistant actually needs when
investigating its own raw transcripts.

Not general-purpose the way lens.py is. This one knows the shape of a
Claude Code session line: {type, message: {role, content: [...]}, timestamp,
sessionId, ...}, with content blocks tagged thinking/text/tool_use/
tool_result. Built 2026-07-20 after a night of hand-rolling the same four
queries from scratch, repeatedly, under time pressure.

Usage:
    py transcript.py map <file>
        Structural overview, no content read back yet: total lines,
        timestamp range, size, counts by block type and by message role.
        Always the first command to run on an unfamiliar file.

    py transcript.py thinking <file> [--min-length N] [--contains TEXT] [--last N]
        List thinking blocks: line index + preview. --min-length filters
        out trivial ones (default 5 chars); --contains does a case-
        insensitive substring filter; --last caps how many are shown,
        most recent first.

    py transcript.py search <text> (--file FILE | --all-projects)
                          [--roles user,assistant] [--block-type text,thinking,tool_use,tool_result]
                          [--exact]
        Search one file or every .jsonl under ~/.claude/projects/ for a
        substring (or, with --exact, a literal exact-match block) inside
        content blocks, filtered by message role and/or block type.
        Prints file, line index, role, block type, and a preview per hit.

    py transcript.py show <file> <line_index>
        Full, cleanly-formatted content of one specific line (1-indexed,
        matching what map/thinking/search report) -- every block, in
        order, not another raw json.loads one-off.

Scoped to what actually got needed: no diff command, since cross-file
comparison is just `search` run twice with --exact and eyeballing the
file column.
"""
import argparse
import glob
import json
import os
import sys
from pathlib import Path

DEFAULT_PROJECTS_ROOT = Path.home() / ".claude" / "projects"


def load_lines(path):
    """Returns a list of (raw_line_str, parsed_obj_or_None) per line."""
    out = []
    with open(path, encoding="utf-8") as f:
        for raw in f:
            raw = raw.rstrip("\n")
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError:
                obj = None
            out.append((raw, obj))
    return out


def iter_blocks(obj):
    """Yields (message_role, block_type, text) for every content block in
    one parsed line object. Text is the block's actual string content
    (thinking text, text, tool_use name, or a flattened tool_result)."""
    if not isinstance(obj, dict):
        return
    msg = obj.get("message")
    if not isinstance(msg, dict):
        return
    role = msg.get("role")
    content = msg.get("content")
    if isinstance(content, str):
        yield role, "text", content
        return
    if not isinstance(content, list):
        return
    for c in content:
        if not isinstance(c, dict):
            continue
        btype = c.get("type")
        if btype == "thinking":
            yield role, "thinking", c.get("thinking", "")
        elif btype == "text":
            yield role, "text", c.get("text", "")
        elif btype == "tool_use":
            yield role, "tool_use", f"{c.get('name', '?')}({json.dumps(c.get('input', {}))[:200]})"
        elif btype == "tool_result":
            inner = c.get("content")
            if isinstance(inner, list):
                inner = " ".join(str(x.get("text", "")) for x in inner if isinstance(x, dict))
            yield role, "tool_result", str(inner)


def cmd_map(path):
    lines = load_lines(path)
    total = len(lines)
    size = os.path.getsize(path)

    first_ts = last_ts = None
    type_counts = {}
    role_counts = {}
    block_counts = {}

    for raw, obj in lines:
        if not isinstance(obj, dict):
            continue
        ts = obj.get("timestamp")
        if ts:
            if first_ts is None:
                first_ts = ts
            last_ts = ts
        t = obj.get("type") or "(untyped event)"
        type_counts[t] = type_counts.get(t, 0) + 1
        for role, btype, _ in iter_blocks(obj):
            role_counts[role] = role_counts.get(role, 0) + 1
            block_counts[btype] = block_counts.get(btype, 0) + 1

    print(path)
    print(f"  {total} lines, {size / 1024:.1f} KB")
    print(f"  timestamp range: {first_ts}  ->  {last_ts}")
    print()
    print("  line types:")
    for t, n in sorted(type_counts.items(), key=lambda kv: -kv[1]):
        print(f"    {n:>6}  {t}")
    print()
    print("  content blocks by role:")
    for r, n in sorted(role_counts.items(), key=lambda kv: -kv[1]):
        print(f"    {n:>6}  {r}")
    print()
    print("  content blocks by type:")
    for b, n in sorted(block_counts.items(), key=lambda kv: -kv[1]):
        print(f"    {n:>6}  {b}")


def cmd_thinking(path, min_length, contains, last):
    lines = load_lines(path)
    hits = []
    for i, (raw, obj) in enumerate(lines):
        for role, btype, text in iter_blocks(obj):
            if btype != "thinking":
                continue
            if len(text.strip()) < min_length:
                continue
            if contains and contains.lower() not in text.lower():
                continue
            hits.append((i, text))

    if last:
        hits = hits[-last:]

    if not hits:
        print("No matching thinking blocks.")
        return
    for idx, text in hits:
        preview = text.strip().replace("\n", " | ")[:200]
        print(f"line {idx + 1}: {preview}")


def _search_one_file(path, needle, roles, block_types, exact):
    results = []
    lines = load_lines(path)
    for i, (raw, obj) in enumerate(lines):
        for role, btype, text in iter_blocks(obj):
            if roles and role not in roles:
                continue
            if block_types and btype not in block_types:
                continue
            if exact:
                match = (text == needle)
            else:
                match = (needle.lower() in text.lower())
            if match:
                preview = text.strip().replace("\n", " | ")[:200]
                results.append((i, role, btype, preview))
    return results


def cmd_search(needle, file, all_projects, roles, block_types, exact):
    roles = set(roles.split(",")) if roles else None
    block_types = set(block_types.split(",")) if block_types else None

    if all_projects:
        targets = []
        for proj_dir in sorted(glob.glob(str(DEFAULT_PROJECTS_ROOT / "*"))):
            targets += sorted(glob.glob(os.path.join(proj_dir, "*.jsonl")))
    else:
        targets = [file]

    total_hits = 0
    for path in targets:
        hits = _search_one_file(path, needle, roles, block_types, exact)
        for idx, role, btype, preview in hits:
            print(f"{path}  line {idx + 1}  [{role}/{btype}]  {preview}")
            total_hits += 1

    if total_hits == 0:
        print("No matches.")
    else:
        print(f"\n{total_hits} match(es) across {len(targets)} file(s).")


def cmd_show(path, line_index):
    lines = load_lines(path)
    i = line_index - 1
    if i < 0 or i >= len(lines):
        print(f"Line {line_index} out of range (file has {len(lines)} lines).")
        sys.exit(1)
    raw, obj = lines[i]
    if obj is None:
        print(f"line {line_index}: could not parse as JSON, raw content below:\n{raw}")
        return

    print(f"line {line_index}  type={obj.get('type')}  timestamp={obj.get('timestamp')}")
    print(f"  uuid={obj.get('uuid')}  parentUuid={obj.get('parentUuid')}")
    print()
    blocks = list(iter_blocks(obj))
    if not blocks:
        print("(no content blocks)")
        return
    for role, btype, text in blocks:
        print(f"--- {role} / {btype} ---")
        print(text)
        print()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_map = sub.add_parser("map", help="Structural overview of a session file.")
    p_map.add_argument("file")

    p_think = sub.add_parser("thinking", help="List thinking blocks, filterable.")
    p_think.add_argument("file")
    p_think.add_argument("--min-length", type=int, default=5)
    p_think.add_argument("--contains", default=None)
    p_think.add_argument("--last", type=int, default=None)

    p_search = sub.add_parser("search", help="Search one file or all projects for a phrase.")
    p_search.add_argument("text")
    g = p_search.add_mutually_exclusive_group(required=True)
    g.add_argument("--file")
    g.add_argument("--all-projects", action="store_true")
    p_search.add_argument("--roles", default=None, help="comma-separated, e.g. assistant,user")
    p_search.add_argument("--block-type", default=None, help="comma-separated, e.g. text,thinking")
    p_search.add_argument("--exact", action="store_true", help="exact block match instead of substring")

    p_show = sub.add_parser("show", help="Full content of one line.")
    p_show.add_argument("file")
    p_show.add_argument("line_index", type=int)

    args = ap.parse_args()

    if args.cmd == "map":
        cmd_map(args.file)
    elif args.cmd == "thinking":
        cmd_thinking(args.file, args.min_length, args.contains, args.last)
    elif args.cmd == "search":
        cmd_search(args.text, args.file, args.all_projects, args.roles, args.block_type, args.exact)
    elif args.cmd == "show":
        cmd_show(args.file, args.line_index)


if __name__ == "__main__":
    main()
