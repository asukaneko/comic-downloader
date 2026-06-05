"""Wait for the current bot process to exit, then start a replacement process."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time


def _is_process_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()

    command = args.command
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        print("restart_launcher: missing command", file=sys.stderr)
        return 2

    deadline = time.time() + 30
    while time.time() < deadline and _is_process_running(args.pid):
        time.sleep(0.5)

    subprocess.Popen(command, cwd=os.getcwd(), close_fds=os.name != "nt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
