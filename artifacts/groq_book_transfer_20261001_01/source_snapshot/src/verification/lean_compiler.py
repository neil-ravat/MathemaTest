#!/usr/bin/env python3
"""
Lean 4 Compiler Bridge for MathemaTest Phase C.

Provides formal verification of mathematical proofs by:
1. Compiling Lean 4 code
2. Detecting compilation errors
3. Feeding errors back to the self-correction loop

Requires: Lean 4 installed (elan/lake toolchain)
"""

import subprocess
import tempfile
import logging
import re
import os
import uuid
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, Any, List, Optional, Tuple

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from openai import OpenAI
from src.config.settings import get_settings, Settings


logger = logging.getLogger(__name__)


@dataclass
class LeanCompilationResult:
    """Result of Lean 4 compilation.
    
    verification_type can be:
    - "COMPILED_UNREVIEWED": Compiler accepted code; theorem fidelity and axioms unreviewed
    - "VERIFIED_STRUCTURE": Statement-only diagnostic, never proof success
    - "TOOLCHAIN_ERROR": Real compiler unavailable; no simulated verification
    - "FAIL_LEAN": Compilation failed
    - "FAIL_STRUCTURE": Even skeleton with sorry failed
    """
    success: bool
    code: str
    output: str
    errors: List[str]
    warnings: List[str]
    error_locations: List[Dict[str, Any]]
    verification_type: str = "FAIL_LEAN"  # Default to failure



@dataclass
class LeanProofAttempt:
    """A single proof verification attempt."""
    attempt_number: int
    lean_code: str
    result: LeanCompilationResult
    correction_prompt: Optional[str] = None


