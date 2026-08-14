#!/usr/bin/env python3
"""Tests for chatbot.py's curation apply path, driven by stub models.

These pin the two failure modes an external review found: a rejected op
(e.g. replace_line with no matching line) must not fire the over-limit
rewrite round, and the rewrite round must refuse any op that does not
target MEMORY.md. Stdlib only:

    python3 test_chatbot.py
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ccmem  # noqa: E402
import chatbot  # noqa: E402


def stub(replies):
    """A chat_fn returning canned fenced-JSON replies in order."""
    it = iter(replies)

    def fn(messages):
        return "```json\n" + json.dumps(next(it)) + "\n```"
    return fn


def mem():
    return ccmem.CCMemory(tempfile.mkdtemp())


class RejectedOpTest(unittest.TestCase):
    def test_unmatched_replace_line_does_not_fire_rewrite_round(self):
        m = mem()
        m.append_index("- existing fact")
        # One rejected replace_line plus one valid create. If the rejection
        # leaks into the over-limit path, the stub's second reply would be
        # consumed by a rewrite round; the assertion on replies makes that
        # loud, and the index content makes it visible.
        replies = [[
            {"op": "replace_line", "path": "MEMORY.md",
             "match": "no such line", "content": "- replacement"},
            {"op": "create", "path": "topic.md", "content": "body",
             "index_line": "- topic (topic.md)", "type": "user"},
        ]]
        chatbot.curate(m, "transcript", "s1", chat_fn=stub(replies),
                       log=lambda *a: None)
        with open(m.index_path) as f:
            lines = f.read().splitlines()
        self.assertEqual(lines, ["- existing fact", "- topic (topic.md)"])
        self.assertIn("topic.md", m.list_files())

    def test_reviewer_scenario_invalid_create_cannot_overwrite_index(self):
        # The reported reproduction: a response whose only over-limit-round
        # op targets a topic file must not rewrite MEMORY.md.
        m = mem()
        for i in range(ccmem.INDEX_MAX_LINES + 1):   # genuinely over limit
            m.append_index(f"- e{i}")
        replies = [
            [{"op": "append", "path": "MEMORY.md", "content": "- one more"}],
            [{"op": "create", "path": "topic.md", "content": "NOT AN INDEX"}],
        ]
        chatbot.curate(m, "t", "s1", chat_fn=stub(replies),
                       log=lambda *a: None)
        with open(m.index_path) as f:
            body = f.read()
        self.assertNotIn("NOT AN INDEX", body)
        self.assertIn("- e0", body)

    def test_legitimate_over_limit_rewrite_still_works(self):
        m = mem()
        for i in range(ccmem.INDEX_MAX_LINES + 1):
            m.append_index(f"- e{i}")
        new_index = "\n".join(f"- kept {i}" for i in range(150))
        replies = [
            [{"op": "append", "path": "MEMORY.md", "content": "- trigger"}],
            [{"op": "update", "path": "MEMORY.md", "content": new_index}],
        ]
        chatbot.curate(m, "t", "s1", chat_fn=stub(replies),
                       log=lambda *a: None)
        self.assertEqual(m.index_stats()[0], 150)


class AnswerToolLoopTest(unittest.TestCase):
    def test_tool_round_then_answer(self):
        m = mem()
        m.append_index("- pets (pets.md)")
        m.create_topic_file("pets.md", "Cat: Miso, 4yo tortie.")
        replies = [
            "```json\n" + json.dumps([{"tool": "read", "path": "pets.md"}]) + "\n```",
            "Your cat is Miso.",
        ]
        it = iter(replies)
        out = chatbot.answer(m, [], "What's my cat's name?",
                             chat_fn=lambda msgs: next(it), log=lambda *a: None)
        self.assertEqual(out, "Your cat is Miso.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
