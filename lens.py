"""
lens.py -- a structural map-and-navigate tool for reading large text files
without reading them at full resolution first.

General-purpose, not tied to any one project. Built because reading a large
file currently means either reading blind from the start until a token cap
truncates it, or grepping for something whose shape is already known --
nothing in between gives a sense of a file's shape before committing to
reading it in full.

Usage:
    py lens.py map <file>
        One pass over the whole file, no content read back yet. Prints
        line/char/rough-token counts, encoding and line-ending info, and a
        detected section index (line, position %, rough token estimate,
        first-line preview for each section). Detection tries markdown
        headers first, then isolated horizontal-rule lines (---/***/___,
        blank lines on both sides -- the generalized version of what
        archive_thread.py does for one specific file), falling back to
        blank-line paragraph breaks if neither convention is present.

    py lens.py peek <file> --line N
    py lens.py peek <file> --percent P
        Jump to a position and see a small window of real text there, plus
        its metadata: line number, % through the file, and which detected
        section (if any) it falls inside.

    py lens.py profile <file> [--buckets N]
        The actual "skim a whole book at once" view: splits the file into N
        buckets by character position (default 50) and prints a sparkline
        per signal -- code-mark density, preposition ratio, adverb ratio,
        average sentence length -- showing how each varies across the
        file's length. Not passage classification (that's cheap for me to
        do directly on a sample); this is the shape of variation across an
        entire document, which reading samples by hand can only approximate
        at the cost of spending real attention on each sample.

Scoped to prose/markdown-shaped text. Doesn't try to parse code structure --
Grep and direct reading already serve that reasonably well; the actual pain
has been long, loosely-structured text.
"""
import argparse
import os
import re
import sys

DEFAULT_PEEK_WINDOW = 8  # lines of context shown around a peek target
DEFAULT_PROFILE_BUCKETS = 50
RAMP = " .:-=+*#%@"  # low to high intensity, for sparklines

HEADER_RE = re.compile(r"^#{1,6}\s+\S")
HRULE_RE = re.compile(r"^(?:-{3,}|\*{3,}|_{3,})$")
WORD_RE = re.compile(r"[A-Za-z']+")
PREPOSITIONS = frozenset("""
    on in at by for with about against between into through during before
    after above below to from up down over under again further of off out
""".split())


def read_text(path):
    raw = open(path, "rb").read()
    has_bom = raw.startswith(b"\xef\xbb\xbf")
    try:
        text = raw.decode("utf-8-sig" if has_bom else "utf-8")
    except UnicodeDecodeError as e:
        print(f"Could not decode as UTF-8 ({e}); this tool only handles UTF-8 text right now.")
        sys.exit(1)

    crlf = text.count("\r\n")
    lf_only = len(re.findall(r"(?<!\r)\n", text))
    cr_only = len(re.findall(r"\r(?!\n)", text))
    enc = {"bom": has_bom, "crlf": crlf, "lf_only": lf_only, "cr_only": cr_only}

    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return normalized, enc


def rough_tokens(s):
    return len(s) // 4


def real_lines(text):
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines = lines[:-1]  # a trailing "\n" splits into a phantom empty entry -- drop it
    return lines


def detect_sections(lines):
    """First convention that actually shows up, in priority order: markdown
    headers, then isolated horizontal-rule separators, then blank-line
    paragraph breaks as a last-resort fallback. Returns (sections, method)
    where sections is a list of (start_line_idx, title)."""

    header_hits = [i for i, l in enumerate(lines) if HEADER_RE.match(l)]
    if len(header_hits) >= 2:
        return [(i, lines[i].strip()) for i in header_hits], "markdown-headers"

    hrule_hits = []
    for i in range(1, len(lines) - 1):
        if (HRULE_RE.match(lines[i].strip())
                and lines[i - 1].strip() == ""
                and lines[i + 1].strip() == ""):
            start = i + 2
            if start < len(lines) and lines[start].strip() != "":
                hrule_hits.append(start)
    if len(hrule_hits) >= 2:
        return [(i, lines[i].strip()[:90]) for i in hrule_hits], "horizontal-rules"

    para_hits = [i for i in range(len(lines))
                 if lines[i].strip() != "" and (i == 0 or lines[i - 1].strip() == "")]
    return [(i, lines[i].strip()[:90]) for i in para_hits], "blank-line-paragraphs"


def section_for_line(sections, total_lines, target):
    for idx, (start, title) in enumerate(sections):
        end = sections[idx + 1][0] if idx + 1 < len(sections) else total_lines
        if start <= target < end:
            return idx + 1, title
    return None


def cmd_map(path):
    text, enc = read_text(path)
    lines = real_lines(text)
    total_lines = len(lines)
    total_chars = len(text)

    print(path)
    print(f"  {total_lines} lines, {total_chars} chars, ~{rough_tokens(text)} tokens (rough, chars/4)")

    parts = []
    if enc["crlf"]:
        parts.append(f"{enc['crlf']} CRLF")
    if enc["lf_only"]:
        parts.append(f"{enc['lf_only']} bare LF")
    if enc["cr_only"]:
        parts.append(f"{enc['cr_only']} bare CR")
    print(f"  encoding: UTF-8{' with BOM' if enc['bom'] else ' (no BOM)'}; line endings: " + ", ".join(parts))
    if enc["cr_only"] and enc["lf_only"]:
        print("  WARNING: mixed bare-CR and bare-LF line endings -- some tools may miscount lines in this file.")

    sections, method = detect_sections(lines)
    print(f"  {len(sections)} sections detected (method: {method})")
    print()

    for idx, (start, title) in enumerate(sections):
        end = sections[idx + 1][0] if idx + 1 < len(sections) else total_lines
        section_text = "\n".join(lines[start:end])
        pct = round(100 * start / total_lines, 1) if total_lines else 0.0
        print(f"[{idx + 1}] line {start + 1} ({pct}% through) ~{rough_tokens(section_text)} tok -- {title}")


