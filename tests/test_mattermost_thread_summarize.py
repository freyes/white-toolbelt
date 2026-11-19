# SPDX-License-Identifier: GPL-2.0-only
# Copyright (C) 2026 white-toolbelt contributors

import importlib.machinery
import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "bin" / "mattermost-thread-summarize"

ZDR_LIST = {"data": [
    {"model_id": "z-ai/glm-5.3-flash", "name": "Nebius | z-ai/glm-5.3-flash"},
    {"model_id": "good/model", "name": "Good | model"},
    {"model_id": "safety/model", "name": "Safety | model", "safety_retention": True},
]}


@pytest.fixture(scope="session")
def mts():
    """Load bin/mattermost-thread-summarize as a module (it has no .py ext)."""
    loader = importlib.machinery.SourceFileLoader("mts", str(SCRIPT))
    spec = importlib.util.spec_from_loader("mts", loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules["mts"] = module
    loader.exec_module(module)
    return module


@pytest.fixture
def zdr_ok(monkeypatch):
    """Fake the ZDR endpoint list HTTP fetch."""
    def fake_get(url, timeout=None):
        r = MagicMock()
        r.raise_for_status = lambda: None
        r.json = lambda: ZDR_LIST
        return r
    monkeypatch.setattr("mts.requests.get", fake_get)


@pytest.fixture
def fake_completion(monkeypatch):
    """Capture the arguments litellm.completion would be called with."""
    calls = []

    def completion(**kwargs):
        calls.append(kwargs)
        resp = MagicMock()
        resp.__getitem__ = lambda self, k: {
            "choices": [{"message": {"content": "SUMMARY"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }[k]
        resp.get = lambda k, default=None: {
            "usage": {"prompt_tokens": 10, "completion_tokens": 5}}.get(k, default)
        resp.model_dump = lambda: {"ok": True}
        return resp

    monkeypatch.setattr("mts.litellm.completion", completion)
    return calls


def make_thread(tmp_path, messages):
    md = "# chan — thread\n\n- Messages: 3\n\n---\n\n"
    md += "\n\n---\n\n".join(messages) + "\n"
    d = tmp_path / "mm-thread-chan-root00000001"
    d.mkdir()
    (d / "thread.md").write_text(md)
    return d


# --- ZDR policy ---------------------------------------------------------

def test_zdr_set_constant_is_true(mts):
    assert mts.ZDR == {"zdr": True}


def test_zdr_models_excludes_safety_retention(zdr_ok, mts):
    assert "safety/model" not in mts.zdr_models()
    assert {"z-ai/glm-5.3-flash", "good/model"} <= mts.zdr_models()


def test_main_refuses_non_zdr_model(zdr_ok, fake_completion, mts, tmp_path,
                                    monkeypatch, capsys):
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    d = make_thread(tmp_path, ["hello"])
    monkeypatch.setattr(sys, "argv", ["mts", str(d), "--model", "bad/model"])
    with pytest.raises(SystemExit) as exc:
        mts.main()
    assert "no Zero Data Retention endpoint" in str(exc.value.code)
    assert not fake_completion  # nothing was sent


def test_main_always_sends_zdr(zdr_ok, fake_completion, mts, tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    monkeypatch.setenv("MT_SUMMARIZE_ACK", "1")
    d = make_thread(tmp_path, ["hello"])
    monkeypatch.setattr(sys, "argv", ["mts", str(d)])
    mts.main()
    kwargs = fake_completion[0]
    assert kwargs["extra_body"] == {"provider": {"zdr": True}}
    assert kwargs["model"] == "openrouter/z-ai/glm-5.3-flash"


# --- key resolution ------------------------------------------------------

def test_get_api_key_reads_env(mts, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "envkey")
    assert mts.get_api_key() == "envkey"


def test_get_api_key_dies_without_env(mts, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(SystemExit) as exc:
        mts.get_api_key()
    assert "OPENROUTER_API_KEY" in str(exc.value.code)


# --- input handling ------------------------------------------------------

def test_truncate_noop_on_small_input(mts):
    md = "# t\n\n---\n\nshort"
    out, cut = mts.truncate(md, ".", 10_000)
    assert out == md
    assert cut == 0


def test_truncate_keeps_newest_messages(mts):
    parts = [f"old-{i}-" + "x" * 60 for i in "abc"]
    parts[-1] = "new-c"
    md = "# header\n\n- meta\n\n---\n\n" + "\n\n---\n\n".join(parts) + "\n"
    out, cut = mts.truncate(md, ".", 30)
    assert "new-c" in out
    assert "1 of 3 messages kept" in out
    assert "old-a" not in out and "old-b" not in out
    assert cut > 0


def test_truncate_never_returns_empty(mts):
    md = "# h\n\n" + "\n\n---\n\n".join(f"msg-{i}" * 20 for i in range(20))
    out, _ = mts.truncate(md, ".", 100)
    assert len(out) > 0


# --- end to end over mocks ----------------------------------------------

def test_main_writes_summary_file(zdr_ok, fake_completion, mts, tmp_path,
                                  monkeypatch, capsys):
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    monkeypatch.setenv("MT_SUMMARIZE_ACK", "1")
    d = make_thread(tmp_path, ["hello"])
    monkeypatch.setattr(sys, "argv", ["mts", str(d), "--write", "--language",
                                       "French"])
    mts.main()
    msgs = fake_completion[0]["messages"]
    assert msgs[0]["role"] == "system"
    assert "French" in msgs[1]["content"]
    assert (d / "summary.md").read_text().startswith("# Summary")


def test_main_accepts_thread_md_path(zdr_ok, fake_completion, mts, tmp_path,
                                      monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    monkeypatch.setenv("MT_SUMMARIZE_ACK", "1")
    d = make_thread(tmp_path, ["hello"])
    monkeypatch.setattr(sys, "argv", ["mts", str(d / "thread.md")])
    mts.main()
    assert fake_completion[0]["messages"][1]["content"].startswith("# chan")


def test_main_dies_on_missing_thread(zdr_ok, fake_completion, mts, tmp_path,
                                      monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    monkeypatch.setattr(sys, "argv", ["mts", str(tmp_path)])
    with pytest.raises(SystemExit):
        mts.load_thread(str(tmp_path))


def test_zdr_fetch_failure_is_fatal(mts, monkeypatch):
    def fake_get(url, timeout=None):
        raise OSError("network down")
    monkeypatch.setattr("mts.requests.get", fake_get)
    with pytest.raises(SystemExit):
        mts.zdr_models()