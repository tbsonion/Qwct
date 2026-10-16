"""Package the exact reviewed notebook source below QC's 64,000-char limit.

Compression is for notebook transport only. No network download, rule
changes or price generation. SHA256 verifies the readable source before exec.
"""
import base64
import hashlib
import json
from pathlib import Path
import textwrap
import zlib

ROOT=Path(__file__).resolve().parents[1]
DIR=ROOT/'research/chart_review_qc'
SOURCE=DIR/'QWCT_5_10_PIPELINE_ACCEPTANCE_ONE_CELL.py'
COMPACT=DIR/'QWCT_5_10_COMPACT_ONE_CELL.py'
NOTEBOOK=DIR/'QWCT_5_10_COMPACT.ipynb'
LIMIT=64000
OUTPUT_BUDGET=10000

HELPERS=r'''

def _qwct510_source():
    raw = zlib.decompress(base64.b64decode(_qwct510_payload, validate=True))
    if hashlib.sha256(raw).hexdigest() != _qwct510_sha256:
        raise ValueError("QWCT_SOURCE_CHECKSUM_MISMATCH: nothing executed")
    return raw.decode("utf-8")


def _qwct510_cost(line):
    # Count escaped notebook JSON, not only the visible text length.
    return len(json.dumps({"output_type":"stream", "name":"stdout", "text":line+"\n"}, ensure_ascii=True))


def _qwct510_lines(text, error=None):
    rows=[]
    priority={"START":0,"END":0,"BLOCKED":1,"LOADER_ERROR":0,
              "FEATURES_14":2,"PIPELINE_EXAMPLE":2,"GATES_8":3,
              "M5_COVERAGE":3,"BSU":3}
    for raw in text.splitlines():
        if not raw.strip():
            continue
        label="CAPTURED_MESSAGE"
        value={"message":raw[:200],"truncated":len(raw)>200}
        if raw.startswith("QWCT 5.10 "):
            try:
                label,encoded=raw[len("QWCT 5.10 "):].split(" ",1)
                value=json.loads(encoded)
                if not isinstance(value,dict):
                    raise ValueError("NON_OBJECT_LOG")
            except (ValueError,TypeError):
                label="UNPARSED_LOG"
                value={"message":raw[:200],"can_trade":False}
        if label=="FEATURES_14":
            for feature in value.get("features",{}).values():
                detail=feature.pop("detail",{})
                unavailable={k:v for k,v in detail.items() if v is None}
                if unavailable:
                    feature["unavailable_subfields"]=unavailable
            value["details_omitted_for_notebook_size"]=True
        if label=="PIPELINE_EXAMPLE":
            for gate in value.get("gates",{}).values():
                reason=gate.get("reason","")
                if len(reason)>140:
                    gate["reason"]=reason[:140]
                    gate["reason_truncated"]=True
        line="QWCT 5.10 "+label+" "+json.dumps(value,ensure_ascii=False,sort_keys=True)
        rows.append((priority.get(label,4),len(rows),label,line))
    if error:
        line="QWCT 5.10 LOADER_ERROR "+json.dumps({"reason":error[:250],"can_trade":False})
        rows.append((0,len(rows),"LOADER_ERROR",line))
    used=0; kept=[]; omitted={}
    for rank,index,label,line in sorted(rows):
        cost=_qwct510_cost(line)
        if used+cost<=_qwct510_output_budget-1024:
            kept.append((index,line)); used+=cost
        else:
            omitted[label]=omitted.get(label,0)+1
    result=[line for _,line in sorted(kept)]
    if omitted:
        notice="QWCT 5.10 OUTPUT_OMITTED "+json.dumps({"counts":omitted,
             "reason":"NOTEBOOK_SIZE_BUDGET_NOT_A_DATA_PASS","can_trade":False},sort_keys=True)
        # Keep the final END easy to find; truncation is always explicit.
        end=next((i for i,x in enumerate(result) if x.startswith("QWCT 5.10 END ")),len(result))
        result.insert(end,notice)
    return result


def _qwct510_run():
    source=_qwct510_source()
    captured=io.StringIO(); error=None
    try:
        with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured):
            exec(compile(source,"QWCT_5_10_REVIEWED_SOURCE","exec"),globals())
    except Exception as exc:
        error=type(exc).__name__+": "+str(exc)
    print("\n".join(_qwct510_lines(captured.getvalue(),error)))

_qwct510_run()
'''


def build():
    raw=SOURCE.read_bytes()
    encoded=base64.b64encode(zlib.compress(raw,9)).decode('ascii')
    header='''# QWCT 5.10.1: use as the ONLY cell in a fresh research.ipynb.
# First export the old notebook as backup; do not append to its old cells.
# Exact reviewed code, compressed only to fit QuantConnect save size.
# Readable source: QWCT_5_10_PIPELINE_ACCEPTANCE_ONE_CELL.py on GitHub.
# Offline transport, no network download. SHA256 checked before execution.
# All strategy thresholds, NO_ORDERS and NOT_TVX_PASS remain unchanged.
import base64, contextlib, hashlib, io, json, zlib
'''
    code=header+'_qwct510_sha256 = '+repr(hashlib.sha256(raw).hexdigest())+'\n'
    code+='_qwct510_output_budget = '+str(OUTPUT_BUDGET)+'\n'
    code+='_qwct510_payload = (\n'+''.join('    '+repr(line)+'\n' for line in textwrap.wrap(encoded,100)) + ')\n'
    code+=HELPERS
    notebook={"cells":[{"cell_type":"code","execution_count":None,"id":"qwct-510-compact",
              "metadata":{},"outputs":[],"source":code.splitlines(keepends=True)}],
              "metadata":{"kernelspec":{"display_name":"Python 3","language":"python","name":"python3"},
                          "language_info":{"name":"python","version":"3.11.0"}},
              "nbformat":4,"nbformat_minor":5}
    notebook_text=json.dumps(notebook,ensure_ascii=True,indent=1)+'\n'
    # Reserve a conservative extra 4KB for output framing/frontend metadata.
    if len(notebook_text)+OUTPUT_BUDGET+4000>=LIMIT:
        raise ValueError('NOTEBOOK_WITH_OUTPUT_RESERVE_EXCEEDS_QC_LIMIT')
    return code,notebook_text


if __name__=='__main__':
    code,notebook=build()
    COMPACT.write_text(code,encoding='utf-8')
    NOTEBOOK.write_text(notebook,encoding='utf-8')
    print(f'Compact cell: {len(code)} chars; full ipynb JSON: {len(notebook)} chars; output reserve: {OUTPUT_BUDGET}; hard limit: {LIMIT}')
