"""Regression tests for MCP behavior retained by the JOR fork."""

from test_mcp_server import _get_collection, _patch_mcp_server


def _prepare(monkeypatch, config, palace_path, kg):
    _patch_mcp_server(monkeypatch, config, kg)
    client, _collection = _get_collection(palace_path, create=True)
    del client


def test_diary_read_returns_entry_id_and_delete_removes_entry(monkeypatch, config, palace_path, kg):
    _prepare(monkeypatch, config, palace_path, kg)
    from mempalace.mcp_server import tool_diary_delete, tool_diary_read, tool_diary_write

    written = tool_diary_write("TestAgent", "durable observation", topic="ops")
    assert written["success"] is True

    read = tool_diary_read("TestAgent")
    assert read["entries"][0]["entry_id"] == written["entry_id"]

    deleted = tool_diary_delete(written["entry_id"])
    assert deleted["success"] is True
    assert deleted["deleted_ids"] == [written["entry_id"]]
    assert tool_diary_read("TestAgent")["entries"] == []


def test_diary_delete_removes_all_chunks(monkeypatch, config, palace_path, kg):
    _prepare(monkeypatch, config, palace_path, kg)
    from mempalace.mcp_server import tool_diary_delete, tool_diary_read, tool_diary_write

    written = tool_diary_write("TestAgent", "Z" * 2400, topic="ops")
    assert written["chunks"] == 3

    deleted = tool_diary_delete(written["entry_id"])
    assert deleted["success"] is True
    assert deleted["chunks_deleted"] == 3
    assert set(deleted["deleted_ids"]) == set(written["chunk_ids"])
    assert tool_diary_read("TestAgent")["entries"] == []


def test_status_counts_chunk_groups_as_logical_drawers(monkeypatch, config, palace_path, kg):
    _prepare(monkeypatch, config, palace_path, kg)
    from mempalace.mcp_server import tool_add_drawer, tool_diary_write, tool_status

    drawer = tool_add_drawer("wing_ops", "infra", "A" * 2400)
    diary = tool_diary_write("TestAgent", "B" * 2400, topic="ops")
    assert drawer["chunks"] == 3
    assert diary["chunks"] == 3

    status = tool_status()
    assert status["total_drawers"] == 2
    assert status["wings"]["wing_ops"] == 1
    assert status["wings"]["wing_testagent"] == 1
