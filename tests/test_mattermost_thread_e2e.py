# SPDX-License-Identifier: GPL-2.0-only
# Copyright (C) 2026 white-toolbelt contributors

import json
import os
import subprocess
import sys
from pathlib import Path

from conftest import POSTS, SCRIPT


def run_cli(server, env, outdir):
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--server", server,
         f"{server}/platform/town-square/perm0000000001", "-o", str(outdir)],
        env=env, capture_output=True, text=True, timeout=120)


def test_cli_download_produces_three_formats(fake_mm, tmp_path):
    result = run_cli(fake_mm, {**os.environ, "MATTERMOST_TOKEN": "testtoken"}, tmp_path)
    assert result.returncode == 0, result.stderr

    outdir = next(tmp_path.glob("mm-thread-*"))
    assert {p.name for p in outdir.iterdir() if p.is_file()} == \
        {"thread.md", "thread.json", "thread.html"}

    doc = json.loads((outdir / "thread.json").read_text())
    assert [p["id"] for p in doc["posts"]] == list(POSTS)
    created = [p["created_at"] for p in doc["posts"]]
    assert created == sorted(created)
    root = doc["posts"][0]
    assert root["author"]["display_name"] == "Alice Smith"
    assert root["reactions"][0]["users"] == ["bob"]
    file_path = outdir / root["files"][0]["local_path"]
    assert file_path.exists()
    assert not (outdir / "style.css").exists()

    assert "data:image/png;base64" in (outdir / "thread.html").read_text()


def test_cli_wrong_token_fails_without_output(fake_mm, tmp_path):
    result = run_cli(fake_mm, {**os.environ, "MATTERMOST_TOKEN": "wrong-token"}, tmp_path)
    assert result.returncode == 1
    assert list(tmp_path.glob("mm-thread-*")) == []
