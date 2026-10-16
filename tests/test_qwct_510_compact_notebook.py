"""Notebook transport/size regressions. No generated candles or native proof."""
import ast
import importlib.util
import json
from pathlib import Path

import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('_q510compact_builder',ROOT/'tools/build_qwct_compact_notebook.py')
builder=importlib.util.module_from_spec(spec); spec.loader.exec_module(builder)


def helpers():
    tree=ast.parse(builder.COMPACT.read_text())
    # Load definitions/payload, never execute the trading research or QC imports.
    tree.body=[node for node in tree.body if not isinstance(node,ast.Expr)]
    ns={}
    exec(compile(tree,str(builder.COMPACT),'exec'),ns)
    return ns


def test_transport_is_reproducible_and_source_is_byte_identical():
    code,notebook=builder.build()
    assert code==builder.COMPACT.read_text()
    assert notebook==builder.NOTEBOOK.read_text()
    assert helpers()['_qwct510_source']().encode()==builder.SOURCE.read_bytes()


def test_corrupted_payload_does_not_execute():
    ns=helpers()
    ns['_qwct510_sha256']='0'*64
    with pytest.raises(ValueError,match='CHECKSUM_MISMATCH'):
        ns['_qwct510_source']()


def test_whole_notebook_is_below_limit_with_output_and_frontend_reserve():
    notebook=builder.NOTEBOOK.read_text()
    data=json.loads(notebook)
    assert len(data['cells'])==1 and data['cells'][0]['outputs']==[]
    assert data['cells'][0]['execution_count'] is None
    assert ''.join(data['cells'][0]['source'])==builder.COMPACT.read_text()
    # Check complete JSON, not Python source file or one cell in isolation.
    assert len(notebook)+builder.OUTPUT_BUDGET+4000<64000
    # Also bound a more verbose serializer than the shipped indent=1.
    assert len(json.dumps(data,ensure_ascii=True,indent=4))+builder.OUTPUT_BUDGET+1000<64000


def test_many_logs_are_bounded_and_omission_is_explicit_with_end_retained():
    ns=helpers()
    lines=['QWCT 5.10 START {"can_trade":false}']
    lines += ['QWCT 5.10 GATES_8 '+json.dumps({'symbol':'TEST_METADATA_ONLY','note':'x'*200}) for _ in range(1000)]
    lines += ['QWCT 5.10 END {"orders":"DISABLED","tvx_pass":false}']
    result=ns['_qwct510_lines']('\n'.join(lines))
    assert sum(ns['_qwct510_cost'](line) for line in result)<=builder.OUTPUT_BUDGET
    assert result[0].startswith('QWCT 5.10 START ')
    assert result[-1].startswith('QWCT 5.10 END ')
    assert any('OUTPUT_OMITTED' in x and 'NOT_A_DATA_PASS' in x for x in result)


def test_all_fourteen_values_and_unknown_subfields_survive_compaction():
    ns=helpers()
    features={f'g{i:02}':{'value':None,'reason':'UNKNOWN','detail':{'market_aligned':None,'other':'details'}} for i in range(1,15)}
    text='QWCT 5.10 FEATURES_14 '+json.dumps({'features':features})
    result=ns['_qwct510_lines'](text)
    value=json.loads(result[0].split(' ',3)[3])
    assert len(value['features'])==14
    assert all(v['value'] is None and v['unavailable_subfields']['market_aligned'] is None for v in value['features'].values())
    assert value['details_omitted_for_notebook_size'] is True


def test_native_error_stays_a_visible_failure_not_a_pass():
    ns=helpers()
    result=ns['_qwct510_lines']('',error='ImportError: TEST_ONLY')
    assert 'LOADER_ERROR' in result[0] and '"can_trade": false' in result[0]
    assert not any('END' in x for x in result)


def test_saved_output_json_size_budget_counts_unicode_escaping():
    ns=helpers()
    # Metadata text only; deliberately worst-case saved JSON escaping.
    text='\n'.join('QWCT 5.10 BLOCKED '+json.dumps({'reason':'Неизвестно '*100,'can_trade':False},ensure_ascii=False) for _ in range(100))
    output=ns['_qwct510_lines'](text)
    notebook=json.loads(builder.NOTEBOOK.read_text())
    notebook['cells'][0]['execution_count']=1
    notebook['cells'][0]['outputs']=[{'output_type':'stream','name':'stdout','text':[x+'\n' for x in output]}]
    assert len(json.dumps(notebook,ensure_ascii=True,indent=4))+1000<64000


def test_frontend_separate_stream_objects_still_fit_with_metadata_reserve():
    ns=helpers()
    text='\n'.join('QWCT 5.10 GATES_8 '+json.dumps({'can_trade':False,'reason':'x'*150}) for _ in range(1000))
    output=ns['_qwct510_lines'](text)
    notebook=json.loads(builder.NOTEBOOK.read_text())
    notebook['cells'][0]['outputs']=[{'output_type':'stream','name':'stdout','text':[line+'\n']} for line in output]
    assert len(json.dumps(notebook,ensure_ascii=True,indent=4))+1000<64000
