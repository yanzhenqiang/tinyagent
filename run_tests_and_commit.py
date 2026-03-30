import subprocess
import sys

def run(cmd, **kwargs):
    print(f">>> {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, **kwargs)
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    print(f"exit: {result.returncode}")
    return result

# Run quick regression tests
r = run("cd /data/data/com.termux/files/home/tinyagent && python3 test_fixes.py")
if r.returncode != 0:
    sys.exit(1)

# Git status and diff
run("cd /data/data/com.termux/files/home/tinyagent && git status")
run("cd /data/data/com.termux/files/home/tinyagent && git diff")

# Add, commit, push
run("cd /data/data/com.termux/files/home/tinyagent && git add -A")
r = run(
    "cd /data/data/com.termux/files/home/tinyagent && git commit -m 'fix runtime bugs: LLMResponse missing attrs, thinking budget guard, command handler args, skills_loader init/xml/metadata'"
)
if r.returncode == 0:
    run("cd /data/data/com.termux/files/home/tinyagent && git push")
