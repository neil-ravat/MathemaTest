#!/usr/bin/env python3
"""
Environment Check for Lean 4 Formal Verification.

Returns True ONLY if a real Lean 4 compiler is detected.
This is used as a gate before running formal verification.

Phase C Task 1: Physical Environment Setup.
"""

import subprocess
import sys
from pathlib import Path
from typing import Tuple, Optional
import shutil


def check_lean_version() -> Tuple[bool, Optional[str]]:
    """Check if Lean 4 is installed and return version.
    
    Returns:
        Tuple of (is_installed, version_string).
    """
    try:
        result = subprocess.run(
            ["lean", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        
        if result.returncode == 0:
            version = result.stdout.strip()
            return True, version
        
        return False, result.stderr
        
    except FileNotFoundError:
        return False, "Lean command not found"
    except subprocess.TimeoutExpired:
        return False, "Lean version check timed out"
    except Exception as e:
        return False, str(e)


def check_elan_installed() -> Tuple[bool, Optional[str]]:
    """Check if elan (Lean version manager) is installed.
    
    Returns:
        Tuple of (is_installed, path).
    """
    elan_path = shutil.which("elan")
    if elan_path:
        return True, elan_path
    return False, None


def check_lake_installed() -> Tuple[bool, Optional[str]]:
    """Check if lake (Lean build tool) is installed.
    
    Returns:
        Tuple of (is_installed, path).
    """
    lake_path = shutil.which("lake")
    if lake_path:
        return True, lake_path
    return False, None


def check_mathlib_available() -> bool:
    """Check if Mathlib is available (requires a Lean project).
    
    Note: This is a basic check. For full Mathlib, need a lake project.
    
    Returns:
        True if Mathlib is likely available.
    """
    # For now, just check if lean is installed
    # Full Mathlib check would require a test compilation
    lean_ok, _ = check_lean_version()
    return lean_ok


def get_installation_instructions() -> str:
    """Get instructions for installing Lean 4.
    
    Returns:
        Shell command to install Lean 4 via elan.
    """
    return """
=== LEAN 4 INSTALLATION INSTRUCTIONS ===

Run the following command in your terminal:

    curl https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh -sSf | sh

After installation, restart your terminal or run:

    source ~/.elan/env

Then verify:

    lean --version
    lake --version

For Mathlib support, create a new project:

    lake new mathlib_test math
    cd mathlib_test
    lake exe cache get
    lake build

"""


def run_full_check() -> bool:
    """Run full environment check.
    
    Returns:
        True ONLY if Lean 4 compiler is properly installed.
    """
    print("=" * 60)
    print("LEAN 4 ENVIRONMENT CHECK")
    print("=" * 60)
    
    all_ok = True
    
    # Check elan
    elan_ok, elan_path = check_elan_installed()
    print(f"elan (version manager): {'✅' if elan_ok else '❌'} {elan_path or 'Not found'}")
    
    # Check lean
    lean_ok, lean_version = check_lean_version()
    print(f"lean (compiler): {'✅' if lean_ok else '❌'} {lean_version or 'Not found'}")
    all_ok = all_ok and lean_ok
    
    # Check lake
    lake_ok, lake_path = check_lake_installed()
    print(f"lake (build tool): {'✅' if lake_ok else '❌'} {lake_path or 'Not found'}")
    
    print()
    
    if not lean_ok:
        print("⚠️  LEAN 4 NOT INSTALLED")
        print(get_installation_instructions())
        return False
    
    print("✅ LEAN 4 ENVIRONMENT READY")
    return True


def is_lean_available() -> bool:
    """Simple check if Lean is available.
    
    This is the gate function - returns True only if Lean 4 
    is properly installed and ready for formal verification.
    
    Returns:
        True if Lean 4 is installed and working.
    """
    lean_ok, _ = check_lean_version()
    return lean_ok


if __name__ == "__main__":
    result = run_full_check()
    sys.exit(0 if result else 1)
