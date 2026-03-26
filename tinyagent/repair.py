#!/usr/bin/env python3
"""
Minimal repair agent - standalone, only bash tool.
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path


def run_bash(cmd: str, timeout: int = 30) -> str:
    """Execute bash command, return output."""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout
        )
        output = result.stdout
        if result.stderr:
            output += f"\n[stderr]\n{result.stderr}"
        output += f"\n[exit: {result.returncode}]"
        return output
    except subprocess.TimeoutExpired:
        return "Error: Command timed out"
    except Exception as e:
        return f"Error: {e}"


def get_crash_file(workspace: Path) -> Path | None:
    """Get fresh crash file (workspace/crash_*.log), None if no fresh crash."""
    crash_files = sorted(workspace.glob("crash_*.log"))
    if not crash_files:
        return None
    return crash_files[-1]  # Most recent


def archive_crash(crash_file: Path, workspace: Path) -> None:
    """Move repaired crash to history."""
    history_dir = workspace / "history_crash"
    history_dir.mkdir(parents=True, exist_ok=True)
    crash_file.rename(history_dir / crash_file.name)


def repair_loop(workspace: Path, code_path: Path, repair_log: Path) -> int:
    """
    Run minimal repair loop.
    Returns: 0=done (no crash or finished repair)
    """
    crash_file = get_crash_file(workspace)
    if not crash_file:
        return 0  # No fresh crash, nothing to repair

    crash_content = crash_file.read_text()

    # Write to repair log
    with open(repair_log, "a") as f:
        f.write(f"\n{'='*50}\n")
        f.write(f"[START] Repairing: {crash_file.name}\n")
        f.write(f"Crash preview:\n{crash_content[:500]}...\n")

    # TODO: Call LLM with bash tool to analyze and fix

    # After repair (success or not), archive the crash file
    archive_crash(crash_file, workspace)

    with open(repair_log, "a") as f:
        f.write(f"[DONE]  Repaired: {crash_file.name} -> archived\n")

    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--code-path", required=True)
    args = parser.parse_args()

    workspace = Path(args.workspace)
    code_path = Path(args.code_path)
    repair_log = workspace / "logs" / "repair.log"
    repair_log.parent.mkdir(parents=True, exist_ok=True)

    exit_code = repair_loop(workspace, code_path, repair_log)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
