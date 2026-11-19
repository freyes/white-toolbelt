# SPDX-License-Identifier: GPL-2.0-only
# Copyright (C) 2026 white-toolbelt contributors

from types import SimpleNamespace

import pytest


@pytest.mark.parametrize(("url", "server", "post_id"), [
    ("https://mm.example.com/platform/town-square/abcdefghijklmnop",
     "https://mm.example.com", "abcdefghijklmnop"),
    ("https://mm.example.com/#/platform/town-square/abcdefghijklmnop",
     "https://mm.example.com", "abcdefghijklmnop"),
    ("https://mm.example.com/team/channel/abcdefghijklmnop?reg=xyz",
     "https://mm.example.com", "abcdefghijklmnop"),
])
def test_parse_url_extracts_server_and_post_id(mtd, url, server, post_id):
    assert mtd.parse_url(url, None) == (server, post_id)


def test_parse_url_keeps_subpath_in_server(mtd):
    url = "https://mm.example.com/mattermost/team/channel/abcdefghijklmnop"
    assert mtd.parse_url(url, None) == ("https://mm.example.com/mattermost", "abcdefghijklmnop")


def test_parse_url_server_override_wins(mtd):
    url = "https://mm.example.com/team/channel/abcdefghijklmnop"
    assert mtd.parse_url(url, "http://localhost:8065") == ("http://localhost:8065", "abcdefghijklmnop")


def test_parse_url_rejects_non_post_id_tail(mtd):
    with pytest.raises(SystemExit):
        mtd.parse_url("https://mm.example.com/team/channel/not-a-post-id", None)


@pytest.mark.parametrize(("user", "expected"), [
    ({"username": "alice", "first_name": "Alice", "last_name": "Smith", "nickname": "ace"}, "ace"),
    ({"username": "alice", "first_name": "Alice", "last_name": "Smith", "nickname": ""}, "Alice Smith"),
    ({"username": "alice", "first_name": "", "last_name": "", "nickname": ""}, "alice"),
])
def test_display_name_falls_back_nickname_then_fullname_then_username(mtd, user, expected):
    assert mtd.display_name(user) == expected


def test_iso_converts_ms_epoch_to_utc(mtd):
    assert mtd.iso(1700000000000) == "2023-11-14T22:13:20+00:00"
    assert mtd.iso(None) is None


def test_message_markdown_falls_back_to_props_attachments(mtd):
    assert mtd.message_markdown({"message": "hello", "props": {}}) == "hello"
    bot = {"message": "", "props": {"attachments": [{"pretext": "pre", "title": "T", "text": "body"}]}}
    assert mtd.message_markdown(bot) == "pre\n\n**T**\nbody"


def test_reaction_line_groups_by_emoji(mtd):
    assert mtd.reaction_line([]) == ""
    reactions = [{"emoji": "+1", "count": 2, "users": ["bob", "alice"]},
                 {"emoji": "tada", "count": 1, "users": ["alice"]}]
    assert mtd.reaction_line(reactions) == "*Reactions: +1 x2 (bob, alice) · tada x1 (alice)*"


@pytest.mark.parametrize(("ref", "mime", "expected"), [
    ({"id": "f1", "name": "1.png"}, "image/png", "![1.png](files/f1__1.png)"),
    ({"id": "f1", "name": "1.pdf"}, "application/pdf", "[1.pdf](files/f1__1.pdf)"),
])
def test_file_markdown_marks_downloads(mtd, ref, mime, expected):
    files = {"f1": {"name": f"f1__{ref['name']}", "mime": mime, "data": b""}}
    assert mtd.file_markdown(ref, files) == expected


def test_file_markdown_notes_missing_download(mtd):
    assert mtd.file_markdown({"id": "f1", "name": "1.png"}, {}) == "*attachment f1 not downloaded*"


