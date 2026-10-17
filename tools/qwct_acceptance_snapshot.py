"""Read-only acceptance snapshot from existing user-supplied QWCT Cloud evidence.

This is NOT a backtest, signal classifier or strategy change. It makes the
previously observed June 3 evidence auditable without treating omitted output
as a zero, an unexecuted gate as PASS, or source heuristics as Gerchik truth.
"""
from __future__ import annotations

from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
QC = ROOT / "research" / "chart_review_qc"
D10 = QC / "QWCT_5_10_USER_RUNTIME_RESULT_2026_10_16.json"
D12 = QC / "QWCT_5_12_USER_RUNTIME_RESULT_2026_10_17.json"
AUTHOR = QC / "QWCT_5_2_AUTHOR_LABELED_M5_EVENTS.json"
PREDICTIONS = QC / "QWCT_5_2_NATIVE_M5_PREDICTIONS.json"
SYMBOLS = ("AMAT", "NFLX", "SRPT", "MSFT")
FEATURES = tuple(f"g{i:02d}" for i in range(1, 15))
SOURCE = "USER_SUPPLIED_CLOUD_STDOUT_NOT_INDEPENDENT_AGENT_RUN"


def _load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _require(ok, label):
    if not ok:
        raise ValueError("EVIDENCE_CONTRACT_FAIL:" + label)


def summarize(d10, d12, author, predictions):
    """Return facts supported by archived stdout, never inferred successes."""
    _require(d10.get("schema_version") == "QWCT_5_10_USER_RUNTIME_RESULT_V1", "5_10_SCHEMA")
    _require(d12.get("schema_version") == "QWCT_5_12_USER_RUNTIME_RESULT_V1", "5_12_SCHEMA")
    _require(d10.get("evidence_source") == SOURCE and
             d12.get("evidence_source") == SOURCE, "EVIDENCE_SOURCE")
    _require(d10.get("symbols") is not None and d12.get("symbols") is not None,
             "SYMBOLS_MISSING")
    _require(set(d10["symbols"]) == set(SYMBOLS) and
             set(d12["symbols"]) == set(SYMBOLS), "COHORT_DIFFERENT")
    _require(d10.get("session") == d12.get("session") == "2024-06-03",
             "DIFFERENT_FROZEN_SESSION")
    _require(author.get("schema_version") == "QWCT_5_2_DIRECT_AUTHOR_M5_LABELS_V1",
             "AUTHOR_SCHEMA")
    _require(predictions.get("schema_version") == "QWCT_5_2_NATIVE_M5_PREDICTIONS_V1",
             "PREDICTION_SCHEMA")
    _require(type(author.get("events")) is list and
             type(predictions.get("bars")) is list, "AUTHOR_DATA_FORMAT")
    n_features, errors, obs, expected, missing = 0, 0, 0, 0, {}
    for ticker in SYMBOLS:
        a, b = d10["symbols"][ticker], d12["symbols"][ticker]
        feats = a.get("feature_values")
        _require(isinstance(feats, dict) and set(feats) == set(FEATURES),
                 ticker + "_FEATURE_IDENTITIES")
        _require(all(type(feats[k]) is bool or feats[k] is None for k in FEATURES),
                 ticker + "_FEATURE_TYPES")
        _require(isinstance(a.get("feature_errors"), list),
                 ticker + "_FEATURE_ERRORS_MISSING")
        n_features += len(feats)
        errors += len(a["feature_errors"])
        coverage = a.get("m5_coverage", {})
        have, want = coverage.get("observed"), coverage.get("expected")
        _require(type(have) is int and type(want) is int and 0 <= have <= want,
                 ticker + "_M5_COUNTS")
        gaps = coverage.get("missing")
        _require(isinstance(gaps, list) and len(gaps) == want - have,
                 ticker + "_M5_GAPS_NOT_ACCOUNTED")
        obs += have
        expected += want
        missing[ticker] = gaps
        _require(b.get("kind") == "mirror" and b.get("source") == "swing_cluster",
                 ticker + "_D1_SOURCE_CHANGED")
        scores = b.get("scores")
        cutoff = b.get("min_model_score")
        _require(isinstance(scores, dict) and
                 set(scores) == {"breakout", "bounce", "false_breakout"} and
                 type(cutoff) in (int, float) and
                 all(type(v) in (int, float) and v < cutoff
                     for v in scores.values()), ticker + "_D1_REJECTION_NOT_PROVEN")
        _require(a.get("gates_note") == "NO_CANONICAL_GATE_EVALUATION" and
                 a.get("all_eight_gate_count_maps_empty") is True,
                 ticker + "_GATES_NOT_KNOWN")
        _require(a.get("conditional_sec_queries") == 0, ticker + "_TVX_UNEXPECTED")
        _require(a.get("bsu", {}).get("status") == "UNAVAILABLE",
                 ticker + "_BSU_UNEXPECTED")
    _require(d12.get("summary") == {"accepted": 0, "rejected": 4, "blocked": 0},
             "D1_ACCEPTANCE_CHANGED")
    _require(n_features == d10["computed_from_shared_counts"]["feature_results"] == 56,
             "FEATURE_COUNT_MISMATCH")
    _require(obs == d10["computed_from_shared_counts"]["m5_observed"] == 311 and
             expected == d10["computed_from_shared_counts"]["m5_expected"] == 312,
             "M5_COVERAGE_MISMATCH")
    _require(missing == {"AMAT": [], "NFLX": [],
                         "SRPT": ["2024-06-03T13:10:00"], "MSFT": []},
             "GAP_IDENTITY_MISMATCH")
    _require(d10.get("output_omitted_from_stdout") ==
             {"D1": 4, "FIXED_FLOATING": 4, "REACTIONS_10": 4},
             "OMITTED_OUTPUT_MISMATCH")
    _require(d10.get("orders") == d12.get("orders") == "DISABLED" and
             d10.get("risk_gate") == "UNCHANGED" and
             d12.get("can_trade") is False, "NO_ORDER_CONTRACT")
    return {
        "evidence_source": SOURCE,
        "session": "2024-06-03",
        "subjects": list(SYMBOLS),
        "D1": {"accepted": 0, "rejected": 4, "model_threshold": 4.0,
               "post_mirror_fix_cloud_parity": "NOT_RETESTED"},
        "features_14": {"results_observed": n_features,
                        "calculation_errors": errors,
                        "author_accuracy": "NOT_MEASURED"},
        "native_M5": {"observed": obs, "expected": expected,
                      "missing": missing,
                      "strict_coverage_pass": obs == expected},
        "ten_reactions": "OUTPUT_OMITTED_NOT_EVALUATED_HERE",
        "fixed_floating": "OUTPUT_OMITTED_NOT_EVALUATED_HERE",
        "gates_8": "NOT_EVALUATED_NO_ACCEPTED_SETUP",
        "TVX_minus_30s": "NOT_EVALUATED_NO_SECOND_QUERIES",
        "author": {"direct_m5_labels": len(author["events"]),
                   "matched_native_predictions": 0,
                   "accuracy": "NOT_MEASURABLE"},
        "risk_certification": "NOT_CERTIFIED",
        "orders": "DISABLED",
        "holdout": "NOT_RUN",
        "can_trade": False,
    }


def main():
    report = summarize(_load(D10), _load(D12),
                       _load(AUTHOR), _load(PREDICTIONS))
    print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False))


if __name__ == "__main__":
    main()
