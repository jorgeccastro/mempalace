"""
test_searcher.py — Tests for the programmatic search_memories API.

Tests the library-facing search interface (not the CLI print variant).
"""

from mempalace.searcher import _build_query_variants, _keyword_overlap, search_memories


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

    def test_similarity_is_bounded(self, palace_path, seeded_collection):
        result = search_memories("database", palace_path)
        assert result["results"]
        for hit in result["results"]:
            assert 0.0 <= hit["similarity"] <= 1.0

    def test_keyword_overlap_is_accent_insensitive(self):
        overlap = _keyword_overlap(["sincronizacao", "convidado"], "sincronização de acesso convidado")
        assert overlap == 1.0

    def test_build_query_variants_adds_keyword_only_form(self):
        variants = _build_query_variants("como ver pasta partilhada externa no OneDrive")
        assert "como ver pasta partilhada externa no OneDrive" in variants
        assert "ver pasta partilhada externa onedrive" in variants

    def test_keyword_rerank_promotes_lexical_match(self, monkeypatch):
        class FakeCollection:
            def count(self):
                return 3

            def query(self, **kwargs):
                return {
                    "ids": [["doc_b", "doc_a", "doc_c"]],
                    "documents": [[
                        "General cloud permissions discussion without the key terms.",
                        "SharePoint guest access for an externally shared folder with sync enabled.",
                        "Unrelated frontend planning note.",
                    ]],
                    "metadatas": [[
                        {"wing": "project", "room": "backend", "source_file": "b.txt"},
                        {"wing": "project", "room": "backend", "source_file": "a.txt"},
                        {"wing": "notes", "room": "planning", "source_file": "c.txt"},
                    ]],
                    "distances": [[0.20, 0.24, 0.80]],
                }

        class FakeClient:
            def __init__(self, path):
                self.path = path

            def get_collection(self, name):
                assert name == "mempalace_drawers"
                return FakeCollection()

        monkeypatch.setattr("mempalace.searcher.chromadb.PersistentClient", FakeClient)

        result = search_memories("guest access shared folder sync", "/tmp/fake-palace", n_results=2)
        assert result["results"][0]["source_file"] == "a.txt"

    def test_query_variants_expand_candidate_pool(self, monkeypatch):
        class FakeCollection:
            def count(self):
                return 2

            def query(self, **kwargs):
                query = kwargs["query_texts"][0]
                if query == "onedrive pasta externa convidado":
                    return {
                        "ids": [["doc_a"]],
                        "documents": [["Generic cloud discussion."]],
                        "metadatas": [[
                            {"wing": "project", "room": "backend", "source_file": "generic.txt"}
                        ]],
                        "distances": [[0.20]],
                    }
                return {
                    "ids": [["doc_b"]],
                    "documents": [[
                        "Pasta partilhada externa com acesso de convidado e sincronização local."
                    ]],
                    "metadatas": [[
                        {"wing": "project", "room": "backend", "source_file": "expanded.txt"}
                    ]],
                    "distances": [[0.25]],
                }

        class FakeClient:
            def __init__(self, path):
                self.path = path

            def get_collection(self, name):
                assert name == "mempalace_drawers"
                return FakeCollection()

        monkeypatch.setattr("mempalace.searcher.chromadb.PersistentClient", FakeClient)

        result = search_memories("OneDrive pasta externa convidado", "/tmp/fake-palace", n_results=2)
        assert [hit["source_file"] for hit in result["results"]] == ["expanded.txt", "generic.txt"]
