#!/usr/bin/env python3

import os
import sys
import time
from datetime import datetime

HEARTBEAT_TIMEOUT = 30
CHANNEL = "gateway"
HEARTBEAT = "HEARTBEAT"
LOG = "GUARD_LOG"


def log(log_file: str, action: str, detail: str = ""):
    ts = datetime.now().isoformat()
    line = f"{ts} [{action}] {detail}\n"
    with open(log_file, "a") as f:
        f.write(line)


def heartbeat_ok(workspace: str) -> bool:
    heartbeat_file = os.path.join(workspace, HEARTBEAT)
    if not os.path.exists(heartbeat_file):
        return False
    mtime = os.path.getmtime(heartbeat_file)
    return (time.time() - mtime) < HEARTBEAT_TIMEOUT


def touch_heartbeat(workspace: str):
    heartbeat_file = os.path.join(workspace, HEARTBEAT)
    with open(heartbeat_file, "a"):
        os.utime(heartbeat_file, None)


def rollback(code_path: str, log_file: str) -> str:
    import subprocess

    r = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=code_path,
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        log(log_file, "rollback_fail", "not a git repo")
        return "error:not_git"

    sha_from = r.stdout.strip()[:8]

    subprocess.run(
        ["git", "reset", "--hard", "HEAD~1"],
        cwd=code_path,
        capture_output=True,
        check=True,
    )

    r = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=code_path,
        capture_output=True,
        text=True,
        check=True,
    )
    sha_to = r.stdout.strip()[:8]

    return f"{sha_from} -> {sha_to}"


def run_agent(workspace: str):
    import subprocess

    cmd = [sys.executable, "-m", "tinyagent", CHANNEL, "--workspace", workspace]
    return subprocess.Popen(cmd, cwd=workspace)


def main(workspace: str, code_path: str):
    log_file = os.path.join(workspace, LOG)

    log(log_file, "start", f"workspace={workspace} code_path={code_path}")
    crash_count = 0

    while True:
        touch_heartbeat(workspace)

        proc = run_agent(workspace)
        log(log_file, "spawn", f"pid={proc.pid}")

        while True:
            time.sleep(5)

            code = proc.poll()
            if code is not None:
                log(log_file, "exit", f"code={code}")
                if code == 0:
                    log(log_file, "shutdown", "normal exit")
                    return
                crash_count += 1
                break

            if not heartbeat_ok(workspace):
                log(log_file, "hang", "heartbeat timeout")
                proc.kill()
                proc.wait()
                crash_count += 1
                break

        if crash_count >= 3:
            sha = rollback(code_path, log_file)
            log(log_file, "rollback", f"sha={sha}")
            crash_count = 0
        else:
            log(log_file, "restart", f"delay=3s crash_count={crash_count}")
            time.sleep(3)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(1)

    main(sys.argv[1], sys.argv[2])
