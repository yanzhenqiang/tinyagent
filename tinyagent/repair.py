#!/usr/bin/env python3
"""
Minimal repair agent - standalone, only bash tool.
No exception, only write log.
"""
import argparse
import json
import os
import subprocess
from pathlib import Path

from anthropic import Anthropic


def run_bash(cmd: str, timeout: int = 30, cwd: Path | None = None) -> str:
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
    crash_files = sorted(workspace.glob("crash_*.log"))
    if not crash_files:
        return None
    return crash_files[-1]


def _load_provider_config() -> tuple[str | None, str | None, str]:
    config_path = Path.home() / ".tinyagent" / "config.json"
    with open(config_path) as f:
        data = json.load(f)
    agent = data.get("agent", {})
    provider_name = agent.get("provider", "anthropic")
    provider_config = data.get("provider", {}).get(provider_name, {})
    model = agent.get("model", "claude-opus-4-6")
    if "/" in model:
        model = model.split("/")[-1]
    return provider_config.get("apiKey"), provider_config.get("apiBase"), model


def _call_llm_repair(workspace: Path, code_path: Path, repair_log: Path) -> None:
    api_key, api_base, model = _load_provider_config()
    if not api_key:
        with open(repair_log, "a") as f:
            f.write("[SKIP] No API_KEY, skipping LLM repair\n")
        return
    client_kwargs = {"api_key": api_key}
    if api_base:
        client_kwargs["base_url"] = api_base
    client = Anthropic(**client_kwargs)
    system_prompt = f"""You are a crash repair agent. Analyze the crash and fix the code.

Workspace: {workspace}
Code path: {code_path}

Crash files are in {workspace}/crash_*.log
After fixing, move the crash file to {workspace}/history_crash/

Available tool: bash(cmd) to execute shell commands.

Your task:
1. List crash files: ls {workspace}/crash_*.log
2. Read the most recent crash log
3. Read relevant source files
4. Identify root cause and make minimal fixes
5. Verify the fix works
6. Move crash file to history_crash directory
7. Report what you changed

Be minimal. Only fix the obvious bug. Do not refactor."""

    messages = [
        {"role": "user", "content": "Find and fix the crash. Start by listing crash files."}
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
                model=model,
                system=system_prompt,
                messages=messages,
                max_tokens=4096,
                tools=[tool_def]
            )
        except Exception as e:
            with open(repair_log, "a") as f:
                f.write(f"[ERROR] LLM API error: {e}\n")
            return
        assistant_content = []
        tool_calls = []
        for block in response.content:
            if block.type == "text":
                assistant_content.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                tool_calls.append(block)
        messages.append({"role": "assistant", "content": assistant_content + [
            {"type": "tool_use", "id": tc.id, "name": tc.name, "input": tc.input}
            for tc in tool_calls
        ]})
        for block in response.content:
            if block.type == "text" and block.text.strip():
                with open(repair_log, "a") as f:
                    f.write(f"[LLM] {block.text[:200]}...\n")
        if not tool_calls:
            with open(repair_log, "a") as f:
                f.write("[LLM] Repair conversation complete\n")
            return
        tool_results = []
        for tc in tool_calls:
            if tc.name == "bash":
                cmd = tc.input.get("cmd", "")
                with open(repair_log, "a") as f:
                    f.write(f"[BASH] {cmd[:80]}\n")
                output = run_bash(cmd, timeout=30, cwd=code_path)
                if len(output) > 2000:
                    output = output[:1000] + "\n... (truncated) ...\n" + output[-500:]
                with open(repair_log, "a") as f:
                    f.write(f"[BASH_OUT] {output[:200]}...\n")
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tc.id,
                    "content": output
                })
        messages.append({"role": "user", "content": tool_results})
    with open(repair_log, "a") as f:
        f.write("[LLM] Max turns reached, stopping\n")

def repair_loop(workspace: Path, code_path: Path, repair_log: Path) -> int:
    crash_file = get_crash_file(workspace)
    if not crash_file:
        return
    with open(repair_log, "a") as f:
        f.write(f"[START] {crash_file.name}\n")
    _call_llm_repair(workspace, code_path, repair_log)
    with open(repair_log, "a") as f:
        f.write("[DONE]\n")
    return


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--code-path", required=True)
    args = parser.parse_args()
    workspace = Path(args.workspace)
    code_path = Path(args.code_path)
    repair_log = workspace / "logs" / "repair.log"
    repair_log.parent.mkdir(parents=True, exist_ok=True)
    repair_loop(workspace, code_path, repair_log)


if __name__ == "__main__":
    main()
