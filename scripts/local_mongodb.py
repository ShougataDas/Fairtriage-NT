"""Start, stop or check the MongoDB server kept in .mongodb/ for local use.

    python scripts/local_mongodb.py start
    python scripts/local_mongodb.py status
    python scripts/local_mongodb.py stop

The server listens on localhost:27017 only (not reachable from the network)
and keeps its data in .mongodb/data. Delete the .mongodb folder to remove it.
Not needed if MongoDB is installed as a Windows service, or with Atlas.
"""

from __future__ import annotations

import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOME = ROOT / ".mongodb"
EXE = HOME / "bin" / ("mongod.exe" if sys.platform == "win32" else "mongod")
PORT = 27017


def running() -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", PORT)) == 0


def start() -> None:
    if running():
        print(f"MongoDB is already running on localhost:{PORT}")
        return
    if not EXE.exists():
        sys.exit(f"{EXE} not found. Install MongoDB, or download it into .mongodb/bin.")
    (HOME / "data").mkdir(parents=True, exist_ok=True)
    (HOME / "log").mkdir(parents=True, exist_ok=True)
    flags = 0
    if sys.platform == "win32":     # keep running after this terminal closes
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen([str(EXE), "--dbpath", str(HOME / "data"), "--port", str(PORT),
                      "--bind_ip", "127.0.0.1", "--logpath", str(HOME / "log" / "mongod.log"),
                      "--logappend"], creationflags=flags, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, close_fds=True)
    for _ in range(40):
        if running():
            print(f"MongoDB started on localhost:{PORT} (data in {HOME / 'data'})")
            return
        time.sleep(0.5)
    sys.exit(f"MongoDB did not start. See {HOME / 'log' / 'mongod.log'}")


def stop() -> None:
    if not running():
        print("MongoDB is not running")
        return
    from pymongo import MongoClient
    try:
        MongoClient(f"mongodb://127.0.0.1:{PORT}", serverSelectionTimeoutMS=3000).admin.command("shutdown")
    except Exception:
        pass                         # the server closes the connection as it shuts down
    for _ in range(20):
        if not running():
            print("MongoDB stopped")
            return
        time.sleep(0.5)
    sys.exit("MongoDB did not stop")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "start":
        start()
    elif cmd == "stop":
        stop()
    else:
        print(f"MongoDB is {'running' if running() else 'not running'} on localhost:{PORT}")
