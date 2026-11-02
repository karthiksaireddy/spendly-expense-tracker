#!/usr/bin/env python3
"""Test Runner Subagent

Validates all routes after changes by running the test suite.
Provides isolated context and a pass/fail report.

Usage:
    python skills/test_runner.py
    python skills/test_runner.py --verbose
    python skills/test_runner.py --test test_auth.py
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import List


def run_tests(test_file: str = None, verbose: bool = False) -> dict:
    """Run pytest and return results as a dictionary."""
    cmd = ["python", "-m", "pytest"]
    
    if verbose:
        cmd.append("-v")
    else:
        cmd.append("-q")
    
    if test_file:
        cmd.append(f"tests/{test_file}")
    else:
        cmd.append("tests/")
    
    # Run pytest
    result = subprocess.run(
        cmd,
        cwd=Path(__file__).parent.parent,
        capture_output=True,
        text=True
    )
    
    return {
        "exit_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "passed": result.returncode == 0
    }


def parse_test_output(output: str) -> dict:
    """Parse pytest output to extract test counts."""
    lines = output.split('\n')
    summary = {
        "total": 0,
        "passed": 0,
        "failed": 0,
        "errors": 0,
        "skipped": 0
    }
    
    for line in lines:
        if "passed" in line.lower():
            # Parse line like "5 passed, 2 failed in 0.5s"
            parts = line.split()
            for i, part in enumerate(parts):
                if part.isdigit():
                    if i > 0 and "passed" in parts[i-1]:
                        summary["passed"] = int(part)
                    elif i > 0 and "failed" in parts[i-1]:
                        summary["failed"] = int(part)
                    elif i > 0 and "error" in parts[i-1]:
                        summary["errors"] = int(part)
                    elif i > 0 and "skipped" in parts[i-1]:
                        summary["skipped"] = int(part)
    
    summary["total"] = summary["passed"] + summary["failed"] + summary["errors"] + summary["skipped"]
    return summary


def generate_report(results: dict, verbose: bool = False) -> str:
    """Generate a human-readable test report."""
    report = "=" * 60 + "\n"
    report += "TEST RUNNER REPORT\n"
    report += "=" * 60 + "\n\n"
    
    if results["passed"]:
        report += "✅ ALL TESTS PASSED\n\n"
    else:
        report += "❌ TESTS FAILED\n\n"
    
    summary = parse_test_output(results["stdout"])
    report += f"Total tests: {summary['total']}\n"
    report += f"Passed: {summary['passed']}\n"
    report += f"Failed: {summary['failed']}\n"
    report += f"Errors: {summary['errors']}\n"
    report += f"Skipped: {summary['skipped']}\n\n"
    
    if verbose or not results["passed"]:
        report += "-" * 60 + "\n"
        report += "DETAILED OUTPUT\n"
        report += "-" * 60 + "\n\n"
        report += results["stdout"]
        
        if results["stderr"]:
            report += "\n" + "-" * 60 + "\n"
            report += "ERRORS\n"
            report += "-" * 60 + "\n\n"
            report += results["stderr"]
    
    report += "\n" + "=" * 60 + "\n"
    return report


def main():
    parser = argparse.ArgumentParser(
        description="Run test suite and generate pass/fail report"
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed output")
    parser.add_argument("--test", type=str, help="Run specific test file (e.g., test_auth.py)")
    
    args = parser.parse_args()
    
    print("Running test suite...")
    results = run_tests(args.test, args.verbose)
    
    report = generate_report(results, args.verbose)
    print(report)
    
    sys.exit(results["exit_code"])


if __name__ == "__main__":
    main()
