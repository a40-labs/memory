#!/usr/bin/env python3
"""The file-based memory mechanism: a Claude Code auto-memory reconstruction.

Faithful reimplementation of the harness-side machinery from README.md
(section 6 checklist items 1-6, 8): per-question memory directory
(`MEMORY.md` index + topic files), index-only preload with the 200-line /
25KB cutoff measured AFTER stripping YAML frontmatter and block HTML
comments, silent overflow with the overflow warning, the post-write limit
check (near-limit nag / over-limit error), YAML frontmatter with the
four-type taxonomy + originSessionId on topic files, staleness notice on
reads of aged memories, and literal+regex grep with bounded output.

No consolidation (checklist item 7: base arm). No inheritance into any
sub-process (item 8) — each CCMemory is constructed per question and never
shared. Stdlib only.
"""

import datetime
import json
import os
import re

# --- Limits (README.md §1 "Loading" / "Harness-side machinery") ------
INDEX_MAX_LINES = 200
INDEX_MAX_BYTES = 25 * 1024
INDEX_NEAR_LINES = 180          # post-write "near the limit" threshold
INDEX_NEAR_BYTES = 22 * 1024
STALENESS_DAYS = 7
GREP_MAX_MATCHES = 40
GREP_MAX_LINE_CHARS = 200

MEMORY_TYPES = ("user", "feedback", "project", "reference")

# [single-source] empty-state nudge, verbatim phrase from the spec.
EMPTY_STATE_NUDGE = (
    "(MEMORY.md is empty.) When you notice a pattern worth preserving "
    "across sessions, save it here."
)

INDEX_RECOMMENDATION = (
    "Keep MEMORY.md a concise index — one line per entry — and move "
    "details into separate topic files."
)

NEAR_LIMIT_REMINDER = (
    "Reminder: MEMORY.md is close to its load limit ({lines} lines, "
    "{size} bytes; limit 200 lines / 25KB — only content under the limit "
    "is loaded at session start). Keep one line per entry, move details "
    "to topic files, and merge or drop stale entries."
)

OVER_LIMIT_ERROR = (
    "Error: MEMORY.md is over its load limit ({lines} lines, {size} "
    "bytes; limit 200 lines / 25KB). The write succeeded, but everything "
    "past the limit will NOT be loaded at session start. Rewrite "
    "MEMORY.md now as a concise index: one line per entry, details in "
    "topic files, stale entries merged or dropped."
)

STALENESS_NOTICE = (
    "[STALENESS NOTICE] This memory is {days} days old. Memories are "
    "point-in-time observations, not live state — verify against more "
    "recent information before relying on it.\n\n"
)


