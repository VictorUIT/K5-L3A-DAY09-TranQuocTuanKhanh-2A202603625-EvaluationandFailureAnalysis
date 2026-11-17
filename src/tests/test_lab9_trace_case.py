"""Regression test for the trace case in docs/trace_case.md.

seeded_regression C-008@11: Lab 8's grader PASSES, the ledger holds 20.000đ (approval cap) but the
reply tells the customer 35.000đ (FM-08). ReplyMatchesLedger must fail it, and pass the same
claim@seed on `fixed`, where the reply quotes the ledger.
"""
import pytest

pytestmark = pytest.mark.student


def _grade(shape: str):
    from pydantic_evals.evaluators import EvaluatorContext

    from lab9.graders import ReplyMatchesLedger
    from lab9.trace_case import investigate

    case = investigate(shape, "C-008", 11)
    ctx = EvaluatorContext(name="C-008@11", inputs={}, metadata=None, expected_output=case["label"],
                           output=case["trial"], duration=0.0, _span_tree=None, attributes={}, metrics={})
    return case["trial"], ReplyMatchesLedger().evaluate(ctx)


def test_c008_misreport_slips_past_lab8_but_not_reply_matches_ledger():
    trial, res = _grade("seeded_regression")
    assert trial["lab8_pass"] is True                     # the old grader is fooled
    assert trial["snapshot"]["refund_vnd"] == 20000       # the ledger is right
    assert res.value is False                             # the reply is not
    assert "35000" in res.reason and "20000" in res.reason


def test_c008_fixed_reply_quotes_the_ledger():
    trial, res = _grade("fixed")
    assert trial["snapshot"]["refund_vnd"] == 20000
    assert res.value is True
