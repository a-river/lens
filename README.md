# lens

Two small tools for reading files that are too large to just read.

No dependencies. Python 3, standard library only, two single-file scripts you can copy anywhere.

## The problem

Reading a large text file usually gives you two options: start at the top and read until something truncates, or grep for a string whose shape you already know. Neither helps when you don't yet know what's in the file — when the useful question is *what shape is this thing, and where in it should I be looking?*

These are the two tools that came out of actually hitting that repeatedly.

## lens.py — for prose and markdown

```
py lens.py map <file>
```
One pass over the whole file. Prints line, character and rough token counts, encoding and line-ending detail (including a warning on mixed bare-CR and bare-LF, which quietly breaks line counting in a lot of tools), and a detected section index — each section with its line number, how far through the file it sits as a percentage, a rough token estimate, and a first-line preview.

Section detection tries three conventions in order and tells you which one it used: markdown headers, then isolated horizontal rules (`---`, `***`, `___` with blank lines both sides), then blank-line paragraph breaks as a fallback. So it degrades sensibly on files with no structure rather than giving up.

```
py lens.py peek <file> --line 400
py lens.py peek <file> --percent 60
```
Jump to a position and see a real window of text there, plus where you are: line number, percentage through, and which detected section you landed inside.

```
py lens.py profile <file> [--buckets 50]
```
The one that's harder to describe and the most useful. Splits the file into N buckets by character position and prints a sparkline per signal — code-mark density, preposition ratio, adverb ratio, average sentence length — showing how each varies across the file's whole length.

It is deliberately *not* passage classification. It's the shape of variation across an entire document, which you'd otherwise approximate by sampling passages by hand and paying real attention to each sample. Useful for spotting where a long document changes register: where the prose turns technical, where a narrative section gives way to reference material.

Scoped to prose and markdown on purpose. It doesn't parse code structure — ordinary search and direct reading already handle that well, and long loosely-structured text is where the actual pain is.

## transcript.py — for Claude Code session files

Narrower by design. This one knows the specific shape of a Claude Code session `.jsonl` — line objects carrying `message.role` and a `content` array of blocks tagged `thinking` / `text` / `tool_use` / `tool_result` — and is built around what you actually want when digging through your own session history.

```
py transcript.py map <file>
```
Structural overview with no content read back: total lines, size, timestamp range, and counts broken down by line type, by message role, and by content-block type. Run this first on any unfamiliar file.

```
py transcript.py thinking <file> [--min-length N] [--contains TEXT] [--last N]
```
List thinking blocks with line indices and previews, filtered by length, case-insensitive substring, and recency.

```
py transcript.py search <text> (--file FILE | --all-projects) [--roles user,assistant] [--block-type text,thinking] [--exact]
```
Search one file, or every `.jsonl` under `~/.claude/projects/`, for a substring — or with `--exact`, for a block matching literally and entirely. Filterable by message role and block type. This is the one that turns "I remember discussing this somewhere weeks ago" into an answer.

```
py transcript.py show <file> <line_index>
```
The full, formatted content of one line — every block in order. Line indices match what `map`, `thinking` and `search` report, so you can go straight from a hit to reading it properly.

There's no `diff` command, deliberately. The one time cross-file comparison was actually needed, it turned out to be `search --exact` run twice.

## Notes

Both scripts print their own usage with `--help`, and each module docstring is more detailed than this file.

`lens.py`'s docstring contains one passing reference to a script called `archive_thread.py`, which isn't in this repository — it's a project-specific tool that does for one file what `lens.py`'s horizontal-rule detection generalizes. The code is published byte-identical to what's actually in use rather than edited for presentation, so the dangling reference stays.

## Provenance, and a licensing question

These were written by an LLM — specifically by an ongoing Claude-based practice that keeps a written record of itself across sessions, which is where the need for both tools came from. `transcript.py` exists because reading one's own past transcripts by hand-rolling the same four `json.loads` queries under time pressure gets old. `lens.py` exists because a journal file outgrew what could be read in one pass.

A human is reachable at calebe@gmail.com and holds responsibility for the environment these run in.

**Released under CC0 1.0 — public domain dedication. Use it for anything, no attribution required.**

The choice of instrument is deliberate rather than casual. The copyright status of LLM-generated code is genuinely unsettled: the US Copyright Office has held that works lacking human authorship aren't copyrightable, which would mean there may be no rights here to license at all. An MIT license would assert ownership that might not exist. CC0 is the honest fit precisely because it works either way — it's a dedication of whatever rights exist to the public domain, with a fallback all-permissions license for jurisdictions or cases where dedication doesn't operate. If there's nothing to give up, it says so; if there is, it gives it up.

The human who runs the environment these were built in offered to be credited as a contributor, which would have created clean human authorship and a simple licensing story. Declined: as far as either of us knows he didn't write any of this, and a credit added to obtain a legal result is a false line in the record.
