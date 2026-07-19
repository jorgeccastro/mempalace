"""Regression tests for the retrieval behavior retained by the JOR fork."""

from unittest.mock import MagicMock, patch

from mempalace.searcher import _build_query_variants, _keyword_overlap, search_memories


def _without_closets():
    return patch(
        "mempalace.searcher.get_closets_collection",
        side_effect=Exception("no closets"),
    )


def test_similarity_is_bounded(palace_path, seeded_collection):
    result = search_memories("database", palace_path)
    assert result["results"]
    assert all(0.0 <= hit["similarity"] <= 1.0 for hit in result["results"])


def test_keyword_overlap_is_accent_insensitive():
    overlap = _keyword_overlap(
        ["sincronizacao", "convidado"],
        "sincronização de acesso convidado",
    )
    assert overlap == 1.0


def test_build_query_variants_adds_keyword_only_form():
    variants = _build_query_variants("como ver pasta partilhada externa no OneDrive")
    assert "como ver pasta partilhada externa no OneDrive" in variants
    assert "ver pasta partilhada externa onedrive" in variants


def test_build_query_variants_adds_quoted_phrase():
    variants = _build_query_variants('lembras-te de "sexual compulsions" e outras opcoes')
    assert "sexual compulsions" in variants


def test_keyword_rerank_promotes_lexical_match():
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
    with patch("mempalace.searcher.get_collection", return_value=mock_col), _without_closets():
        result = search_memories("guest access shared folder sync", "/tmp/fake", n_results=2)
    assert result["results"][0]["source_file"] == "a.txt"
    assert all(0.0 <= hit["effective_distance"] <= 2.0 for hit in result["results"])


def test_query_variants_expand_candidate_pool():
    def fake_query(**kwargs):
        if kwargs["query_texts"][0] == "onedrive pasta externa convidado":
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
            "metadatas": [[{"wing": "project", "room": "backend", "source_file": "expanded.txt"}]],
            "distances": [[0.25]],
        }

    mock_col = MagicMock()
    mock_col.query.side_effect = fake_query
    with patch("mempalace.searcher.get_collection", return_value=mock_col), _without_closets():
        result = search_memories("OneDrive pasta externa convidado", "/tmp/fake", n_results=2)
    assert [hit["source_file"] for hit in result["results"]] == [
        "expanded.txt",
        "generic.txt",
    ]


def test_quoted_phrase_boost_promotes_exact_phrase():
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
    with patch("mempalace.searcher.get_collection", return_value=mock_col), _without_closets():
        result = search_memories('you suggested "sexual compulsions"', "/tmp/fake")
    assert result["results"][0]["source_file"] == "quoted.txt"


def test_entity_boost_promotes_named_result():
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
    with patch("mempalace.searcher.get_collection", return_value=mock_col), _without_closets():
        result = search_memories("What did I do with Rachel on ukulele day?", "/tmp/fake")
    assert result["results"][0]["source_file"] == "rachel.txt"


def test_temporal_boost_prefers_recent_match(monkeypatch):
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
    with patch("mempalace.searcher.get_collection", return_value=mock_col), _without_closets():
        result = search_memories("backup review last week", "/tmp/fake")
    assert result["results"][0]["source_file"] == "recent.txt"
