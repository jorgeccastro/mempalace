"""
test_searcher.py -- Tests for both search() (CLI) and search_memories() (API).

Uses the real ChromaDB fixtures from conftest.py for integration tests,
plus mock-based tests for error paths.
"""

from unittest.mock import MagicMock, patch

import pytest

from mempalace.searcher import (
    SearchError,
    _build_query_variants,
    _keyword_overlap,
    search,
    search_memories,
)


# ── search_memories (API) ──────────────────────────────────────────────


class TestSearchMemories:
    def test_basic_search(self, palace_path, seeded_collection):
        result = search_memories("JWT authentication", palace_path)
        assert "results" in result
        assert len(result["results"]) > 0
        assert result["query"] == "JWT authentication"

    def test_wing_filter(self, palace_path, seeded_collection):
        result = search_memories("planning", palace_path, wing="notes")
        assert all(r["wing"] == "notes" for r in result["results"])

    def test_room_filter(self, palace_path, seeded_collection):
        result = search_memories("database", palace_path, room="backend")
        assert all(r["room"] == "backend" for r in result["results"])

    def test_wing_and_room_filter(self, palace_path, seeded_collection):
        result = search_memories("code", palace_path, wing="project", room="frontend")
        assert all(r["wing"] == "project" and r["room"] == "frontend" for r in result["results"])

    def test_n_results_limit(self, palace_path, seeded_collection):
        result = search_memories("code", palace_path, n_results=2)
        assert len(result["results"]) <= 2

    def test_no_palace_returns_error(self, tmp_path):
        result = search_memories("anything", str(tmp_path / "missing"))
        assert "error" in result

    def test_result_fields(self, palace_path, seeded_collection):
        result = search_memories("authentication", palace_path)
        hit = result["results"][0]
        assert "text" in hit
        assert "wing" in hit
        assert "room" in hit
        assert "source_file" in hit
        assert "similarity" in hit
        assert isinstance(hit["similarity"], float)
        assert "created_at" in hit

    def test_created_at_contains_filed_at(self, palace_path, seeded_collection):
        """created_at surfaces the filed_at metadata from the drawer."""
        result = search_memories("JWT authentication", palace_path)
        hit = result["results"][0]
        assert hit["created_at"] == "2026-01-01T00:00:00"

    def test_created_at_fallback_when_filed_at_missing(self):
        """created_at defaults to 'unknown' when filed_at is absent."""
        mock_col = MagicMock()
        mock_col.query.return_value = {
            "ids": [["drawer_no_date"]],
            "documents": [["Some text without a date"]],
            "metadatas": [[{"wing": "project", "room": "backend", "source_file": "x.py"}]],
            "distances": [[0.1]],
        }

        with patch("mempalace.searcher.get_collection", return_value=mock_col):
            result = search_memories("test", "/fake/path")
        hit = result["results"][0]
        assert hit["created_at"] == "unknown"

    def test_search_memories_query_error(self):
        """search_memories returns error dict when query raises."""
        mock_col = MagicMock()
        mock_col.query.side_effect = RuntimeError("query failed")

        with patch("mempalace.searcher.get_collection", return_value=mock_col):
            result = search_memories("test", "/fake/path")
        assert "error" in result
        assert "query failed" in result["error"]

    def test_search_memories_filters_in_result(self, palace_path, seeded_collection):
        result = search_memories("test", palace_path, wing="project", room="backend")
        assert result["filters"]["wing"] == "project"
        assert result["filters"]["room"] == "backend"

    def test_similarity_is_bounded(self, palace_path, seeded_collection):
        result = search_memories("database", palace_path)
        assert result["results"]
        for hit in result["results"]:
            assert 0.0 <= hit["similarity"] <= 1.0

    def test_keyword_overlap_is_accent_insensitive(self):
        overlap = _keyword_overlap(
            ["sincronizacao", "convidado"],
            "sincronização de acesso convidado",
        )
        assert overlap == 1.0

    def test_build_query_variants_adds_keyword_only_form(self):
        variants = _build_query_variants("como ver pasta partilhada externa no OneDrive")
        assert "como ver pasta partilhada externa no OneDrive" in variants
        assert "ver pasta partilhada externa onedrive" in variants

    def test_build_query_variants_adds_quoted_phrase(self):
        variants = _build_query_variants('lembras-te de "sexual compulsions" e outras opcoes')
        assert "sexual compulsions" in variants

    def test_keyword_rerank_promotes_lexical_match(self):
        mock_col = MagicMock()
        mock_col.query.return_value = {
            "ids": [["doc_b", "doc_a", "doc_c"]],
            "documents": [
                [
                    "General cloud permissions discussion without the key terms.",
                    "SharePoint guest access for an externally shared folder with sync enabled.",
                    "Unrelated frontend planning note.",
                ]
            ],
            "metadatas": [
                [
                    {"wing": "project", "room": "backend", "source_file": "b.txt"},
                    {"wing": "project", "room": "backend", "source_file": "a.txt"},
                    {"wing": "notes", "room": "planning", "source_file": "c.txt"},
                ]
            ],
            "distances": [[0.20, 0.24, 0.80]],
        }

        with (
            patch("mempalace.searcher.get_collection", return_value=mock_col),
            patch(
                "mempalace.searcher.get_closets_collection",
                side_effect=Exception("no closets"),
            ),
        ):
            result = search_memories(
                "guest access shared folder sync", "/tmp/fake-palace", n_results=2
            )
        assert result["results"][0]["source_file"] == "a.txt"

    def test_query_variants_expand_candidate_pool(self):
        def fake_query(**kwargs):
            query = kwargs["query_texts"][0]
            if query == "onedrive pasta externa convidado":
                return {
                    "ids": [["doc_a"]],
                    "documents": [["Generic cloud discussion."]],
                    "metadatas": [
                        [{"wing": "project", "room": "backend", "source_file": "generic.txt"}]
                    ],
                    "distances": [[0.20]],
                }
            return {
                "ids": [["doc_b"]],
                "documents": [
                    ["Pasta partilhada externa com acesso de convidado e sincronização local."]
                ],
                "metadatas": [
                    [{"wing": "project", "room": "backend", "source_file": "expanded.txt"}]
                ],
                "distances": [[0.25]],
            }

        mock_col = MagicMock()
        mock_col.query.side_effect = fake_query

        with (
            patch("mempalace.searcher.get_collection", return_value=mock_col),
            patch(
                "mempalace.searcher.get_closets_collection",
                side_effect=Exception("no closets"),
            ),
        ):
            result = search_memories(
                "OneDrive pasta externa convidado", "/tmp/fake-palace", n_results=2
            )
        assert [hit["source_file"] for hit in result["results"]] == ["expanded.txt", "generic.txt"]

    def test_quoted_phrase_boost_promotes_exact_phrase(self):
        mock_col = MagicMock()
        mock_col.query.return_value = {
            "ids": [["doc_a", "doc_b"]],
            "documents": [
                [
                    "General advice about habit formation and compulsion labels.",
                    "You suggested sexual compulsions, sexual fixations, and related terms.",
                ]
            ],
            "metadatas": [
                [
                    {"wing": "notes", "room": "general", "source_file": "generic.txt"},
                    {"wing": "notes", "room": "general", "source_file": "quoted.txt"},
                ]
            ],
            "distances": [[0.20, 0.29]],
        }

        with (
            patch("mempalace.searcher.get_collection", return_value=mock_col),
            patch(
                "mempalace.searcher.get_closets_collection",
                side_effect=Exception("no closets"),
            ),
        ):
            result = search_memories(
                'you suggested "sexual compulsions" and other options', "/tmp/fake-palace"
            )
        assert result["results"][0]["source_file"] == "quoted.txt"

    def test_entity_boost_promotes_named_result(self):
        mock_col = MagicMock()
        mock_col.query.return_value = {
            "ids": [["doc_a", "doc_b"]],
            "documents": [
                [
                    "We talked about ukulele practice with a friend during the lesson.",
                    "I started ukulele lessons with Rachel and we practiced together.",
                ]
            ],
            "metadatas": [
                [
                    {"wing": "notes", "room": "music", "source_file": "generic.txt"},
                    {"wing": "notes", "room": "music", "source_file": "rachel.txt"},
                ]
            ],
            "distances": [[0.19, 0.24]],
        }

        with (
            patch("mempalace.searcher.get_collection", return_value=mock_col),
            patch(
                "mempalace.searcher.get_closets_collection",
                side_effect=Exception("no closets"),
            ),
        ):
            result = search_memories(
                "What did I do with Rachel on ukulele day?", "/tmp/fake-palace"
            )
        assert result["results"][0]["source_file"] == "rachel.txt"

    def test_temporal_boost_prefers_recent_match(self, monkeypatch):
        mock_col = MagicMock()
        mock_col.query.return_value = {
            "ids": [["doc_old", "doc_recent"]],
            "documents": [
                [
                    "Backup review and deployment checklist for the infra team.",
                    "Backup review and deployment checklist for the infra team.",
                ]
            ],
            "metadatas": [
                [
                    {
                        "wing": "ops",
                        "room": "infra",
                        "source_file": "old.txt",
                        "filed_at": "2026-02-10T10:00:00",
                    },
                    {
                        "wing": "ops",
                        "room": "infra",
                        "source_file": "recent.txt",
                        "filed_at": "2026-04-02T10:00:00",
                    },
                ]
            ],
            "distances": [[0.22, 0.26]],
        }

        monkeypatch.setattr(
            "mempalace.searcher._utc_now",
            lambda: __import__("datetime").datetime(2026, 4, 9, 12, 0, 0),
        )

        with (
            patch("mempalace.searcher.get_collection", return_value=mock_col),
            patch(
                "mempalace.searcher.get_closets_collection",
                side_effect=Exception("no closets"),
            ),
        ):
            result = search_memories("backup review last week", "/tmp/fake-palace")
        assert result["results"][0]["source_file"] == "recent.txt"


