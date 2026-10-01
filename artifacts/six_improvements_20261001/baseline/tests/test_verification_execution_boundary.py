from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from src.verification.lean_compiler import Lean4Compiler, LeanCompilationResult
from src.verification.verification_sandbox import SymbolicVerifier


def compiler(tmp_path):
    c=Lean4Compiler.__new__(Lean4Compiler)
    c.use_mathlib=False;c.mathlib_available=False;c.lean_available=True
    c.LEAN_PATH=Path('/nonexistent/lean');c.LAKE_PATH=Path('/nonexistent/lake')
    c.env={};c.lean_project_path=tmp_path;c.VERIFICATION_DIR=tmp_path
    return c


def test_unreviewed_code_never_reaches_subprocess(tmp_path):
    c=compiler(tmp_path)
    with patch('subprocess.run') as run:
        assert c.compile('#eval IO.println "bad"').verification_type=='EXECUTION_DISABLED'
        verifier=SymbolicVerifier.__new__(SymbolicVerifier)
        assert verifier.run_in_sandbox('raise Exception()')[0] is False
        run.assert_not_called()


def test_skeleton_elaboration_is_not_proof_and_compile_failure_wins(tmp_path):
    c=compiler(tmp_path)
    with patch('subprocess.run',return_value=SimpleNamespace(returncode=1,stdout='error: bad',stderr='')):
        result=c.compile('example : True := by sorry',trusted_code=True)
        assert result.verification_type=='FAIL_LEAN'
    c.compile=Mock(side_effect=[
        LeanCompilationResult(False,'','',['bad proof'],[],[], 'FAIL_LEAN'),
        LeanCompilationResult(False,'','',[],[],[], 'INCOMPLETE_PROOF')])
    result=c.compile_with_skeleton_fallback('theorem x : True := by trivial',trusted_code=True)
    assert result.verification_type=='VERIFIED_STRUCTURE' and not result.success


def test_mathlib_requests_have_distinct_input_files(tmp_path):
    c=compiler(tmp_path);names=[]
    def run(args,**kwargs):
        names.append(args[-1])
        return SimpleNamespace(returncode=0,stdout='',stderr='')
    with patch('subprocess.run',side_effect=run):
        c._run_lake_build('example : True := by trivial')
        c._run_lake_build('example : True := by trivial')
    assert len(set(names))==2
    assert not list(tmp_path.glob('*.lean'))
