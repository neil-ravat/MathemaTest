"""Offline regression checks for real defects, without API or database access."""
import ast
import json
import re
from pathlib import Path
from unittest.mock import Mock
import xml.etree.ElementTree as ET

import pytest

from src.config.settings import Settings
from src.verification.verdicts import parse_verdict
from src.verification.lean_compiler import Lean4Compiler, LeanCompilationResult
from scripts.prepare_openstax import extract_module, render
from scripts.run_local_pilot import query_filter, summarize


def test_verdicts_and_legacy_negation():
    value = {"status": "FAIL_GAP", "reason": "Not available yet", "missing_prerequisites": ["definition"]}
    assert parse_verdict(json.dumps(value)).status == "FAIL_GAP"
    for text in ['ERROR: missing API key', '{"status":"PASS"}', json.dumps({**value, "confidence": 1.5})]:
        with pytest.raises(ValueError):
            parse_verdict(text)
    # Import only the pure scoring function: legacy script initializes paid clients at module scope.
    tree = ast.parse(Path('scripts/benchmark_grand_matrix.py').read_text())
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'score_response')
    ns = {'re': re}
    exec(compile(ast.Module(body=[function], type_ignores=[]), 'score_response', 'exec'), ns)
    assert ns['score_response']('No, this theorem is not valid.') == 'RAW_GAP'
    assert ns['score_response']('ERROR: missing API key') == 'ERROR'
    assert ns['score_response']('Yes, valid; no missing premises.') == 'RAW_PASS'


def test_local_endpoint_and_missing_lean():
    settings = Settings(_env_file=None, openai_api_key='ollama', openai_base_url='http://127.0.0.1:11434/v1')
    client = settings.create_openai_client()
    assert str(client.base_url) == 'http://127.0.0.1:11434/v1/'
    client.close()
    compiler = Lean4Compiler.__new__(Lean4Compiler)
    compiler.use_mathlib = False
    compiler.mathlib_available = False
    compiler.lean_available = False
    result = compiler.compile('theorem x : True := by trivial', trusted_code=True)
    assert not result.success and result.verification_type == 'TOOLCHAIN_ERROR'
    assert not hasattr(compiler, '_simulate_compilation')


def test_compilation_does_not_certify_proof():
    compiler = Lean4Compiler.__new__(Lean4Compiler)
    compiler.compile = Mock(return_value=LeanCompilationResult(True, '', '', [], [], [], 'COMPILED_UNREVIEWED'))
    result = compiler.compile_with_skeleton_fallback('theorem x : True := by trivial')
    assert result.verification_type != 'VERIFIED_PROOF'


def test_math_and_exercise_extraction(tmp_path):
    math = ET.fromstring('<mfrac xmlns="http://www.w3.org/1998/Math/MathML"><mi>a</mi><mi>b</mi></mfrac>')
    assert render(math, set()) == '((a)/(b))'
    path = tmp_path / 'index.cnxml'
    path.write_text('<document xmlns="http://cnx.rice.edu/cnxml"><title>T</title><content>'
                    '<para id="before">Known prerequisite</para><exercise id="exercise">'
                    '<problem>What is 2+2?</problem><solution>SECRET ANSWER</solution>'
                    '</exercise><para id="after">Later concept</para></content></document>')
    records = extract_module(path, 'module', 2, 0, 10)
    assert [r['position'] for r in records] == [10, 11, 12]
    assert records[1]['is_target']
    assert 'SECRET ANSWER' not in records[1]['content']


def test_boundary_and_failure_denominators():
    case = {'source_id': 'edition-a', 'position': 20}
    assert query_filter(case, True) == {'$and': [
        {'source_id': 'edition-a'}, {'position': {'$ne': 20}}, {'position': {'$lt': 20}}]}
    rows = [{'arm': 'vector', 'expected': 'FAIL_GAP', 'future_items': 0, 'seconds': 1, 'run_status': 'ERROR'}]
    result = summarize(rows)['vector']
    assert result['attempts'] == result['errors'] == result['labeled_cases'] == 1
    assert result['scored'] == result['exact_fixture_matches'] == 0
