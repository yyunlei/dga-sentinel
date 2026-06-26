"""
Unit tests for alert filter logic and severity priority resolution.
Tasks: T004 (_build_filter_query), T006 (_SEVERITY_PRIORITY)
"""
from __future__ import annotations

import pytest

from business.routers.alerts import _build_filter_query, _SEVERITY_PRIORITY


# ---------------------------------------------------------------------------
# T004: _build_filter_query tests
# ---------------------------------------------------------------------------

class TestBuildFilterQuery:
    """Unit tests for the common ES filter query builder."""

    def test_no_filters_returns_match_all(self) -> None:
        result = _build_filter_query()
        assert result == {"match_all": {}}

    def test_severity_filter(self) -> None:
        result = _build_filter_query(severity="CRITICAL")
        assert result == {"bool": {"must": [{"term": {"severity.keyword": "CRITICAL"}}]}}

    def test_family_filter(self) -> None:
        result = _build_filter_query(family="qakbot")
        assert result == {"bool": {"must": [{"term": {"family.keyword": "qakbot"}}]}}

    def test_acknowledged_false(self) -> None:
        result = _build_filter_query(acknowledged=False)
        assert result == {"bool": {"must": [{"term": {"acknowledged": False}}]}}

    def test_acknowledged_true(self) -> None:
        result = _build_filter_query(acknowledged=True)
        assert result == {"bool": {"must": [{"term": {"acknowledged": True}}]}}

    def test_acknowledged_none_omitted(self) -> None:
        result = _build_filter_query(acknowledged=None)
        assert result == {"match_all": {}}

    def test_domain_wildcard(self) -> None:
        result = _build_filter_query(domain="evil")
        must = result["bool"]["must"]
        assert len(must) == 1
        assert must[0] == {"wildcard": {"domain.keyword": {"value": "*evil*"}}}

    def test_src_ip_exact_match(self) -> None:
        result = _build_filter_query(src_ip="10.0.0.1")
        must = result["bool"]["must"]
        assert {"term": {"src_ip.keyword": "10.0.0.1"}} in must

    def test_source_manual(self) -> None:
        result = _build_filter_query(source="manual")
        must = result["bool"]["must"]
        assert len(must) == 1
        bool_clause = must[0]["bool"]
        assert "should" in bool_clause
        assert bool_clause["minimum_should_match"] == 1

    def test_source_dag(self) -> None:
        result = _build_filter_query(source="dag")
        must = result["bool"]["must"]
        assert len(must) == 2
        assert {"exists": {"field": "pipeline_id"}} in must

    def test_pipeline_id_filter(self) -> None:
        result = _build_filter_query(pipeline_id="dga-realtime-v1")
        must = result["bool"]["must"]
        assert {"term": {"pipeline_id.keyword": "dga-realtime-v1"}} in must
    def test_score_min_only(self) -> None:
        result = _build_filter_query(score_min=0.5)
        must = result["bool"]["must"]
        assert {"range": {"score": {"gte": 0.5}}} in must

    def test_score_max_only(self) -> None:
        result = _build_filter_query(score_max=0.9)
        must = result["bool"]["must"]
        assert {"range": {"score": {"lte": 0.9}}} in must

    def test_score_range(self) -> None:
        result = _build_filter_query(score_min=0.3, score_max=0.8)
        must = result["bool"]["must"]
        assert {"range": {"score": {"gte": 0.3, "lte": 0.8}}} in must

    def test_time_range(self) -> None:
        result = _build_filter_query(
            start_time="2026-02-19T00:00:00Z",
            end_time="2026-02-19T23:59:59Z",
        )
        must = result["bool"]["must"]
        assert {
            "range": {
                "timestamp": {
                    "gte": "2026-02-19T00:00:00Z",
                    "lte": "2026-02-19T23:59:59Z",
                }
            }
        } in must

    def test_start_time_only(self) -> None:
        result = _build_filter_query(start_time="2026-02-19T00:00:00Z")
        must = result["bool"]["must"]
        assert {"range": {"timestamp": {"gte": "2026-02-19T00:00:00Z"}}} in must

    def test_combined_filters(self) -> None:
        result = _build_filter_query(
            severity="HIGH",
            family="necurs",
            acknowledged=False,
            domain="bad",
            score_min=0.7,
        )
        must = result["bool"]["must"]
        assert len(must) == 5
        assert {"term": {"severity.keyword": "HIGH"}} in must
        assert {"term": {"family.keyword": "necurs"}} in must
        assert {"term": {"acknowledged": False}} in must
        assert {"wildcard": {"domain.keyword": {"value": "*bad*"}}} in must
        assert {"range": {"score": {"gte": 0.7}}} in must

    def test_all_filters_combined(self) -> None:
        result = _build_filter_query(
            severity="CRITICAL",
            family="qakbot",
            acknowledged=True,
            domain="evil",
            src_ip="10.0.0.1",
            pipeline_id="dga-realtime-v1",
            score_min=0.5,
            score_max=1.0,
            start_time="2026-01-01T00:00:00Z",
            end_time="2026-12-31T23:59:59Z",
        )
        must = result["bool"]["must"]
        # severity + family + acknowledged + domain + src_ip + pipeline_id + score_range + time_range = 8
        assert len(must) == 8


# ---------------------------------------------------------------------------
# T006: _SEVERITY_PRIORITY tests
# ---------------------------------------------------------------------------

class TestSeverityPriority:
    """Unit tests for severity priority resolution."""

    def test_priority_ordering(self) -> None:
        assert _SEVERITY_PRIORITY["CRITICAL"] > _SEVERITY_PRIORITY["HIGH"]
        assert _SEVERITY_PRIORITY["HIGH"] > _SEVERITY_PRIORITY["MEDIUM"]
        assert _SEVERITY_PRIORITY["MEDIUM"] > _SEVERITY_PRIORITY["LOW"]

    def test_all_four_levels_present(self) -> None:
        assert set(_SEVERITY_PRIORITY.keys()) == {"CRITICAL", "HIGH", "MEDIUM", "LOW"}

    def test_max_extraction_from_mixed_buckets(self) -> None:
        """Simulate extracting max severity from ES terms buckets."""
        buckets = [
            {"key": "LOW", "doc_count": 10},
            {"key": "CRITICAL", "doc_count": 2},
            {"key": "MEDIUM", "doc_count": 5},
        ]
        max_sev = max(buckets, key=lambda s: _SEVERITY_PRIORITY.get(s["key"], 0))["key"]
        assert max_sev == "CRITICAL"

    def test_max_extraction_single_bucket(self) -> None:
        buckets = [{"key": "HIGH", "doc_count": 3}]
        max_sev = max(buckets, key=lambda s: _SEVERITY_PRIORITY.get(s["key"], 0))["key"]
        assert max_sev == "HIGH"

    def test_max_extraction_all_same(self) -> None:
        buckets = [
            {"key": "MEDIUM", "doc_count": 5},
            {"key": "MEDIUM", "doc_count": 3},
        ]
        max_sev = max(buckets, key=lambda s: _SEVERITY_PRIORITY.get(s["key"], 0))["key"]
        assert max_sev == "MEDIUM"

    def test_unknown_severity_defaults_to_zero(self) -> None:
        assert _SEVERITY_PRIORITY.get("UNKNOWN", 0) == 0
