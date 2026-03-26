#!/usr/bin/env python3
"""
Minimal repair agent - standalone, only bash tool.
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from anthropic import Anthropic


def run_bash(cmd: str, timeout: int = 30, cwd: Path | None = None) -> str:
    """Execute bash command, return output."""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout, cwd=cwd
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


def _load_anthropic_config() -> tuple[str | None, str | None]:
    """Load anthropic api_key and api_base from config."""
    config_path = Path.home() / ".tinyagent" / "config.json"
    if config_path.exists():
        try:
            with open(config_path) as f:
                data = json.load(f)
            provider = data.get("provider", {})
            anthropic = provider.get("anthropic", {})
            return anthropic.get("apiKey"), anthropic.get("apiBase")
        except Exception:
            pass
    return None, None


def _call_llm_repair(crash_content: str, workspace: Path, code_path: Path, repair_log: Path) -> None:
    """Call LLM with bash tool to analyze and fix crash."""
    api_key, api_base = _load_anthropic_config()
    if not api_key:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        with open(repair_log, "a") as f:
            f.write("[SKIP] No ANTHROPIC_API_KEY, skipping LLM repair\n")
        return

    client_kwargs = {"api_key": api_key}
    if api_base:
        client_kwargs["base_url"] = api_base
    client = Anthropic(**client_kwargs)

    system_prompt = f"""You are a crash repair agent. Your task: analyze the crash and fix the code.

Available tool:
- bash(cmd): execute shell command in the project directory ({code_path})

Workflow:
1. Read crash log and related code files using bash("cat ...") or bash("head ...")
2. Analyze the root cause
3. Fix with bash("sed ...") or bash("echo ... > file")
4. Verify fix with bash("python -m py_compile ...")
5. When done, report what you fixed

Constraints:
- Fix only the obvious bug causing the crash
- Do not refactor unrelated code
- If you cannot fix it, report why"""

    messages = [
        {"role": "user", "content": f"Fix this crash:\n\n```\n{crash_content}\n```"}
    ]

    max_turns = 20
    tool_def = {
        "name": "bash",
        "description": "Execute bash command",
        "input_schema": {
            "type": "object",
            "properties": {"cmd": {"type": "string", "description": "Command to execute"}},
            "required": ["cmd"]
        }
    }

    with open(repair_log, "a") as f:
        f.write("[LLM] Starting repair conversation\n")

    for turn in range(max_turns):
        try:
            response = client.messages.create(
                model="claude-sonnet-4-6",
                system=system_prompt,
                messages=messages,
                max_tokens=4096,
                tools=[tool_def]
            )
        except Exception as e:
            with open(repair_log, "a") as f:
                f.write(f"[ERROR] LLM API error: {e}\n")
            return

        # Collect assistant content and tool calls
        assistant_content = []
        tool_calls = []

        for block in response.content:
            if block.type == "text":
                assistant_content.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                tool_calls.append(block)

        # Add assistant message to history
        messages.append({"role": "assistant", "content": assistant_content + [
            {"type": "tool_use", "id": tc.id, "name": tc.name, "input": tc.input}
            for tc in tool_calls
        ]})

        # Log assistant thought
        for block in response.content:
            if block.type == "text" and block.text.strip():
                with open(repair_log, "a") as f:
                    f.write(f"[LLM] {block.text[:200]}...\n")

        if not tool_calls:
            # No more tool calls, repair done
            with open(repair_log, "a") as f:
                f.write("[LLM] Repair conversation complete\n")
            return

        # Execute tool calls
        tool_results = []
        for tc in tool_calls:
            if tc.name == "bash":
                cmd = tc.input.get("cmd", "")
                with open(repair_log, "a") as f:
                    f.write(f"[BASH] {cmd[:80]}\n")

                output = run_bash(cmd, timeout=30, cwd=code_path)

                # Truncate long output
                if len(output) > 2000:
                    output = output[:1000] + "\n... (truncated) ...\n" + output[-500:]

                with open(repair_log, "a") as f:
                    f.write(f"[BASH_OUT] {output[:200]}...\n")

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tc.id,
                    "content": output
                })

        # Add tool results to history
        messages.append({"role": "user", "content": tool_results})

    # Max turns reached
    with open(repair_log, "a") as f:
        f.write("[LLM] Max turns reached, stopping\n")


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

    # Call LLM with bash tool to analyze and fix
    _call_llm_repair(crash_content, workspace, code_path, repair_log)

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
