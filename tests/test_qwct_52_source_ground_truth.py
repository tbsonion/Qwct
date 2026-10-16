"""QWCT 5.2 — regression of evidence gates only; NO author-labeled case fixtures.

Synthetic test rows exercise the scorer's arithmetic. They are never
written to the real author-label JSON and never measure Gerchik accuracy.
"""
import importlib.util
import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

ROOT=Path(__file__).resolve().parents[1]
DIR=ROOT/"research/chart_review_qc"
SCRIPT=DIR/"QWCT_5_2_AUTHOR_ACCURACY_EVALUATOR.py"
spec=importlib.util.spec_from_file_location("_q52_eval",SCRIPT)
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
ET=ZoneInfo("America/New_York")


def author_row(i=0,positive=None,negative=None):
    at=datetime(2024,6,3,10,0,tzinfo=ET)+timedelta(minutes=5*i)
    return {
        "market":"US_EQUITY","symbol":"DUMMY_TEST_ONLY",
        "bar_end_iso":at.isoformat(),"level_price":100.0,
        "side":"long","timeframe":"M5",
        "source_role":"DIRECT_ALEXANDER_GERCHIK",
        "independent_review":True,
        "author_chart_or_video_verified":True,
        "source_url":"https://example.test/SYNTHETIC_NOT_REAL_EVIDENCE",
        "source_event_locator":"TEST-ONLY",
        "level_provenance":"TEST_D1_FROZEN",
        "level_frozen_before_bar_iso":datetime(2024,6,2,16,0,tzinfo=ET).isoformat(),
        "positive_kinds":positive or [],
        "negative_kinds":negative or [],
    }


def pred_row(row,values=None):
    return {k:row[k] for k in (
        "market","symbol","bar_end_iso","level_price","side")} | {
        "timeframe":"M5","native_completed_bar":True,
        "level_frozen_before_bar":True,
        "predicted_kinds":values or [],
    }


def test_real_source_catalog_is_editorial_and_never_direct_author_accuracy():
    d=json.loads((DIR/"QWCT_5_2_OFFICIAL_EDITORIAL_REFERENCE_CASES.json").read_text(encoding="utf-8"))
    assert len(d["cases"])==10
    assert set(x["kind"] for x in d["cases"])==m.KINDS
    assert all(not c["author_direct_label"] for c in d["cases"])
    assert all(not c["replayable_in_current_us_quantconnect"] for c in d["cases"])
    assert all(not c["has_native_event_timestamp"] for c in d["cases"])
    assert all(c["url"].startswith("https://gerchik.com/") for c in d["cases"])
    assert all(c["source_role"].startswith("GTE_") for c in d["cases"])


def test_real_author_groundtruth_is_empty_and_scoring_says_not_measurable():
    a=json.loads((DIR/"QWCT_5_2_AUTHOR_LABELED_M5_EVENTS.json").read_text(encoding="utf-8"))
    b=json.loads((DIR/"QWCT_5_2_NATIVE_M5_PREDICTIONS.json").read_text(encoding="utf-8"))
    assert a["events"]==[] and b["bars"]==[]
    result=m.evaluate(a["events"],b["bars"])
    assert result["accuracy_status"]=="NOT_MEASURABLE_YET"
    assert result["summary"]["matched_bars"]==0
    assert all(x["precision"] is None and x["recall"] is None
               for x in result["by_kind"].values())


def test_editorial_label_and_future_frozen_level_are_forbidden():
    a=author_row(positive=["BOUNCE"])
    a["source_role"]="GTE_EDITORIAL"
    with pytest.raises(ValueError,match="NOT_DIRECT_AUTHOR"):
        m.validate_truth(a)
    a["source_role"]="DIRECT_ALEXANDER_GERCHIK"
    a["level_frozen_before_bar_iso"]=a["bar_end_iso"]
    with pytest.raises(ValueError,match="LOOKAHEAD"):
        m.validate_truth(a)


def test_unreviewed_kinds_cannot_be_assumed_negatives():
    a=author_row(positive=["BOUNCE"])
    pred=pred_row(a,["BOUNCE","CHOP"])
    report=m.evaluate([a],[pred])
    assert report["by_kind"]["BOUNCE"]["TP"]==1
    assert report["by_kind"]["CHOP"]["FP"]==0  # Not reviewed -> unknown
    assert report["by_kind"]["BOUNCE"]["precision"] is None
    assert report["accuracy_status"]=="NOT_MEASURABLE_YET"


def test_missing_native_prediction_is_unknown_not_false_negative():
    a=author_row(positive=["BOUNCE"])
    r=m.evaluate([a],[])
    assert r["summary"]["unmatched_bars"]==1
    assert r["by_kind"]["BOUNCE"]["FN"]==0


