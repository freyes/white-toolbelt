# SPDX-License-Identifier: GPL-2.0-only
# Copyright (C) 2026 white-toolbelt contributors

import importlib.machinery
import importlib.util
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "bin" / "mattermost-thread-download"


@pytest.fixture(scope="session")
def mtd():
    """Load bin/mattermost-thread-download as a module (it has no .py ext)."""
    loader = importlib.machinery.SourceFileLoader("mtd", str(SCRIPT))
    spec = importlib.util.spec_from_loader("mtd", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


# Wire-level fake of the Mattermost API used by the e2e tests.
# Endpoints served: /posts/{id}, /posts/{root}/thread, /users/ids (POST),
# /posts/{id}/reactions, /channels/{id}, /teams/{id}, /files/{id}.
TOKEN = "testtoken"
ROOT_ID = "r0000000000000000000001"
USERS = {
    "u1": {"id": "u1", "username": "alice", "first_name": "Alice", "last_name": "Smith",
           "nickname": "", "email": "alice@example.com"},
    "u2": {"id": "u2", "username": "bob", "first_name": "Bob", "last_name": "",
           "nickname": "bobby", "email": "bob@example.com"},
}
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000a49444154789c6360000002000154a24f5f0000000049454e44ae426082"
)


def _post(pid, create_at, delete_at, parent_id, message, files):
    return {
        "id": pid, "create_at": create_at, "update_at": 0, "delete_at": delete_at,
        "user_id": "u1" if pid == ROOT_ID else "u2", "channel_id": "ch1", "team_id": "t1",
        "root_id": "" if pid == ROOT_ID else ROOT_ID, "parent_id": parent_id,
        "message": message, "type": "", "props": {}, "file_ids": files,
        "metadata": {"files": [{"id": fid, "name": f"{fid}.png", "mime_type": "image/png",
                                "size": len(PNG)} for fid in files]},
    }


POSTS = {
    ROOT_ID: _post(ROOT_ID, 1700000000000, 0, "", "Root `code` and [link](https://x.y)", ["f111"]),
    "r0000000000000000000002": _post("r0000000000000000000002", 1700000100000, 0, ROOT_ID, "Reply", []),
    "r0000000000000000000003": _post("r0000000000000000000003", 1700000200000, 1700000200000,
                                     ROOT_ID, "deleted message", []),
}
# The API returns the thread order newest-first
THREAD = {"order": list(reversed(list(POSTS))), "posts": POSTS}


class Handler(BaseHTTPRequestHandler):
    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self):
        if self.headers.get("Authorization") != f"Bearer {TOKEN}":
            self._json({"message": "not authorized"}, 401)
            return False
        return True

    def do_GET(self):
        if not self._authorized():
            return
        path = self.path.split("?")[0]
        match path:
            case p if p == f"/api/v4/posts/{ROOT_ID}/thread":
                self._json(THREAD)
            case p if p.startswith("/api/v4/posts/") and p.endswith("/reactions"):
                pid = p.split("/")[4]
                self._json([{"emoji_name": "+1", "user_id": "u2", "post_id": pid}])
            case p if p.startswith("/api/v4/posts/"):
                # permalink target: a reply pointing at the thread root
                self._json(_post("perm0000000001", 1700000050000, 0, ROOT_ID, "", []))
            case p if p.startswith("/api/v4/channels/"):
                self._json({"id": "ch1", "name": "town-square",
                            "display_name": "Town Square", "type": "O"})
            case p if p.startswith("/api/v4/teams/"):
                self._json({"id": "t1", "name": "platform"})
            case p if p.startswith("/api/v4/files/"):
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(PNG)))
                self.end_headers()
                self.wfile.write(PNG)
            case _:
                self._json({"message": "not found"}, 404)

    def do_POST(self):
        if not self._authorized():
            return
        if self.path == "/api/v4/users/ids":
            n = int(self.headers.get("Content-Length", 0))
            ids = json.loads(self.rfile.read(n))
            self._json([USERS[i] for i in ids])
        else:
            self._json({"message": "not found"}, 404)

    def log_message(self, *args):
        pass


@pytest.fixture(scope="session")
def fake_mm():
    """Mattermost API fake on an OS-assigned port."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
