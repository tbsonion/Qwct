"""Move immutable reviewed code out of notebook JSON into ONE Cloud module.

The notebook stores imports only. No external download or new package.
"""
import ast
import base64
import bz2
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DIR=ROOT/'research/chart_review_qc'
RUNNER=DIR/'qwct_pipeline_runner.py'
CELL=DIR/'QWCT_5_11_RUN_CELL.py'
NOTEBOOK=DIR/'QWCT_5_11_RESEARCH.ipynb'
SOURCE=DIR/'QWCT_5_10_PIPELINE_ACCEPTANCE_ONE_CELL.py'
PY_LIMIT=32000
NB_LIMIT=64000
OUTPUT_BUDGET=16000


def build():
    spec=importlib.util.spec_from_file_location('_q511_compact_source',ROOT/'tools/build_qwct_compact_notebook.py')
    mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    helpers=mod.HELPERS.replace('_qwct510','_qwct511')
    helpers=helpers.replace('zlib.decompress','bz2.decompress')
    helpers=helpers.replace('"START":0,"END":0,"BLOCKED":1', '"D1":0,"START":0,"END":0,"BLOCKED":1')
    helpers=helpers.replace('def _qwct511_run():\n', 'def _qwct511_run():\n    global last_raw_output, last_error\n')
    helpers=helpers.replace('    print("\\n".join(_qwct511_lines(captured.getvalue(),error)))',
         '    last_raw_output=captured.getvalue()\n    last_error=error\n    print("\\n".join(_qwct511_lines(last_raw_output,error)))')
    tree=ast.parse(helpers)
    tree.body=[node for node in tree.body if not isinstance(node,ast.Expr)]
    helpers=ast.unparse(tree)+'\n'
    raw=SOURCE.read_bytes()
    payload=base64.b64encode(bz2.compress(raw,9)).decode('ascii')
    code='# QWCT 5.11 Cloud helper. Save as qwct_pipeline_runner.py in PROJECT ROOT.\n'
    code+='# Reviewed source is SHA256 checked. No orders. No network download.\n'
    code+='import base64,bz2,contextlib,hashlib,io,json\n'
    code+='_qwct511_sha256='+repr(hashlib.sha256(raw).hexdigest())+'\n'
    code+='_qwct511_output_budget='+str(OUTPUT_BUDGET)+'\n'
    code+='_qwct511_payload='+repr(payload)+'\nlast_raw_output=""\nlast_error=None\n'
    code+=helpers
    code+='\ndef run():\n    print("QWCT 5.11 RUNNER: MODULE_LOADED NO_ORDERS NOTEBOOK_STORES_IMPORTS_ONLY")\n    _qwct511_run()\n'
    cell='# QWCT 5.11: use ONLY this cell; remove old cells/outputs first.\nimport importlib\nimport qwct_pipeline_runner\nimportlib.reload(qwct_pipeline_runner)\nqwct_pipeline_runner.run()\n'
    nb={'cells':[{'cell_type':'code','execution_count':None,'id':'qwct-511','metadata':{},'outputs':[],
          'source':cell.splitlines(keepends=True)}],
        'metadata':{'kernelspec':{'display_name':'Python 3','language':'python','name':'python3'}},
        'nbformat':4,'nbformat_minor':5}
    notebook=json.dumps(nb,ensure_ascii=True,indent=1)+'\n'
    if max(len(code),len(code.encode('utf-8')))>=PY_LIMIT:
        raise ValueError('CLOUD_HELPER_EXCEEDS_32K')
    if len(notebook)>2000 or len(notebook)+OUTPUT_BUDGET*3+2000>=NB_LIMIT:
        raise ValueError('NOTEBOOK_OUTPUT_HEADROOM_INSUFFICIENT')
    ast.parse(code); ast.parse(cell)
    return code,cell,notebook


if __name__=='__main__':
    code,cell,notebook=build()
    RUNNER.write_text(code,encoding='utf-8')
    CELL.write_text(cell,encoding='utf-8')
    NOTEBOOK.write_text(notebook,encoding='utf-8')
    print(f'Cloud helper {len(code)} chars; cell {len(cell)} chars; full notebook {len(notebook)} chars')