def test_full_reviewed_multi_label_confusion_and_minimum_sample_threshold():
    rows=[]
    predictions=[]
    for i in range(10):
        a=author_row(i,positive=["BOUNCE"] if i<5 else [],
                     negative=[] if i<5 else ["BOUNCE"])
        rows.append(a)
        predictions.append(pred_row(a,["BOUNCE"] if i in (0,1,2,5) else []))
    out=m.evaluate(rows,predictions)
    x=out["by_kind"]["BOUNCE"]
    assert x["status"]=="SCOREABLE"
    assert (x["TP"],x["FN"],x["FP"],x["TN"])==(3,2,1,4)
    assert x["precision"]==0.75
    assert x["recall"]==0.6
    assert out["by_kind"]["CHOP"]["status"]=="INSUFFICIENT_AUTHOR_LABELS"


def test_hard_fail_on_duplicate_wrong_tf_conflicting_source_and_bad_prediction():
    a=author_row(positive=["BOUNCE"])
    with pytest.raises(ValueError,match="DUPLICATE_AUTHOR_CASE"):
        m.evaluate([a,a],[pred_row(a)])
    with pytest.raises(ValueError,match="CONTRADICTORY"):
        m.validate_truth(author_row(
            positive=["BOUNCE"],negative=["BOUNCE"]))
    with pytest.raises(ValueError,match="NOT_M5"):
        m.validate_truth({**a,"timeframe":"D1"})
    with pytest.raises(ValueError,match="DUPLICATE_NATIVE_PREDICTION_ROW"):
        m.evaluate([a],[pred_row(a),pred_row(a)])
    with pytest.raises(ValueError,match="UNVERIFIED_NATIVE_BAR_OR_LEVEL"):
        m.validate_prediction({**pred_row(a),"native_completed_bar":False})
    with pytest.raises(ValueError,match="M5_EXACT_CLOSED"):
        m.validate_truth({**a,"bar_end_iso":"2024-06-03T10:03:00-04:00"})


# Metadata-only regression: no new market bars or author labels are created.
@pytest.mark.parametrize('url', [
    'https://gerchik.co/docs/TORGOVLYA_AKTSIYAMI.pdf',
    'http://www.GERCHIK.co/docs/TORGOVLYA_AKTSIYAMI.pdf?download=1#page=25',
    'https://gerchik.co/docs/TORGOVLYA_%41KTSIYAMI.pdf',
    'https://gerchik.com/pdf/algoritm_forts.pdf',
    'https://gerchik.com/torgovye-patterny/bsu-bpu-teoriya/',
    'https://mybook.ru/author/aleksandr-gerchik/kurs-aktivnogo-trejdera/read/?page=9',
])
def test_known_guest_editorial_or_concept_cannot_be_promoted_by_true_flags(url):
    with pytest.raises(ValueError, match='KNOWN_SOURCE_NOT_DIRECT_AUTHOR_M5'):
        m.validate_truth({**author_row(positive=['BOUNCE']), 'source_url': url})


def test_all_existing_editorial_references_are_excluded_even_if_relabelled():
    catalog=json.loads((DIR/'QWCT_5_2_OFFICIAL_EDITORIAL_REFERENCE_CASES.json').read_text())
    for case in catalog['cases']:
        with pytest.raises(ValueError, match='KNOWN_SOURCE_NOT_DIRECT_AUTHOR_M5'):
            m.validate_truth({**author_row(positive=['BOUNCE']), 'source_url': case['url']})


def test_provenance_exclusion_does_not_block_entire_official_domain():
    # Unknown resource is NOT verified by this test; all old gates still apply.
    row={**author_row(positive=['BOUNCE']),
         'source_url':'https://gerchik.co/TEST_ONLY_UNREVIEWED_RESOURCE'}
    m.validate_truth(row)
    with pytest.raises(ValueError, match='NOT_DIRECT_AUTHOR'):
        m.validate_truth({**row, 'independent_review':False})


def test_missing_provenance_registry_fails_closed(monkeypatch):
    original=Path.read_text
    def read(path,*args,**kwargs):
        if path.name=='QWCT_5_9_SOURCE_PROVENANCE.json':
            raise FileNotFoundError('test-only missing registry')
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'read_text',read)
    with pytest.raises(ValueError, match='SOURCE_PROVENANCE_REGISTRY_UNAVAILABLE'):
        m.validate_truth(author_row(positive=['BOUNCE']))


@pytest.mark.parametrize('content', [
    'not json',
    '[]',
    '{"schema_version":"WRONG","sources":[]}',
    '{"schema_version":"QWCT_5_9_SOURCE_PROVENANCE_V1","sources":[]}',
    '{"schema_version":"QWCT_5_9_SOURCE_PROVENANCE_V1","sources":[{}]}',
    '{"schema_version":"QWCT_5_9_SOURCE_PROVENANCE_V1","sources":[{"url":"https://example.test","source_role":"UNKNOWN","direct_m5_ground_truth_eligible":true}]}',
])
def test_broken_registry_cannot_silently_disable_exclusion(monkeypatch,content):
    original=Path.read_text
    def read(path,*args,**kwargs):
        return content if path.name=='QWCT_5_9_SOURCE_PROVENANCE.json' else original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'read_text',read)
    with pytest.raises(ValueError, match='SOURCE_PROVENANCE_REGISTRY_UNAVAILABLE'):
        m.validate_truth(author_row(positive=['BOUNCE']))