class Lean4Compiler:
    """Lean 4 compiler interface for theorem verification.
    
    Uses the mathematest/ Mathlib project for compilation with lake build.
    """
    
    # Mathlib-aware prelude for generated files
    MATHLIB_PRELUDE = """/-
  MathemaTest Generated Theorem
  Uses Mathlib for formal verification
-/

import Mathlib.Tactic
import Mathlib.Data.Real.Basic
import Mathlib.Data.Nat.Basic
import Mathlib.Data.Int.Basic

open Real Set Function

"""
    
    # Legacy standalone prelude (no Mathlib)
    LEAN_PRELUDE = """-- MathemaTest Generated
-- Standalone Lean 4 (no Mathlib)

"""
    
    # Lean binary path from elan installation
    LEAN_PATH = Path.home() / ".elan" / "bin" / "lean"
    LAKE_PATH = Path.home() / ".elan" / "bin" / "lake"
    
    # Path to Mathlib project (relative to MATHEMATEST root)
    MATHLIB_PROJECT_DIR = Path(__file__).parent.parent.parent / "mathematest"
    VERIFICATION_DIR = MATHLIB_PROJECT_DIR / "Mathematest" / "Verification"
    
    def __init__(self, lean_project_path: Optional[Path] = None, use_mathlib: bool = True,
                 settings: Optional[Settings] = None):
        """Initialize Lean 4 compiler.
        
        Args:
            lean_project_path: Path to existing Lean 4 project. If None, uses mathematest/.
            use_mathlib: If True, uses lake build with Mathlib project.
        """
        self.settings = settings or get_settings()
        if self.settings.lean_binary:
            self.LEAN_PATH = Path(self.settings.lean_binary).resolve()
        if self.settings.lake_binary:
            self.LAKE_PATH = Path(self.settings.lake_binary).resolve()
        self.lean_project_path = lean_project_path or self.MATHLIB_PROJECT_DIR
        self.use_mathlib = use_mathlib
        self.openai = self.settings.create_openai_client()
        
        # Set up environment with elan PATH
        self.env = dict(os.environ)
        elan_bin = str(Path.home() / ".elan" / "bin")
        if elan_bin not in self.env.get("PATH", ""):
            self.env["PATH"] = f"{elan_bin}:{self.env.get('PATH', '')}"
        
        # Ensure Verification directory exists
        self.VERIFICATION_DIR = self.lean_project_path / "Mathematest" / "Verification"
        self.VERIFICATION_DIR.mkdir(parents=True, exist_ok=True)
        
        # Check if Lean is available
        self.lean_available = self._check_lean_installation()
        self.mathlib_available = self._check_mathlib_available()
        
    def _check_lean_installation(self) -> bool:
        """Check if Lean 4 is installed."""
        try:
            lean_cmd = str(self.LEAN_PATH) if self.LEAN_PATH.exists() else "lean"
            result = subprocess.run(
                [lean_cmd, "--version"],
                capture_output=True,
                text=True,
                timeout=10,
                env=self.env,
            )
            if result.returncode == 0:
                logger.info(f"Lean 4 found: {result.stdout.strip()}")
                return True
        except (subprocess.SubprocessError, FileNotFoundError):
            pass
        
        logger.warning("Lean 4 not installed - formal verification unavailable")
        return False
    
    def _check_mathlib_available(self) -> bool:
        """Check if Mathlib project is properly set up."""
        lakefile = self.lean_project_path / "lakefile.toml"
        lake_packages = self.lean_project_path / ".lake" / "packages"
        
        if lakefile.exists() and lake_packages.exists():
            logger.info(f"Mathlib project found at {self.lean_project_path}")
            return True
        
        logger.warning(f"Mathlib project not found at {self.lean_project_path}")
        return False
    
    def compile(self, lean_code: str, use_prelude: bool = True, use_mathlib: bool = None, *, trusted_code: bool = False) -> LeanCompilationResult:
        """Compile Lean 4 code and return result.
        
        Args:
            lean_code: Lean 4 code to compile.
            use_prelude: Whether to prepend the standard prelude. 
                        Auto-disabled if code already starts with 'import'.
            use_mathlib: If True, uses lake build with Mathlib. Defaults to self.use_mathlib.
            
        Returns:
            LeanCompilationResult with success/failure details.
        """
        use_mathlib = use_mathlib if use_mathlib is not None else self.use_mathlib
        
        # Auto-detect if code already has imports - don't add prelude if so
        code_stripped = lean_code.strip()
        has_imports = code_stripped.startswith("import ") or "\nimport " in code_stripped[:100]
        
        if has_imports:
            # Code has its own imports - use directly without prelude
            use_prelude = False
            logger.debug("Code has imports - skipping prelude")
        
        if not trusted_code:
            return LeanCompilationResult(False, lean_code,
                'Host execution of unreviewed Lean is disabled',
                ['Use an isolated execution service for model-generated code'], [], [], 'EXECUTION_DISABLED')

        if use_mathlib and self.mathlib_available:
            # Use Mathlib prelude for lake build
            full_code = (self.MATHLIB_PRELUDE + lean_code) if use_prelude else lean_code
            return self._run_lake_build(full_code)
        else:
            # Fallback to standalone compilation
            full_code = (self.LEAN_PRELUDE + lean_code) if use_prelude else lean_code
            
            if not self.lean_available:
                return LeanCompilationResult(False, full_code, "Lean is not installed", ["Lean toolchain unavailable; no simulation performed"], [], [], "TOOLCHAIN_ERROR")
            
            return self._run_lean_compiler(full_code)
    
    def _run_lake_build(self, lean_code: str) -> LeanCompilationResult:
        """Run lake build on a file in the Mathlib project.
        
        Use a unique module per request so concurrent jobs cannot overwrite input.
        """
        module = "Run" + uuid.uuid4().hex
        temp_path = self.VERIFICATION_DIR / f"{module}.lean"
        module_name = f"Mathematest.Verification.{module}"
        
        try:
            # Write the lean code (overwrites existing Temp.lean)
            with open(temp_path, "w") as f:
                f.write(lean_code)
            
            # Run lake build from the project root
            lake_cmd = str(self.LAKE_PATH) if self.LAKE_PATH.exists() else "lake"
            result = subprocess.run(
                [lake_cmd, "build", module_name],
                capture_output=True,
                text=True,
                timeout=180,  # Increased timeout for Mathlib imports
                cwd=str(self.lean_project_path),
                env=self.env,
            )
            
            errors = self._parse_lean_errors(result.stdout + result.stderr)
            warnings = self._parse_lean_warnings(result.stdout + result.stderr)
            error_locations = self._extract_error_locations(result.stdout + result.stderr)
            
            return LeanCompilationResult(
                success=result.returncode == 0 and not errors and not re.search(r"\b(sorry|admit|axiom)\b", lean_code),
                verification_type=("FAIL_LEAN" if result.returncode != 0 or errors else
                                   "INCOMPLETE_PROOF" if re.search(r"\b(sorry|admit|axiom)\b", lean_code)
                                   else "COMPILED_UNREVIEWED"),
                code=lean_code,
                output=result.stdout + result.stderr,
                errors=errors,
                warnings=warnings,
                error_locations=error_locations,
            )
            
        except subprocess.TimeoutExpired:
            return LeanCompilationResult(
                success=False,
                code=lean_code,
                output="Lake build timed out",
                errors=["Lake build timed out after 180 seconds"],
                warnings=[],
                error_locations=[],
            )
        finally:
            temp_path.unlink(missing_ok=True)
    
    def _create_skeleton_code(self, lean_code: str) -> str:
        """Replace proof content with sorry to create skeleton code.
        
        Preserves imports and theorem statements, replaces proof bodies with sorry.
        """
        import re
        
        # Pattern 1: Match `:= by <tactic_block>` and replace with `:= by sorry`
        skeleton = re.sub(
            r':=\s*by\s+[\s\S]*?(?=\n(?:theorem|lemma|example|def|#|$)|\Z)',
            ':= by sorry',
            lean_code,
            flags=re.MULTILINE
        )
        
        # Pattern 2: Match `:= <proof_term>` (not `by`) and replace with `:= sorry`
        skeleton = re.sub(
            r':=\s+(?!by\s)[\s\S]*?(?=\n(?:theorem|lemma|example|def|#|$)|\Z)',
            ':= sorry',
            skeleton,
            flags=re.MULTILINE
        )
        
        return skeleton
    
    def compile_with_skeleton_fallback(self, lean_code: str, *, trusted_code: bool = False) -> LeanCompilationResult:
        """Compile Lean code with skeleton fallback for structure verification.
        
        Strategy:
        1. Try to compile the full proof
        2. If that fails, create a skeleton (replace proofs with sorry)
        3. Try to compile the skeleton
        
        Returns:
            LeanCompilationResult with verification_type:
            - COMPILED_UNREVIEWED: Code compiled; statement fidelity not established
            - VERIFIED_STRUCTURE: Only skeleton compiled (theorem statement valid)
            - FAIL_STRUCTURE: Even skeleton failed (real syntax/type error)
        """
        # Step 1: Try full proof
        full_result = self.compile(lean_code, trusted_code=trusted_code)
        if full_result.verification_type in {"EXECUTION_DISABLED", "TOOLCHAIN_ERROR"}:
            return full_result
        
        if full_result.success:
            # Full proof compiled!
            return LeanCompilationResult(
                success=True,
                code=lean_code,
                output=full_result.output,
                errors=[],
                warnings=full_result.warnings,
                error_locations=[],
                verification_type=full_result.verification_type,
            )
        
        # Step 2: Full proof failed - try skeleton
        logger.info("Full proof failed, attempting skeleton verification...")
        skeleton_code = self._create_skeleton_code(lean_code)
        
        # If skeleton is same as original (no proof to replace), fail
        if skeleton_code.strip() == lean_code.strip():
            logger.warning("Could not create skeleton - no proof body found")
            return LeanCompilationResult(
                success=False,
                code=lean_code,
                output=full_result.output,
                errors=full_result.errors,
                warnings=full_result.warnings,
                error_locations=full_result.error_locations,
                verification_type="FAIL_LEAN",
            )
        
        skeleton_result = self.compile(skeleton_code, trusted_code=trusted_code)
        
        if skeleton_result.verification_type == "INCOMPLETE_PROOF" and not skeleton_result.errors:
            # Skeleton compiled - theorem structure is valid!
            logger.info("Skeleton verification succeeded - theorem structure valid")
            return LeanCompilationResult(
                success=False,  # Statement elaboration is not a completed proof
                code=skeleton_code,
                output=skeleton_result.output,
                errors=[],
                warnings=skeleton_result.warnings + ["Proof uses sorry - structure only"],
                error_locations=[],
                verification_type="VERIFIED_STRUCTURE",
            )
        else:
            # Even skeleton failed - real structural problem
            logger.error("Skeleton verification failed - theorem has structural errors")
            return LeanCompilationResult(
                success=False,
                code=skeleton_code,
                output=skeleton_result.output,
                errors=skeleton_result.errors,
                warnings=skeleton_result.warnings,
                error_locations=skeleton_result.error_locations,
                verification_type="FAIL_STRUCTURE",
            )
    
    def _run_lean_compiler(self, lean_code: str) -> LeanCompilationResult:
        """Run standalone Lean 4 compiler (without Mathlib)."""
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".lean",
            delete=False,
        ) as f:
            f.write(lean_code)
            temp_path = Path(f.name)
        
        try:
            lean_cmd = str(self.LEAN_PATH) if self.LEAN_PATH.exists() else "lean"
            result = subprocess.run(
                [lean_cmd, str(temp_path)],
                capture_output=True,
                text=True,
                timeout=60,
                env=self.env,
            )
            
            errors = self._parse_lean_errors(result.stdout + result.stderr)
            warnings = self._parse_lean_warnings(result.stdout + result.stderr)
            error_locations = self._extract_error_locations(result.stdout + result.stderr)
            
            return LeanCompilationResult(
                success=result.returncode == 0 and not errors and not re.search(r"\b(sorry|admit|axiom)\b", lean_code),
                verification_type=("FAIL_LEAN" if result.returncode != 0 or errors else
                                   "INCOMPLETE_PROOF" if re.search(r"\b(sorry|admit|axiom)\b", lean_code)
                                   else "COMPILED_UNREVIEWED"),
                code=lean_code,
                output=result.stdout + result.stderr,
                errors=errors,
                warnings=warnings,
                error_locations=error_locations,
            )
            
        except subprocess.TimeoutExpired:
            return LeanCompilationResult(
                success=False,
                code=lean_code,
                output="Compilation timed out",
                errors=["Compilation timed out after 60 seconds"],
                warnings=[],
                error_locations=[],
            )
        finally:
            temp_path.unlink(missing_ok=True)
    
    def _parse_lean_errors(self, output: str) -> List[str]:
        """Extract error messages from Lean output."""
        errors = []
        for line in output.split("\n"):
            if "error:" in line.lower():
                errors.append(line.strip())
        return errors
    
    def _parse_lean_warnings(self, output: str) -> List[str]:
        """Extract warning messages from Lean output."""
        warnings = []
        for line in output.split("\n"):
            if "warning:" in line.lower():
                warnings.append(line.strip())
        return warnings
    
    def _extract_error_locations(self, output: str) -> List[Dict[str, Any]]:
        """Extract error locations (line, column) from Lean output."""
        locations = []
        pattern = r":(\d+):(\d+):"
        
        for match in re.finditer(pattern, output):
            locations.append({
                "line": int(match.group(1)),
                "column": int(match.group(2)),
            })
        
        return locations
    
    def generate_lean_proof(
        self,
        theorem_statement: str,
        natural_language_proof: Optional[str] = None,
    ) -> str:
        """Generate Lean 4 code from theorem statement.
        
        Args:
            theorem_statement: Natural language theorem.
            natural_language_proof: Optional proof outline.
            
        Returns:
            Lean 4 code.
        """
        prompt = f"""Convert this mathematical theorem to Lean 4 code with a proof.

THEOREM: {theorem_statement}
"""
        if natural_language_proof:
            prompt += f"\nPROOF OUTLINE: {natural_language_proof}"
        
        prompt += """

Generate Lean 4 code with a complete proof. Do not use sorry, admit, or new axioms.

```lean
"""
        
        response = self.openai.chat.completions.create(
            model=self.settings.default_model,
            messages=[
                {"role": "system", "content": "You are a Lean 4 expert. Generate syntactically correct Lean 4 code."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=500,
            temperature=0.2,
        )
        
        content = response.choices[0].message.content
        
        # Extract code block
        if "```lean" in content:
            code = content.split("```lean")[1].split("```")[0]
        elif "```" in content:
            code = content.split("```")[1].split("```")[0]
        else:
            code = content
        
        return code.strip()
    
    def verify_with_self_correction(
        self,
        theorem_statement: str,
        natural_language_proof: Optional[str] = None,
        max_attempts: int = 3,
    ) -> Tuple[bool, List[LeanProofAttempt]]:
        """Verify theorem with self-correction loop.
        
        Args:
            theorem_statement: Theorem to prove.
            natural_language_proof: Optional proof outline.
            max_attempts: Maximum correction attempts.
            
        Returns:
            Tuple of (success, list of attempts).
        """
        attempts = []
        current_code = None
        
        for attempt_num in range(1, max_attempts + 1):
            logger.info(f"Verification attempt {attempt_num}/{max_attempts}")
            
            if attempt_num == 1:
                # Initial generation
                current_code = self.generate_lean_proof(
                    theorem_statement,
                    natural_language_proof,
                )
            else:
                # Self-correction based on previous errors
                prev_attempt = attempts[-1]
                current_code = self._generate_correction(
                    theorem_statement,
                    prev_attempt.lean_code,
                    prev_attempt.result.errors,
                )
            
            # Compile
            result = self.compile(current_code)
            
            attempt = LeanProofAttempt(
                attempt_number=attempt_num,
                lean_code=current_code,
                result=result,
            )
            attempts.append(attempt)
            
            if result.success:
                logger.info(f"Code compiled on attempt {attempt_num}; proof statement and axioms still need review")
                return True, attempts
            
            logger.warning(f"Attempt {attempt_num} failed: {result.errors}")
        
        logger.error(f"Failed to verify after {max_attempts} attempts")
        return False, attempts
    
    def _generate_correction(
        self,
        theorem_statement: str,
        failed_code: str,
        errors: List[str],
    ) -> str:
        """Generate corrected Lean code based on compiler errors.
        
        Args:
            theorem_statement: Original theorem.
            failed_code: Code that failed to compile.
            errors: List of compilation errors.
            
        Returns:
            Corrected Lean 4 code.
        """
        prompt = f"""The following Lean 4 code failed to compile:

```lean
{failed_code}
```

ERRORS:
{chr(10).join(errors)}

ORIGINAL THEOREM: {theorem_statement}

Fix the errors and provide corrected Lean 4 code. Do not use sorry, admit, or new axioms.

```lean
"""
        
        response = self.openai.chat.completions.create(
            model=self.settings.default_model,
            messages=[
                {"role": "system", "content": "You are a Lean 4 expert. Fix compilation errors."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=500,
            temperature=0.2,
        )
        
        content = response.choices[0].message.content
        
        # Extract code block
        if "```lean" in content:
            code = content.split("```lean")[1].split("```")[0]
        elif "```" in content:
            code = content.split("```")[1].split("```")[0]
        else:
            code = content
        
        return code.strip()


def main():
    """Test the Lean 4 compiler bridge."""
    import argparse
    
    logging.basicConfig(level=logging.INFO)
    
    parser = argparse.ArgumentParser(description="Lean 4 Compiler Bridge")
    parser.add_argument("--theorem", type=str, help="Theorem to verify")
    parser.add_argument("--test", action="store_true", help="Run tests")
    args = parser.parse_args()
    
    compiler = Lean4Compiler()
    
    if args.test:
        # Test cases
        test_theorems = [
            "For all real numbers a and b, (a + b)² = a² + 2ab + b²",
            "The derivative of sin(x) is cos(x)",
            "If n is even, then n² is even",
        ]
        
        print("=" * 60)
        print("LEAN 4 COMPILER BRIDGE TEST")
        print("=" * 60)
        print(f"Lean Available: {compiler.lean_available}")
        print()
        
        for thm in test_theorems:
            print(f"Theorem: {thm}")
            success, attempts = compiler.verify_with_self_correction(thm, max_attempts=2)
            print(f"  Success: {success}")
            print(f"  Attempts: {len(attempts)}")
            if attempts:
                last = attempts[-1]
                print(f"  Errors: {last.result.errors[:2]}")
            print()
    
    elif args.theorem:
        success, attempts = compiler.verify_with_self_correction(args.theorem)
        print(f"Success: {success}")
        for a in attempts:
            print(f"\nAttempt {a.attempt_number}:")
            print(f"Code:\n{a.lean_code[:200]}...")
            print(f"Errors: {a.result.errors}")


if __name__ == "__main__":
    main()
