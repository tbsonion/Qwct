"""QWCT 5.2 — source-grounded, *independent* M5 label comparison.

No market orders, threshold tuning or synthetic market data.
GTE editorial examples are helpful qualitative references, not direct
Alexander Gerchik-labeled timestamped market bars. Never count them as
author accuracy observations.

Predictions must explicitly cover every reviewed bar, even when no tags
were emitted. A missing prediction is UNKNOWN rather than a false negative.
"""
from collections import defaultdict
from datetime import datetime, timezone
from math import isfinite
from pathlib import Path
import json
from urllib.parse import unquote, urlsplit

KINDS = frozenset((
    "BOUNCE", "WICK_BOUNCE", "WICK_RECLAIM", "FALSE_BREAK_1BAR",
    "FALSE_BREAK_2BAR", "BREAK_FOLLOWTHROUGH", "MIRROR_RETEST",
    "COMPRESSION", "CONSOLIDATION", "CHOP",
))
MIN_POSITIVES_PER_KIND = 5
MIN_NEGATIVES_PER_KIND = 5


def _date(value):
    at = datetime.fromisoformat(value)
    if at.tzinfo is None or at.utcoffset() is None:
        raise ValueError("EXACT_TIMEZONE_REQUIRED")
    if at.second or at.microsecond or at.minute % 5:
        raise ValueError("M5_EXACT_CLOSED_BAR_END_REQUIRED")
    return at.astimezone(timezone.utc)


def _key(record):
    for name in ("market", "symbol", "bar_end_iso",
                 "level_price", "side"):
        if name not in record:
            raise ValueError("INCOMPLETE_BAR_IDENTITY: " + name)
    at = _date(record["bar_end_iso"])
    try:
        level = float(record["level_price"])
    except (ValueError,TypeError,OverflowError):
        raise ValueError("INVALID_FROZEN_PRICE") from None
    if not isfinite(level) or level <= 0:
        raise ValueError("INVALID_FROZEN_PRICE")
    if record["side"] not in ("long", "short"):
        raise ValueError("INVALID_FROZEN_ROLE")
    if not record["market"] or not record["symbol"]:
        raise ValueError("INVALID_MARKET_OR_SYMBOL")
    # Exact normalized tick-grid source price is part of join key.
    return (record["market"],record["symbol"],at,level,record["side"])


def _kinds(values):
    if not isinstance(values,list) or len(set(values)) != len(values):
        raise ValueError("INVALID_OR_DUPLICATE_REACTION_KINDS")
    if not set(values) <= KINDS:
        raise ValueError("UNKNOWN_REACTION_KIND")
    return set(values)


def _source_identity(url):
    parts = urlsplit(url)
    host = (parts.hostname or "").lower().removeprefix("www.")
    return host, unquote(parts.path).rstrip("/")


def _validate_known_source(url):
    """A caller's True flags cannot override reviewed contrary provenance.

    This is an exclusion registry, not automatic verification of other URLs.
    Read on each validation so a missing/broken sibling cannot silently
    disable the gate. It is used only by this offline research evaluator.
    """
    path = Path(__file__).with_name("QWCT_5_9_SOURCE_PROVENANCE.json")
    try:
        registry = json.loads(path.read_text(encoding="utf-8"))
        if registry["schema_version"] != "QWCT_5_9_SOURCE_PROVENANCE_V1":
            raise ValueError("INVALID_SCHEMA")
        sources = registry["sources"]
        if not isinstance(sources, list) or not sources:
            raise ValueError("EMPTY_REGISTRY")
        for source in sources:
            if (not isinstance(source["url"], str)
                    or source["direct_m5_ground_truth_eligible"] is not False
                    or not source["source_role"]):
                raise ValueError("INVALID_ENTRY")
        denied = {_source_identity(source["url"]) for source in sources}
    except (OSError, ValueError, TypeError, KeyError):
        raise ValueError("SOURCE_PROVENANCE_REGISTRY_UNAVAILABLE") from None
    if _source_identity(url) in denied:
        raise ValueError("KNOWN_SOURCE_NOT_DIRECT_AUTHOR_M5_GROUND_TRUTH")