def raw_posts():
    """Thread as the Mattermost API returns it (raw shapes for build_json)."""
    root = {"id": "p1", "parent_id": "", "root_id": "", "delete_at": 0, "user_id": "u1",
            "message": "Root", "file_ids": ["f111"], "props": {},
            "metadata": {"files": [{"id": "f111", "name": "1.png", "mime_type": "image/png", "size": 70}]}}
    reply = {"id": "p2", "parent_id": "p1", "root_id": "p1", "delete_at": 1700000200000,
             "user_id": "u2", "message": "gone", "file_ids": [], "props": {}}
    return [root, reply]


def resolved_doc():
    """Thread in the shape build_json produces (input for build_markdown)."""
    return {
        "source": {"url": "http://s/x", "fetched_at": "2026-01-01T00:00:00+00:00"},
        "team": {"id": "t1", "name": "platform"},
        "channel": {"id": "ch1", "name": "town-square", "display_name": "Town Square", "type": "O"},
        "post_count": 2,
        "users": {}, "participants": [],
        "posts": [
            {"id": "p1", "parent_id": "", "deleted": False,
             "author": {"username": "alice", "display_name": "Alice Smith"},
             "created_at": "2023-11-14T22:13:20+00:00", "message": "Root",
             "files": [{"id": "f111", "name": "1.png", "local_path": "files/f111__1.png"}],
             "reactions": [], "props": {}},
            {"id": "p2", "parent_id": "p1", "deleted": True,
             "author": {"username": "bob", "display_name": "bobby"},
             "created_at": "2023-11-14T22:13:21+00:00", "message": "gone",
             "files": [], "reactions": [], "props": {}},
        ],
    }


def test_build_json_resolves_authors_and_groups_reactions(mtd):
    users = {"u1": {"username": "alice", "first_name": "Alice", "last_name": "Smith",
                    "nickname": "", "email": "a@x"},
             "u2": {"username": "bob", "first_name": "Bob", "last_name": "",
                    "nickname": "bobby", "email": "b@x"}}
    reactions = {"p1": [{"emoji_name": "+1", "user_id": "u1"},
                        {"emoji_name": "+1", "user_id": "u2"}]}
    files = {"f111": {"info": {"id": "f111", "name": "1.png", "mime_type": "image/png", "size": 70},
                      "name": "f111__1.png", "mime": "image/png", "data": b""}}
    doc = mtd.build_json("http://s/x", "now", raw_posts(), users, reactions,
                         {"id": "ch1", "name": "c", "display_name": "C", "type": "O"}, None, files)
    assert doc["post_count"] == 2
    assert [(p["author"]["username"], p["deleted"]) for p in doc["posts"]] == \
        [("alice", False), ("bob", True)]
    assert doc["posts"][0]["reactions"] == [{"emoji": "+1", "count": 2, "users": ["alice", "bob"]}]
    assert doc["posts"][0]["files"][0]["local_path"] == "files/f111__1.png"


def test_build_markdown_renders_posts_in_order_with_attachments(mtd):
    md = mtd.build_markdown(resolved_doc(), {"f111": {"name": "f111__1.png", "mime": "image/png", "data": b""}})
    assert md.startswith("# Town Square — platform — thread")
    assert "![1.png](files/f111__1.png)" in md
    assert "(message deleted)" in md
    assert md.index("Alice Smith") < md.index("(message deleted)")


def test_get_token_prefers_flag_then_env_then_dies(mtd, monkeypatch):
    monkeypatch.setenv("MATTERMOST_TOKEN", "from-env")
    assert mtd.get_token(SimpleNamespace(token="from-flag")) == "from-flag"
    monkeypatch.delenv("MATTERMOST_TOKEN", raising=False)
    monkeypatch.delenv("MM_TOKEN", raising=False)
    monkeypatch.setattr(mtd.subprocess, "run",
                        lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError()))
    with pytest.raises(SystemExit):
        mtd.get_token(SimpleNamespace(token=None))