# ── search() (CLI print function) ─────────────────────────────────────


class TestSearchCLI:
    def test_search_prints_results(self, palace_path, seeded_collection, capsys):
        search("JWT authentication", palace_path)
        captured = capsys.readouterr()
        assert "JWT" in captured.out or "authentication" in captured.out

    def test_search_with_wing_filter(self, palace_path, seeded_collection, capsys):
        search("planning", palace_path, wing="notes")
        captured = capsys.readouterr()
        assert "Results for" in captured.out

    def test_search_with_room_filter(self, palace_path, seeded_collection, capsys):
        search("database", palace_path, room="backend")
        captured = capsys.readouterr()
        assert "Room:" in captured.out

    def test_search_with_wing_and_room(self, palace_path, seeded_collection, capsys):
        search("code", palace_path, wing="project", room="frontend")
        captured = capsys.readouterr()
        assert "Wing:" in captured.out
        assert "Room:" in captured.out

    def test_search_no_palace_raises(self, tmp_path):
        with pytest.raises(SearchError, match="No palace found"):
            search("anything", str(tmp_path / "missing"))

    def test_search_no_results(self, palace_path, collection, capsys):
        """Empty collection returns no results message."""
        # collection is empty (no seeded data)
        result = search("xyzzy_nonexistent_query", palace_path, n_results=1)
        captured = capsys.readouterr()
        # Either prints "No results" or returns None
        assert result is None or "No results" in captured.out

    def test_search_query_error_raises(self):
        """search raises SearchError when query fails."""
        mock_col = MagicMock()
        mock_col.query.side_effect = RuntimeError("boom")

        with patch("mempalace.searcher.get_collection", return_value=mock_col):
            with pytest.raises(SearchError, match="Search error"):
                search("test", "/fake/path")

    def test_search_n_results(self, palace_path, seeded_collection, capsys):
        search("code", palace_path, n_results=1)
        captured = capsys.readouterr()
        # Should have output with at least one result block
        assert "[1]" in captured.out