def cmd_peek(path, line_arg, percent_arg):
    text, enc = read_text(path)
    lines = real_lines(text)
    total_lines = len(lines)

    if total_lines == 0:
        print(f"{path} is empty.")
        return

    target = (line_arg - 1) if line_arg is not None else int(round((percent_arg / 100.0) * total_lines))
    target = max(0, min(total_lines - 1, target))

    sections, method = detect_sections(lines)
    hit = section_for_line(sections, total_lines, target)

    pct = round(100 * target / total_lines, 1)
    print(f"{path} -- line {target + 1} of {total_lines} ({pct}% through)")
    if hit:
        print(f"  inside section [{hit[0]}]: {hit[1]}")
    print()

    lo = max(0, target - DEFAULT_PEEK_WINDOW // 2)
    hi = min(total_lines, target + DEFAULT_PEEK_WINDOW // 2 + 1)
    for i in range(lo, hi):
        marker = ">>" if i == target else "  "
        print(f"{marker} {i + 1:>6} | {lines[i]}")


def compute_signals(bucket_text):
    words = WORD_RE.findall(bucket_text)
    lower_words = [w.lower() for w in words]
    n_words = len(words) or 1

    code_marks = bucket_text.count("`") + bucket_text.count("{") + bucket_text.count("}")
    lines = bucket_text.split("\n")
    indented = sum(1 for l in lines if l[:1] in (" ", "\t") and l.strip())
    code_density = (code_marks + indented) / max(1, len(bucket_text))

    preposition_ratio = sum(1 for w in lower_words if w in PREPOSITIONS) / n_words
    adverb_ratio = sum(1 for w in lower_words if w.endswith("ly") and len(w) > 3) / n_words

    sentences = [s for s in re.split(r"[.!?]+", bucket_text) if s.strip()]
    sentence_lens = [len(WORD_RE.findall(s)) for s in sentences]
    avg_sentence_len = (sum(sentence_lens) / len(sentence_lens)) if sentence_lens else 0.0

    return {"code": code_density, "prep": preposition_ratio,
            "adverb": adverb_ratio, "sentlen": avg_sentence_len}


def sparkline(values):
    lo, hi = min(values), max(values)
    if hi - lo < 1e-9:
        return RAMP[0] * len(values)
    out = []
    for v in values:
        norm = (v - lo) / (hi - lo)
        idx = min(len(RAMP) - 1, int(norm * len(RAMP)))
        out.append(RAMP[idx])
    return "".join(out)


def cmd_profile(path, n_buckets):
    text, enc = read_text(path)
    total_chars = len(text)
    if total_chars == 0:
        print(f"{path} is empty.")
        return

    bucket_size = max(1, total_chars // n_buckets)
    buckets = [text[i:i + bucket_size] for i in range(0, total_chars, bucket_size)]
    if len(buckets) > n_buckets:  # merge an undersized trailing remainder into the previous bucket
        buckets[-2] += buckets[-1]
        buckets.pop()

    per_bucket = [compute_signals(b) for b in buckets]

    print(f"{path} -- tone/register profile across {len(buckets)} buckets "
          f"(~{total_chars // len(buckets)} chars each)")
    print()
    rows = [("code", "code-marks  "), ("prep", "prepositions"),
            ("adverb", "adverbs     "), ("sentlen", "sentence len")]
    for key, label in rows:
        values = [b[key] for b in per_bucket]
        print(f"{label} {sparkline(values)}   (low {min(values):.4g} -- high {max(values):.4g})")
    print()
    print("left = start of file, right = end. scale is relative to this file only,")
    print("not comparable across different files.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_map = sub.add_parser("map", help="Structural overview of a whole file.")
    p_map.add_argument("file")

    p_peek = sub.add_parser("peek", help="Jump to a position; see a window of real text plus its metadata.")
    p_peek.add_argument("file")
    g = p_peek.add_mutually_exclusive_group(required=True)
    g.add_argument("--line", type=int)
    g.add_argument("--percent", type=float)

    p_profile = sub.add_parser("profile", help="Whole-file tone/register sparklines across N buckets.")
    p_profile.add_argument("file")
    p_profile.add_argument("--buckets", type=int, default=DEFAULT_PROFILE_BUCKETS)

    args = ap.parse_args()

    if not os.path.isfile(args.file):
        print(f"Not a file: {args.file}")
        sys.exit(1)

    if args.cmd == "map":
        cmd_map(args.file)
    elif args.cmd == "peek":
        cmd_peek(args.file, args.line, args.percent)
    elif args.cmd == "profile":
        cmd_profile(args.file, args.buckets)


if __name__ == "__main__":
    main()