def validate_truth(row):
    """Demand independently demonstrated direct author provenance."""
    key = _key(row)
    positive = _kinds(row.get("positive_kinds"))
    negative = _kinds(row.get("negative_kinds"))
    if not positive.isdisjoint(negative):
        raise ValueError("CONTRADICTORY_AUTHOR_LABEL")
    if not positive and not negative:
        raise ValueError("UNREVIEWED_AUTHOR_LABEL")
    if row.get("timeframe") != "M5":
        raise ValueError("AUTHOR_LABEL_NOT_M5")
    if (row.get("source_role") != "DIRECT_ALEXANDER_GERCHIK"
            or row.get("independent_review") is not True
            or row.get("author_chart_or_video_verified") is not True
            or not row.get("source_url")
            or not row.get("source_event_locator")
            or not row.get("level_provenance")):
        raise ValueError("NOT_DIRECT_AUTHOR_GROUND_TRUTH")
    if not row.get("source_url","").startswith(("https://","http://")):
        raise ValueError("AUTHOR_SOURCE_URL_REQUIRED")
    _validate_known_source(row["source_url"])
    freeze = _date(row["level_frozen_before_bar_iso"])
    if freeze >= key[2]:
        raise ValueError("LOOKAHEAD_LEVEL_FREEZE")
    return key, positive, negative


def validate_prediction(row):
    key=_key(row)
    if (row.get("timeframe") != "M5"
            or row.get("native_completed_bar") is not True
            or row.get("level_frozen_before_bar") is not True):
        raise ValueError("UNVERIFIED_NATIVE_BAR_OR_LEVEL")
    return key,_kinds(row.get("predicted_kinds"))


def evaluate(truth_rows, prediction_rows):
    """Precision/recall on the SAME labeled bar and SAME frozen price only.

    Unreviewed kinds are NOT treated as negative examples. If there are no
    enough true author-labeled bars, numeric percentages remain withheld.
    """
    predictions={}
    for row in prediction_rows:
        key, tags=validate_prediction(row)
        if key in predictions:
            raise ValueError("DUPLICATE_NATIVE_PREDICTION_ROW")
        predictions[key]=tags

    score=defaultdict(lambda:dict(TP=0,FP=0,FN=0,TN=0))
    summary=dict(author_rows=0,matched_bars=0,
                 unmatched_bars=0,author_labels=0)
    seen=set()
    for row in truth_rows:
        key,positive,negative=validate_truth(row)
        if key in seen:
            raise ValueError("DUPLICATE_AUTHOR_CASE")
        seen.add(key)
        summary["author_rows"] += 1
        summary["author_labels"] += len(positive)+len(negative)
        if key not in predictions:
            summary["unmatched_bars"] += 1
            continue
        summary["matched_bars"] += 1
        tags=predictions[key]
        for kind in positive:
            score[kind]["TP" if kind in tags else "FN"] += 1
        for kind in negative:
            score[kind]["FP" if kind in tags else "TN"] += 1

    by_kind={}
    for kind in sorted(KINDS):
        counts=dict(score[kind])
        pos=counts["TP"]+counts["FN"]
        neg=counts["FP"]+counts["TN"]
        sufficient=(pos>=MIN_POSITIVES_PER_KIND and
                    neg>=MIN_NEGATIVES_PER_KIND)
        denom=counts["TP"]+counts["FP"]
        by_kind[kind]={
            **counts, "evaluated_positive":pos,"evaluated_negative":neg,
            "status":"SCOREABLE" if sufficient else "INSUFFICIENT_AUTHOR_LABELS",
            "precision":round(counts["TP"]/denom,4)
                if sufficient and denom else None,
            "recall":round(counts["TP"]/pos,4)
                if sufficient and pos else None,
        }
    return {"summary":summary,"by_kind":by_kind,
            "accuracy_status":("POTENTIALLY_MEASURABLE"
              if any(x["status"]=="SCOREABLE" for x in by_kind.values())
              else "NOT_MEASURABLE_YET")}


def main():
    base=Path(__file__).resolve().parent
    reference=json.loads((base/"QWCT_5_2_OFFICIAL_EDITORIAL_REFERENCE_CASES.json").read_text(encoding="utf-8"))
    truth=json.loads((base/"QWCT_5_2_AUTHOR_LABELED_M5_EVENTS.json").read_text(encoding="utf-8"))
    preds=json.loads((base/"QWCT_5_2_NATIVE_M5_PREDICTIONS.json").read_text(encoding="utf-8"))
    report=evaluate(truth["events"],preds["bars"])
    print("QWCT 5.2 SOURCE AUDIT",
          "GTE_EDITORIAL_OR_CONCEPT_REFS=",len(reference["cases"]),
          "DIRECT_AUTHOR_M5_LABELS=",report["summary"]["author_labels"],
          "MATCHED_NATIVE_BARS=",report["summary"]["matched_bars"],
          "STATUS=",report["accuracy_status"],"NO_ORDERS")
    for kind,x in report["by_kind"].items():
        print("QWCT 5.2",kind,x["status"],
              "TP=",x["TP"],"FP=",x["FP"],"FN=",x["FN"],"TN=",x["TN"],
              "PRECISION=",x["precision"],"RECALL=",x["recall"])


if __name__=="__main__":
    main()
