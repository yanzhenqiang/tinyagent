#!/usr/bin/env python3
"""
Guard: Minimal watchdog for tinyagent.
Starts agent, monitors health, restarts on crash.
< 50 lines, zero dependencies outside stdlib.
"""

import os
import signal
import subprocess
import sys
import time

AGENT_CMD = [sys.executable, "-m", "tinyagent"]
HEARTBEAT_FILE = "/tmp/tinyagent_heartbeat"
HEARTBEAT_TIMEOUT = 30  # seconds


def start_agent():
    """Start agent as subprocess."""
    return subprocess.Popen(AGENT_CMD)


def check_heartbeat():
    """Check if agent is alive via heartbeat file."""
    try:
        mtime = os.path.getmtime(HEARTBEAT_FILE)
        return (time.time() - mtime) < HEARTBEAT_TIMEOUT
    except FileNotFoundError:
        return False


def main():
    proc = None
    shutdown = False

    def on_sigterm(signum, frame):
        nonlocal shutdown
        shutdown = True
        if proc:
            proc.send_signal(signal.SIGTERM)

    signal.signal(signal.SIGTERM, on_sigterm)
    signal.signal(signal.SIGINT, on_sigterm)

    while not shutdown:
        proc = start_agent()
        print(f"[guard] Agent started (pid={proc.pid})")

        while proc.poll() is None and not shutdown:
            time.sleep(5)
            if not check_heartbeat():
                print("[guard] Heartbeat lost, killing agent...")
                proc.send_signal(signal.SIGKILL)
                break

        exit_code = proc.wait()
        print(f"[guard] Agent exited with code {exit_code}")

        if shutdown or exit_code == 0:
            print("[guard] Graceful shutdown")
            break

        print("[guard] Restarting in 3s...")
        time.sleep(3)


if __name__ == "__main__":
    main()
