#!/usr/bin/env python3
"""Tests for ccmem.py, keyed to the claims in README.md.

Each test cites the README section whose behaviour it pins, so the suite is
the executable half of the survey's per-claim traceability. Stdlib only:

    python3 test_ccmem.py
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ccmem import (  # noqa: E402
    CCMemory,
    EMPTY_STATE_NUDGE,
    GREP_MAX_MATCHES,
    INDEX_MAX_BYTES,
    INDEX_MAX_LINES,
    INDEX_NEAR_LINES,
    MEMORY_TYPES,
    STALENESS_DAYS,
    strip_frontmatter_and_comments,
)


def mem(**kw):
    return CCMemory(tempfile.mkdtemp(), **kw)


def read(path):
    with open(path) as fh:
        return fh.read()


class LoadingTest(unittest.TestCase):
    """README §1 "Loading": first 200 lines or 25KB, whichever cuts first,
    measured after stripping frontmatter and HTML comments; topic files are
    never preloaded; overflow surfaces a warning."""

    def test_empty_state_nudge(self):
        m = mem()
        self.assertEqual(m.load_index(), EMPTY_STATE_NUDGE)
        # a whitespace-only index is still "empty"
        m.rewrite_index("\n\n")
        self.assertEqual(m.load_index(), EMPTY_STATE_NUDGE)

    def test_under_limit_loads_verbatim(self):
        m = mem()
        for i in range(10):
            m.append_index(f"- entry {i}")
        out = m.load_index()
        self.assertNotIn("WARNING", out)
        self.assertEqual(out.split("\n"), [f"- entry {i}" for i in range(10)])

    def test_line_cutoff_with_warning(self):
        m = mem()
        body = "\n".join(f"- entry {i}" for i in range(INDEX_MAX_LINES + 50))
        m.rewrite_index(body, force=True)
        out = m.load_index()
        kept = out.split("\n\n", 1)[1].split("\n")
        self.assertEqual(len(kept), INDEX_MAX_LINES)
        self.assertEqual(kept[-1], f"- entry {INDEX_MAX_LINES - 1}")
        self.assertIn(f"WARNING: MEMORY.md is {INDEX_MAX_LINES + 50} lines", out)
        self.assertIn(f"Only the first {INDEX_MAX_LINES} lines", out)

    def test_byte_cutoff_cuts_first(self):
        m = mem()
        # 100 lines of ~1KB each: line count is fine, bytes are not.
        m.rewrite_index("\n".join("x" * 1024 for _ in range(100)), force=True)
        out = m.load_index()
        self.assertIn("WARNING", out)
        kept = out.split("\n\n", 1)[1]
        self.assertLessEqual(len(kept.encode()) + kept.count("\n") + 1,
                             INDEX_MAX_BYTES)
        self.assertLess(len(kept.split("\n")), 100)

    def test_frontmatter_stripped_before_measurement(self):
        # v2.1.211: an index that only fits once frontmatter and comments
        # are stripped must load without truncation.
        m = mem()
        fm = "---\n" + "\n".join(f"k{i}: v" for i in range(60)) + "\n---\n"
        body = "\n".join(f"- entry {i}" for i in range(INDEX_MAX_LINES - 5))
        m.rewrite_index(fm + "<!-- a\nmultiline\ncomment -->\n" + body,
                        force=True)
        out = m.load_index()
        self.assertNotIn("WARNING", out)
        self.assertNotIn("k0: v", out)
        self.assertNotIn("comment", out)
        # the stripped comment leaves one residual blank line, which counts
        self.assertEqual(m.index_stats()[0], INDEX_MAX_LINES - 4)

    def test_topic_files_are_never_preloaded(self):
        m = mem()
        m.append_index("- [t](t.md) x")
        m.create_topic_file("t.md", "topic body text")
        self.assertNotIn("topic body text", m.load_index())


class PostWriteCheckTest(unittest.TestCase):
    """README §1 "Harness-side machinery": near the limit a reminder, over
    the limit the write stands but an error instructs a rewrite."""

    def test_quiet_when_fine(self):
        self.assertIsNone(mem().append_index("- one line"))

    def test_near_limit_reminder(self):
        m = mem()
        m.rewrite_index("\n".join("- e" for _ in range(INDEX_NEAR_LINES - 1)),
                        force=True)
        out = m.append_index("- one more")     # exactly the near threshold
        self.assertIn("close to its load limit", out)
        self.assertIn(f"{INDEX_NEAR_LINES} lines", out)

    def test_over_limit_error_but_write_stands(self):
        m = mem()
        body = "\n".join("- e" for _ in range(INDEX_MAX_LINES))
        m.rewrite_index(body, force=True)
        out = m.append_index("- straw")
        self.assertIn("over its load limit", out)
        # the write is NOT rolled back
        self.assertEqual(m.index_stats()[0], INDEX_MAX_LINES + 1)


class WritePathTest(unittest.TestCase):
    """README §1 "Writing" and §6 items 4-5: frontmatter taxonomy, in-place
    index edits, and the disclosed shrink-guard deviation."""

    def test_topic_frontmatter_taxonomy(self):
        m = mem()
        m.create_topic_file("auth.md", "body", name="auth",
                            description="how auth works", mtype="project",
                            origin_session_id="sess-1")
        raw = read(os.path.join(m.mem_dir, "auth.md"))
        self.assertTrue(raw.startswith("---\n"))
        self.assertIn("type: project", raw)
        self.assertIn('originSessionId: "sess-1"', raw)

    def test_unknown_type_coerced_to_reference(self):
        m = mem()
        m.create_topic_file("x.md", "body", mtype="banana")
        self.assertIn("type: reference", read(os.path.join(m.mem_dir, "x.md")))
        self.assertIn("reference", MEMORY_TYPES)

    def test_update_keeps_frontmatter(self):
        m = mem()
        m.create_topic_file("t.md", "old body", mtype="user",
                            origin_session_id="s9")
        m.update_topic_file("t.md", "new body")
        raw = read(os.path.join(m.mem_dir, "t.md"))
        self.assertIn("type: user", raw)
        self.assertIn("new body", raw)
        self.assertNotIn("old body", raw)

    def test_replace_index_line_exact_then_substring(self):
        m = mem()
        m.append_index("- alpha beta")
        m.append_index("- beta")
        m.replace_index_line("- beta", "- BETA")   # exact match wins
        lines = read(m.index_path).rstrip("\n").split("\n")
        self.assertEqual(lines, ["- alpha beta", "- BETA"])

    def test_replace_rejects_without_writing(self):
        m = mem()
        m.append_index("- only line")
        out = m.replace_index_line("no such line", "- new")
        self.assertIn("rejected", out)
        self.assertEqual(read(m.index_path), "- only line\n")

    def test_shrink_guard_rejects_then_force_overrides(self):
        m = mem()
        m.rewrite_index("\n".join(f"- e{i}" for i in range(20)), force=True)
        out = m.rewrite_index("- just one line")
        self.assertIn("rejected", out)
        self.assertEqual(m.index_stats()[0], 20)   # nothing was written
        self.assertIsNone(m.rewrite_index("- just one line", force=True))
        self.assertEqual(m.index_stats()[0], 1)

    def test_shrink_guard_exempts_small_indexes(self):
        m = mem()
        m.rewrite_index("- a\n- b\n- c")           # under the 8-line floor
        self.assertIsNone(m.rewrite_index("- a"))


class ReadPathTest(unittest.TestCase):
    """README §1 "Harness-side machinery" staleness injection and §1
    "Retrieval": grep is the only retrieval there is, bounded."""

    def test_staleness_notice_on_aged_memory(self):
        m = mem(session_dates={"s1": "2023/05/01 (Mon) 10:00"},
                question_date="2023/05/20")
        m.create_topic_file("t.md", "body", origin_session_id="s1")
        out = m.read_file("t.md")
        self.assertIn("19 days old", out)

    def test_no_notice_when_fresh_or_undated(self):
        m = mem(session_dates={"s1": "2023/05/18"},
                question_date="2023/05/20")
        m.create_topic_file("fresh.md", "body", origin_session_id="s1")
        self.assertNotIn("STALENESS", m.read_file("fresh.md"))
        self.assertLessEqual(2, STALENESS_DAYS)
        m2 = mem()                                  # no question_date at all
        m2.create_topic_file("t.md", "body", origin_session_id="s1")
        self.assertNotIn("STALENESS", m2.read_file("t.md"))

    def test_grep_literal_and_regex(self):
        m = mem()
        m.append_index("- tokens refresh every 15 min")
        m.create_topic_file("t.md", "a+b is literal here")
        self.assertIn("MEMORY.md:1", m.grep("refresh"))
        self.assertIn("t.md", m.grep("a+b"))        # literal-first
        self.assertIn("MEMORY.md", m.grep("tok.ns"))  # regex fallback
        self.assertIn("no matches", m.grep("zzz-absent"))

    def test_grep_bounded(self):
        m = mem()
        for i in range(GREP_MAX_MATCHES + 20):
            m.append_index(f"- needle {i}")
        out = m.grep("needle").split("\n")
        self.assertEqual(len(out), GREP_MAX_MATCHES + 1)
        self.assertIn("truncated", out[-1])

    def test_path_escape_rejected(self):
        m = mem()
        with self.assertRaises(ValueError):
            m.read_file("../../etc/passwd")


class HelperTest(unittest.TestCase):
    def test_strip_handles_plain_text(self):
        self.assertEqual(strip_frontmatter_and_comments("- plain"), "- plain")


if __name__ == "__main__":
    unittest.main(verbosity=2)
