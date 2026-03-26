#!/usr/bin/env python3
"""
Standalone crash repair agent.
Minimal dependencies, self-contained.
"""
import os
import subprocess
import sys
from pathlib import Path

# Only external dep: anthropic
from anthropic import Anthropic


def run_bash(cmd: str) -> str:
    """Execute bash command, return output."""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30
        )
        output = result.stdout
        if result.stderr:
            output += f"\n[stderr]\n{result.stderr}"
        output += f"\n[exit: {result.returncode}]"
        return output
    except subprocess.TimeoutExpired:
        return "Error: Command timed out after 30s"
    except Exception as e:
        return f"Error: {e}"


def get_recent_crash_log(workspace: Path) -> str | None:
    """Find most recent crash log."""
    logs_dir = workspace / "logs"
    if not logs_dir.exists():
        return None

    crash_logs = sorted(logs_dir.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not crash_logs:
        return None

    # Check if it's actually a crash (not user exit)
    content = crash_logs[0].read_text()
    if "KeyboardInterrupt" in content or "SystemExit: 0" in content:
        return None

    return content[:5000]  # First 5k chars


def repair_loop(workspace: Path, api_key: str) -> bool:
    """
    Run minimal repair loop.
    Returns True if repair was attempted and restart needed.
    """
    # Check if already repaired
    marker = workspace / ".repair_done"
    if marker.exists():
        marker.unlink()
        print("[repair] This is a repair restart, skipping")
        return False

    crash_log = get_recent_crash_log(workspace)
    if not crash_log:
        print("[repair] No crash found")
        return False

    client = Anthropic(api_key=api_key)

    system_prompt = """You are a crash repair agent.
Your task: analyze the crash log and fix the code.

Available commands (call via function):
- bash(cmd): execute shell command

Workflow:
1. Read crash log with bash("cat ...")
2. Examine relevant code files
3. Fix with bash("sed ...") or write file
4. Test with bash("python -m py_compile ...")
5. Commit with bash("git add ... && git commit ...")
6. When done, call bash("echo done > workspace/.repair_done")
7. Then call bash("echo restart > workspace/.restart_requested")

Be minimal. Fix only the obvious bug."""

    messages = [
        {"role": "user", "content": f"Crash log:\n```\n{crash_log}\n```\n\nAnalyze and fix."}
    ]

    max_turns = 20
    for turn in range(max_turns):
        print(f"[repair] Turn {turn + 1}/{max_turns}")

        response = client.messages.create(
            model="claude-sonnet-4-6",  # or env configured
            system=system_prompt,
            messages=messages,
            max_tokens=4096,
            tools=[{
                "name": "bash",
                "description": "Execute bash command",
                "input_schema": {
                    "type": "object",
                    "properties": {"cmd": {"type": "string"}},
                    "required": ["cmd"]
                }
            }]
        )

        content_blocks = []
        tool_calls = []

        for block in response.content:
            if block.type == "text":
                content_blocks.append(block.text)
                print(f"[repair] Thought: {block.text[:200]}...")
            elif block.type == "tool_use":
                tool_calls.append(block)

        # Add assistant response to history
        messages.append({
            "role": "assistant",
            "content": content_blocks + [{"type": "tool_use", "id": tc.id, "name": tc.name, "input": tc.input} for tc in tool_calls]
        })

        if not tool_calls:
            print("[repair] No tool calls, finishing")
            break

        # Execute tools
        tool_results = []
        for tc in tool_calls:
            if tc.name == "bash":
                cmd = tc.input.get("cmd", "")
                print(f"[repair] Bash: {cmd[:60]}...")
                output = run_bash(cmd)

                # Check for restart marker
                restart_marker = workspace / ".restart_requested"
                if restart_marker.exists():
                    restart_marker.unlink()
                    print("[repair] Restart requested")
                    return True

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tc.id,
                    "content": output[:2000]  # Truncate long output
                })

        messages.append({"role": "user", "content": tool_results})

    print("[repair] Max turns reached")
    return False


if __name__ == "__main__":
    workspace = Path(os.environ.get("TINYAGENT_WORKSPACE", "."))
    api_key = os.environ.get("ANTHROPIC_API_KEY")

    if not api_key:
        print("[repair] No ANTHROPIC_API_KEY, skipping")
        sys.exit(0)

    needs_restart = repair_loop(workspace, api_key)
    sys.exit(42 if needs_restart else 0)  # 42 = restart requested
