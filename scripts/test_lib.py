#!/usr/bin/env python3
"""Regression tests for the pairing guard in lib.py.

    python3 scripts/test_lib.py
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import assert_aligned, mcnemar  # noqa: E402


def rows(ids, key="qa_id", **extra):
    return [{key: i, "correct": True, **extra} for i in ids]


class PairingGuardTest(unittest.TestCase):
    def test_aligned_rows_pass(self):
        a, b = rows("xyz"), rows("xyz")
        self.assertTrue(assert_aligned(a, b))

    def test_single_field_mismatch_fires(self):
        with self.assertRaises(AssertionError):
            assert_aligned(rows("xyz"), rows("xzy"))

    def test_idless_rows_are_refused_not_waved_through(self):
        a = [{"correct": True}, {"correct": False}]
        b = [{"correct": False}, {"correct": True}]
        with self.assertRaises(AssertionError):
            mcnemar(a, b)

    def test_every_present_field_is_checked(self):
        # qa_index matches but conv_id does not: must still fire, because a
        # per-cluster index cannot vouch for alignment alone.
        a = [{"qa_index": 0, "conv_id": "c1", "correct": True},
             {"qa_index": 0, "conv_id": "c2", "correct": True}]
        b = [{"qa_index": 0, "conv_id": "c2", "correct": True},
             {"qa_index": 0, "conv_id": "c1", "correct": True}]
        with self.assertRaises(AssertionError):
            assert_aligned(a, b)

    def test_length_mismatch_fires(self):
        with self.assertRaises(AssertionError):
            assert_aligned(rows("xy"), rows("xyz"))


if __name__ == "__main__":
    unittest.main(verbosity=1)
