"""Acceptance checks on archived REAL user-supplied Cloud stdout.

These tests establish report integrity, NOT independent native LEAN replay.
No synthetic market candles, mock price histories, fills or brokerage calls.
"""
from copy import deepcopy
from pathlib import Path
import json

import pytest

from tools.qwct_acceptance_snapshot import QC, summarize

ROOT = Path(__file__).resolve().parents[1]


def sources():
    read = lambda name: json.loads((QC / name).read_text(encoding="utf-8"))
    return [
        read("QWCT_5_10_USER_RUNTIME_RESULT_2026_10_16.json"),
        read("QWCT_5_12_USER_RUNTIME_RESULT_2026_10_17.json"),
        read("QWCT_5_2_AUTHOR_LABELED_M5_EVENTS.json"),
        read("QWCT_5_2_NATIVE_M5_PREDICTIONS.json"),
    ]


def test_513_actual_stdout_reports_56_features_and_real_gap_not_acceptance():
    report = summarize(*sources())
    assert report["evidence_source"].startswith("USER_SUPPLIED_")
    assert report["features_14"]["results_observed"] == 56
    assert report["features_14"]["calculation_errors"] == 0
    assert report["native_M5"]["observed"] == 311
    assert report["native_M5"]["expected"] == 312
    assert report["native_M5"]["strict_coverage_pass"] is False
    assert report["native_M5"]["missing"]["SRPT"] == ["2024-06-03T13:10:00"]
    assert report["D1"]["accepted"] == 0
    assert report["D1"]["rejected"] == 4
    assert report["D1"]["post_mirror_fix_cloud_parity"] == "NOT_RETESTED"
    assert report["gates_8"] == "NOT_EVALUATED_NO_ACCEPTED_SETUP"
    assert report["TVX_minus_30s"] == "NOT_EVALUATED_NO_SECOND_QUERIES"
    assert "OMITTED" in report["ten_reactions"]
    assert "OMITTED" in report["fixed_floating"]
    assert report["author"]["accuracy"] == "NOT_MEASURABLE"
    assert report["risk_certification"] == "NOT_CERTIFIED"
    assert report["orders"] == "DISABLED"
    assert report["can_trade"] is False


@pytest.mark.parametrize("item,field,value,expected", [
    (0, "evidence_source", "INDEPENDENT_TESTED", "EVIDENCE_SOURCE"),
    (0, "session", "2024-06-04", "DIFFERENT_FROZEN_SESSION"),
    (1, "session", "2024-06-04", "DIFFERENT_FROZEN_SESSION"),
    (0, "orders", "ENABLED", "NO_ORDER_CONTRACT"),
    (1, "can_trade", True, "NO_ORDER_CONTRACT"),
])
def test_evidence_metadata_tampering_fails_closed(item, field, value, expected):
    src = sources()
    src[item][field] = value
    with pytest.raises(ValueError, match=expected):
        summarize(*src)


def test_missing_feature_identity_cannot_pass_as_fourteen():
    src = sources()
    del src[0]["symbols"]["AMAT"]["feature_values"]["g14"]
    with pytest.raises(ValueError, match="AMAT_FEATURE_IDENTITIES"):
        summarize(*src)


def test_missing_srpt_candle_cannot_be_silently_fill_forwarded():
    src = sources()
    src[0]["symbols"]["SRPT"]["m5_coverage"]["missing"] = []
    with pytest.raises(ValueError, match="SRPT_M5_GAPS_NOT_ACCOUNTED"):
        summarize(*src)


def test_seemingly_positive_d1_score_invalidates_frozen_rejection_report():
    src = sources()
    src[1]["symbols"]["NFLX"]["scores"]["bounce"] = 4.0
    with pytest.raises(ValueError, match="NFLX_D1_REJECTION_NOT_PROVEN"):
        summarize(*src)


def test_absent_eight_gates_do_not_mean_eight_passes():
    src = sources()
    src[0]["symbols"]["AMAT"]["all_eight_gate_count_maps_empty"] = False
    with pytest.raises(ValueError, match="AMAT_GATES_NOT_KNOWN"):
        summarize(*src)


def test_sec_query_must_be_documented_not_guessed():
    src = sources()
    src[0]["symbols"]["MSFT"]["conditional_sec_queries"] = 1
    with pytest.raises(ValueError, match="MSFT_TVX_UNEXPECTED"):
        summarize(*src)


def test_new_author_cases_require_separate_5_2_evaluation_not_auto_certification():
    src = sources()
    src[2]["events"] = [{"unvalidated": "not a source case"}]
    with pytest.raises(ValueError, match="AUTHOR_SNAPSHOT_CHANGED"):
        summarize(*src)


def test_snapshots_are_not_live_brokerage_or_market_data_tests():
    report = summarize(*sources())
    assert report["holdout"] == "NOT_RUN"
    assert report["can_trade"] is False
    assert report["D1"]["post_mirror_fix_cloud_parity"] != "PASS"
    assert report["author"]["direct_m5_labels"] == 0
