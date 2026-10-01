"""Actual compiler smoke checks, with known statements and explicit axiom output.

No LLM calls or Mathlib required. These are engineering fixtures, not paper results.
"""
import json
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.config.settings import Settings
from src.verification.lean_compiler import Lean4Compiler


def main():
    binary = ROOT / '.tools/lean-4.26.0-darwin_aarch64/bin/lean'
    settings = Settings(_env_file=None, openai_api_key='unused', lean_binary=str(binary))
    compiler = Lean4Compiler(use_mathlib=False, settings=settings)
    cases = [
        ('addition', 'theorem local_add (n : Nat) : n + 0 = n := by rfl\n#print axioms local_add', True),
        ('logic', 'theorem local_and (p q : Prop) : p ∧ q → p := fun h => h.left\n#print axioms local_and', True),
        ('false_statement', 'theorem false_claim : (1 : Nat) + 1 = 3 := by rfl', False),
        ('unfinished', 'theorem unfinished_claim : False := by sorry\n#print axioms unfinished_claim', False),
        ('new_axiom', 'axiom assumed_false : False\ntheorem assumed_claim : False := assumed_false\n#print axioms assumed_claim', False),
    ]
    outputs = []
    for name, code, expected in cases:
        result = compiler.compile(code, use_prelude=False, use_mathlib=False, trusted_code=True)
        assert result.success == expected, (name, result)
        if expected:
            assert 'does not depend on any axioms' in result.output, result.output
        outputs.append({'case': name, 'expected_compilation_success': expected, 'result': asdict(result)})
        print(name, result.success, result.verification_type)
    report = {'lean_version': subprocess.check_output([str(binary), '--version'], text=True).strip(),
              'scope': 'Known engineering fixtures; no mathematical textbook claims tested', 'cases': outputs}
    path = ROOT / 'artifacts/local_lean_checks.json'
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(report, indent=2)+'\n')
    print('Saved', path)


if __name__ == '__main__':
    main()
