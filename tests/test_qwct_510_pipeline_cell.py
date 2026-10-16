"""Verify notebook code parity and metadata orchestration; no market candles."""
import ast
import importlib.util
from pathlib import Path
import sys
from types import ModuleType

import pandas as pd

from strategy.config import StrategyConfig
from strategy.pipeline_audit import audit_pipeline

ROOT=Path(__file__).resolve().parents[1]
CELL=ROOT/'research/chart_review_qc/QWCT_5_10_PIPELINE_ACCEPTANCE_ONE_CELL.py'
GENERATOR=ROOT/'tools/build_qwct_pipeline_cell.py'
spec=importlib.util.spec_from_file_location('_q510_generator',GENERATOR)
g=importlib.util.module_from_spec(spec); spec.loader.exec_module(g)


def cell_module():
    tree=ast.parse(CELL.read_text(encoding='utf-8'))
    body=[]
    for node in tree.body:
        if isinstance(node,ast.ImportFrom) and (node.module=='AlgorithmImports' or node.module.startswith('QuantConnect')):
            continue
        if isinstance(node,ast.Expr) and isinstance(node.value,ast.Call) and isinstance(node.value.func,ast.Name) and node.value.func.id=='run_qwct_pipeline_acceptance':
            continue
        body.append(node)
    module=ModuleType('_q510_notebook_metadata_only')
    sys.modules[module.__name__]=module
    exec(compile(ast.fix_missing_locations(ast.Module(body=body,type_ignores=[])),str(CELL),'exec'),module.__dict__)
    return module


def test_cell_is_reproducibly_generated_from_current_canonical_rules():
    assert g.build()==CELL.read_text(encoding='utf-8')
    tree=ast.parse(g.build())
    found={node.name:node for node in tree.body if isinstance(node,(ast.ClassDef,ast.FunctionDef))}
    for path,names in g.PARTS.items():
        for node in g.selected_nodes(path,names):
            if isinstance(node,(ast.ClassDef,ast.FunctionDef)):
                assert ast.dump(found[node.name])==ast.dump(node),(path,node.name)


def test_cell_does_not_require_extra_small_cloud_modules_or_call_orders():
    tree=ast.parse(CELL.read_text(encoding='utf-8'))
    local_modules={node.module for node in ast.walk(tree) if isinstance(node,ast.ImportFrom) and (node.module or '').startswith('strategy')}
    assert local_modules=={'strategy.config','strategy.levels','strategy.patterns_bsu'}
    assert not any(isinstance(node,ast.ImportFrom) and node.level for node in ast.walk(tree))
    calls={node.func.attr for node in ast.walk(tree) if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute)}
    assert not calls & {'market_order','limit_order','stop_market_order','stop_limit_order','liquidate','set_brokerage_model','buy','sell'}
    assert not {'requests','urllib','subprocess'} & {node.names[0].name for node in ast.walk(tree) if isinstance(node,ast.Import)}
    assert 'bpu_tvx=None' in g.DRIVER  # History cannot forge OnData evidence.


def test_bundled_feature_contract_keeps_unknown_and_rejects_truthy_nan():
    module=cell_module()
    assert module._without_exception(True,None) is None
    out=module.evaluate_all(None,None,None,None,[],StrategyConfig())
    assert len(out)==14 and all(v.value is None for v in out.values())
    rows,blockers=module.feature_snapshot(out)
    assert len(rows)==14 and len(blockers)==14
    assert len(module.gate_snapshot({})[0])==8


def test_notebook_and_offline_audit_agree_on_missing_native_evidence():
    # Metadata only: no OHLC is invented to exercise the orchestration.
    module=cell_module()
    from test_qwct_510_pipeline_audit import metadata_market,AT
    decision,market=metadata_market()
    canonical=audit_pipeline(decision,market,AT,StrategyConfig())
    bundled=module.audit_pipeline(decision,market,AT,StrategyConfig())
    assert bundled==canonical
    assert bundled['can_trade'] is False and bundled['status']=='BLOCKED'


def test_emit_converts_numpy_values_to_strict_json(capsys):
    module=cell_module()
    module._emit('TEST_METADATA_ONLY',flag=module.np.bool_(False),unknown=float('nan'))
    out=capsys.readouterr().out
    assert '"flag": false' in out and '"unknown": null' in out
    assert 'NaN' not in out


def test_reaction_role_is_frozen_price_side_not_breakout_trade_direction():
    module=cell_module()
    assert module._frozen_level_role(99,100,.01)=='short'
    assert module._frozen_level_role(101,100,.01)=='long'
    assert module._frozen_level_role(100,100,.01) is None
    assert "side=decision.side if decision.accepted" not in g.DRIVER
