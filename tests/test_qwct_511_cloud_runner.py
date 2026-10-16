"""Cloud module/notebook transport and log priorities; no invented market data."""
import importlib.util
import json
from pathlib import Path
import sys

import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('_q511builder',ROOT/'tools/build_qwct_pipeline_runner.py')
b=importlib.util.module_from_spec(spec); spec.loader.exec_module(b)


def runner():
    spec=importlib.util.spec_from_file_location('_q511helper',b.RUNNER)
    mod=importlib.util.module_from_spec(spec); sys.modules[spec.name]=mod
    spec.loader.exec_module(mod)
    return mod


def test_one_cloud_helper_and_entire_import_only_notebook_fit_limits():
    code,cell,nb=b.build()
    assert code==b.RUNNER.read_text() and cell==b.CELL.read_text() and nb==b.NOTEBOOK.read_text()
    assert len(code.encode())<32000
    assert len(code.replace("\n","\r\n").encode())<32000
    assert len(cell)<300 and len(nb)<1000
    assert len(nb)+b.OUTPUT_BUDGET*3+2000<64000
    data=json.loads(nb)
    assert len(data['cells'])==1 and data['cells'][0]['outputs']==[]
    assert '_payload' not in ''.join(data['cells'][0]['source'])
    assert len(code)>len(cell)*100  # payload stays in MODULE, never notebook source.


def test_readable_source_is_identical_and_import_does_not_execute_it(capsys):
    mod=runner()
    assert capsys.readouterr().out==''
    assert mod.last_raw_output=='' and mod.last_error is None
    assert mod._qwct511_source().encode()==b.SOURCE.read_bytes()


def test_corruption_is_detected_before_native_code_runs():
    mod=runner(); mod._qwct511_sha256='0'*64
    with pytest.raises(ValueError,match='CHECKSUM_MISMATCH'):
        mod._qwct511_source()


def test_d1_rejection_records_are_not_dropped_by_other_verbose_logs():
    mod=runner()
    noisy=['QWCT 5.10 FEATURES_14 '+json.dumps({'symbol':'TEST_ONLY','features':{},'padding':'x'*200}) for _ in range(300)]
    d1=['QWCT 5.10 D1 '+json.dumps({'symbol':name,'accepted':False,'rejects':['TEST_METADATA_ONLY']}) for name in ['A','B','C','D']]
    output=mod._qwct511_lines('\n'.join(noisy+d1+['QWCT 5.10 END {"can_trade":false}']))
    assert sum(x.startswith('QWCT 5.10 D1 ') for x in output)==4
    assert sum(mod._qwct511_cost(x) for x in output)<=b.OUTPUT_BUDGET
    assert any('OUTPUT_OMITTED' in x for x in output)
    assert output[-1].startswith('QWCT 5.10 END ')


def test_raw_log_is_retained_in_module_memory_not_written_into_notebook(monkeypatch,capsys):
    mod=runner()
    source='print(\'QWCT 5.10 D1 {"accepted":false,"scope":"TEST_METADATA_ONLY"}\')'
    monkeypatch.setattr(mod,'_qwct511_source',lambda: source)
    mod.run()
    assert 'TEST_METADATA_ONLY' in mod.last_raw_output and mod.last_error is None
    assert 'QWCT 5.10 D1 ' in capsys.readouterr().out
    assert 'TEST_METADATA_ONLY' not in b.NOTEBOOK.read_text()


def test_helper_error_stays_visible_and_does_not_produce_end_pass(monkeypatch,capsys):
    mod=runner()
    monkeypatch.setattr(mod,'_qwct511_source',lambda: 'raise ValueError("TEST_ONLY_FAILURE")')
    mod.run(); out=capsys.readouterr().out
    assert 'LOADER_ERROR' in out and 'TEST_ONLY_FAILURE' in out
    assert 'QWCT 5.10 END ' not in out
    assert mod.last_error=='ValueError: TEST_ONLY_FAILURE'


def test_import_only_notebook_plus_triple_escaped_outputs_fits():
    mod=runner()
    noisy='\n'.join('QWCT 5.10 BLOCKED '+json.dumps({'reason':'Неизвестно '*100,'can_trade':False},ensure_ascii=False) for _ in range(100))
    lines=mod._qwct511_lines(noisy)
    nb=json.loads(b.NOTEBOOK.read_text())
    nb['cells'][0]['outputs']=[{'name':'stdout','output_type':'stream','text':[line+'\n']} for line in lines]
    encoded=json.dumps(nb,ensure_ascii=True,indent=4)
    assert len(encoded)<24000
    assert len(json.dumps(json.dumps(encoded,ensure_ascii=True),ensure_ascii=True))+2000<64000


def test_saved_user_result_distinguishes_native_data_from_unexecuted_gates():
    result=json.loads((b.DIR/'QWCT_5_10_USER_RUNTIME_RESULT_2026_10_16.json').read_text())
    assert set(result['symbols'])=={'AMAT','NFLX','SRPT','MSFT'}
    assert sum(row['m5_coverage']['observed'] for row in result['symbols'].values())==311
    assert all(len(row['feature_values'])==14 and not row['feature_errors'] for row in result['symbols'].values())
    assert all(row['gates_note']=='NO_CANONICAL_GATE_EVALUATION' and row['conditional_sec_queries']==0 for row in result['symbols'].values())
    assert result['output_omitted_from_stdout']=={'D1':4,'FIXED_FLOATING':4,'REACTIONS_10':4}
    assert result['tvx_pass'] is False and result['author_accuracy']=='UNKNOWN'