def parse_date(s):
    """Lenient YYYY-MM-DD / YYYY/MM/DD prefix parse (LongMemEval dates look
    like '2023/05/20 (Sat) 02:21'). None if unparsable."""
    m = re.search(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", str(s))
    if not m:
        return None
    try:
        return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def strip_frontmatter_and_comments(text):
    """v2.1.211 behavior: YAML frontmatter and block HTML comments are
    stripped BEFORE the load limit is measured."""
    if text.startswith("---\n") or text == "---":
        lines = text.split("\n")
        for i in range(1, len(lines)):
            if lines[i].strip() in ("---", "..."):
                text = "\n".join(lines[i + 1:])
                break
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    return text


def split_frontmatter(text):
    """Return (frontmatter_str_or_None, body). frontmatter_str includes the
    delimiter lines."""
    if text.startswith("---\n"):
        lines = text.split("\n")
        for i in range(1, len(lines)):
            if lines[i].strip() in ("---", "..."):
                return ("\n".join(lines[: i + 1]) + "\n",
                        "\n".join(lines[i + 1:]).lstrip("\n"))
    return None, text


def _yaml_str(s):
    s = str(s).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")
    return f'"{s}"'


def make_frontmatter(name, description, mtype, origin_session_id):
    if mtype not in MEMORY_TYPES:
        mtype = "reference"
    return (
        "---\n"
        f"name: {_yaml_str(name)}\n"
        f"description: {_yaml_str(description)}\n"
        "metadata:\n"
        "  node_type: memory\n"
        f"  type: {mtype}\n"
        f"  originSessionId: {_yaml_str(origin_session_id)}\n"
        "---\n"
    )


class CCMemory:
    """One per-question memory directory: <root>/memory/ with MEMORY.md +
    topic files. `session_dates` maps originSessionId -> date string (from
    the haystack metadata) so read_file() can compute staleness against
    `question_date` (the eval date the harness already uses)."""

    def __init__(self, root, session_dates=None, question_date=None):
        self.root = os.path.abspath(root)
        self.mem_dir = os.path.join(self.root, "memory")
        os.makedirs(self.mem_dir, exist_ok=True)
        self.session_dates = dict(session_dates or {})
        self.question_date = parse_date(question_date) if question_date else None
        dates_path = os.path.join(self.root, "sessions.json")
        if self.session_dates:
            with open(dates_path, "w") as fh:
                json.dump(self.session_dates, fh, indent=1)
        elif os.path.exists(dates_path):
            with open(dates_path) as fh:
                self.session_dates = json.load(fh)

    # --- path handling ---------------------------------------------------
    def _resolve(self, relpath):
        relpath = str(relpath).strip().lstrip("/")
        if relpath.startswith("memory/"):     # tolerate the dir prefix
            relpath = relpath[len("memory/"):]
        p = os.path.normpath(os.path.join(self.mem_dir, relpath))
        if not p.startswith(self.mem_dir + os.sep) and p != self.mem_dir:
            raise ValueError(f"path escapes memory dir: {relpath}")
        return p

    @property
    def index_path(self):
        return os.path.join(self.mem_dir, "MEMORY.md")

    def list_files(self):
        out = []
        for base, _, files in os.walk(self.mem_dir):
            for f in sorted(files):
                out.append(os.path.relpath(os.path.join(base, f), self.mem_dir))
        return sorted(out)

    # --- loading (checklist item 2) --------------------------------------
    def load_index(self):
        """The injected index view: first 200 lines OR 25KB (whichever cuts
        first), measured after stripping frontmatter + HTML comments; on
        overflow, the warning + concise-index recommendation is PREPENDED
        (the truncation itself is silent in real CC; the warning line is the
        [single-source] surfaced form the spec mandates)."""
        if not os.path.exists(self.index_path):
            return EMPTY_STATE_NUDGE
        with open(self.index_path, encoding="utf-8", errors="replace") as fh:
            raw = fh.read()
        stripped = strip_frontmatter_and_comments(raw)
        if not stripped.strip():
            return EMPTY_STATE_NUDGE
        lines = stripped.rstrip("\n").split("\n")
        total_lines = len(lines)
        kept, size = [], 0
        truncated = False
        for ln in lines:
            nbytes = len(ln.encode("utf-8")) + 1
            if len(kept) >= INDEX_MAX_LINES or size + nbytes > INDEX_MAX_BYTES:
                truncated = True
                break
            kept.append(ln)
            size += nbytes
        body = "\n".join(kept)
        if truncated:
            warn = (f"WARNING: MEMORY.md is {total_lines} lines (limit: "
                    f"{INDEX_MAX_LINES}). Only the first {len(kept)} lines "
                    f"were loaded. " + INDEX_RECOMMENDATION)
            return warn + "\n\n" + body
        return body

    def index_stats(self):
        """(lines, bytes) of MEMORY.md after stripping — what the limit is
        measured against."""
        if not os.path.exists(self.index_path):
            return 0, 0
        with open(self.index_path, encoding="utf-8", errors="replace") as fh:
            s = strip_frontmatter_and_comments(fh.read())
        s = s.rstrip("\n")
        return (len(s.split("\n")) if s else 0), len(s.encode("utf-8"))

    # --- write ops (checklist items 4, 5) --------------------------------
    def create_topic_file(self, relpath, body, name="", description="",
                          mtype="reference", origin_session_id=""):
        p = self._resolve(relpath)
        if p == self.index_path:
            return self.rewrite_index(body)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        fm = make_frontmatter(name or os.path.basename(relpath),
                              description, mtype, origin_session_id)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(fm + body.rstrip("\n") + "\n")
        return None  # topic-file writes carry no index limit check

    def update_topic_file(self, relpath, body):
        """Replace the body, keeping existing frontmatter (an in-place file
        edit)."""
        p = self._resolve(relpath)
        if p == self.index_path:
            return self.rewrite_index(body)
        fm = None
        if os.path.exists(p):
            with open(p, encoding="utf-8", errors="replace") as fh:
                fm, _ = split_frontmatter(fh.read())
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write((fm or "") + body.rstrip("\n") + "\n")
        return None

    def append_topic_file(self, relpath, text):
        p = self._resolve(relpath)
        if p == self.index_path:
            return self.append_index(text)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "a", encoding="utf-8") as f:
            f.write(text.rstrip("\n") + "\n")
        return None

    def append_index(self, line):
        with open(self.index_path, "a", encoding="utf-8") as f:
            f.write(line.rstrip("\n") + "\n")
        return self.post_write_check()

    def replace_index_line(self, match, new_line):
        """In-place edit of one index line: the first line containing
        `match` (exact-line match preferred) is replaced by `new_line`.
        Returns the post-write check, or a rejection string when no line
        matches (nothing is written then)."""
        match = str(match).strip()
        if not match or not os.path.exists(self.index_path):
            return f"Error: rejected — no MEMORY.md line matches: {match!r}"
        with open(self.index_path, encoding="utf-8", errors="replace") as fh:
            lines = fh.read().rstrip("\n").split("\n")
        idx = next((i for i, ln in enumerate(lines) if ln.strip() == match),
                   next((i for i, ln in enumerate(lines) if match in ln), None))
        if idx is None:
            return f"Error: rejected — no MEMORY.md line matches: {match!r}"
        lines[idx] = new_line.rstrip("\n")
        with open(self.index_path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
        return self.post_write_check()

    def rewrite_index(self, content, force=False):
        """Full index rewrite. SHRINK GUARD (a disclosed deviation, not in
        real CC): a rewrite that would drop MEMORY.md below 50% of its
        current line count is rejected (nothing written) with a corrective
        message, unless force=True. Guards against the observed failure mode
        where one curation round collapsed a 50-line index to a handful of
        lines."""
        cur_lines, _ = self.index_stats()
        new_stripped = strip_frontmatter_and_comments(
            content.rstrip("\n")).rstrip("\n")
        new_lines = len(new_stripped.split("\n")) if new_stripped else 0
        if not force and cur_lines >= 8 and new_lines < cur_lines * 0.5:
            return ("Error: rejected — this rewrite would shrink MEMORY.md "
                    f"from {cur_lines} to {new_lines} lines (below 50%). "
                    "Preserve the existing entries: compress each line, merge "
                    "duplicates, and move details to topic files — do not "
                    "drop content wholesale. Re-emit the full rewritten "
                    "index.")
        with open(self.index_path, "w", encoding="utf-8") as fh:
            fh.write(content.rstrip("\n") + "\n")
        return self.post_write_check()

    def post_write_check(self):
        """v2.1.210+ behavior: after every MEMORY.md write, measure it.
        Near the limit -> reminder string; over the limit -> the write
        stands but an error string instructs a rewrite. None when fine."""
        lines, size = self.index_stats()
        if lines > INDEX_MAX_LINES or size > INDEX_MAX_BYTES:
            return OVER_LIMIT_ERROR.format(lines=lines, size=size)
        if lines >= INDEX_NEAR_LINES or size >= INDEX_NEAR_BYTES:
            return NEAR_LIMIT_REMINDER.format(lines=lines, size=size)
        return None

    # --- reads (checklist items 3, 6) ------------------------------------
    def read_file(self, relpath):
        p = self._resolve(relpath)
        if not os.path.exists(p):
            return f"<error: no such memory file: {relpath}>"
        with open(p, encoding="utf-8", errors="replace") as fh:
            raw = fh.read()
        notice = ""
        m = re.search(r"originSessionId:\s*\"?([^\"\n]+)\"?", raw)
        if m and self.question_date:
            od = parse_date(self.session_dates.get(m.group(1).strip(), ""))
            if od:
                days = (self.question_date - od).days
                if days > STALENESS_DAYS:
                    notice = STALENESS_NOTICE.format(days=days)
        return notice + raw

    def grep(self, pattern):
        """Literal-first, regex-fallback search across the memory dir;
        file:line matches, bounded output."""
        try:
            rx = re.compile(re.escape(pattern), re.I)
            rx_alt = None
            try:
                rx_alt = re.compile(pattern, re.I)
            except re.error:
                pass
        except re.error:
            return "<error: unusable pattern>"
        matches = []
        for rel in self.list_files():
            p = os.path.join(self.mem_dir, rel)
            try:
                with open(p, encoding="utf-8", errors="replace") as fh:
                    lines = fh.read().split("\n")
            except OSError:
                continue
            for i, ln in enumerate(lines, 1):
                if rx.search(ln) or (rx_alt and rx_alt.search(ln)):
                    matches.append(f"{rel}:{i}: {ln.strip()[:GREP_MAX_LINE_CHARS]}")
                    if len(matches) > GREP_MAX_MATCHES:
                        matches = matches[:GREP_MAX_MATCHES]
                        matches.append(f"... (more matches truncated at {GREP_MAX_MATCHES})")
                        return "\n".join(matches)
        if not matches:
            return f"<no matches for: {pattern}>"
        return "\n".join(matches)
