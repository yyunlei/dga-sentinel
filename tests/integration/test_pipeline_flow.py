"""Integration tests — DAG pipeline node flow"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock


class TestDNSParserNode:
    def test_parse_dict_input(self):
        from dag.nodes.transform.dns_parser import DNSParserNode
        node = DNSParserNode(node_id="parser-1", config={}, pipeline_id="test")
        state = {
            "raw_data": {
                "query_name": "evil.example.com",
                "src_ip": "10.0.0.1",
                "query_type": "A",
                "timestamp": "2026-02-11T00:00:00Z",
            }
        }
        result = asyncio.get_event_loop().run_until_complete(node.process(state))
        assert result["domain"] == "evil.example.com"
        assert result["src_ip"] == "10.0.0.1"
        assert "parsed" in result

    def test_parse_string_input(self):
        from dag.nodes.transform.dns_parser import DNSParserNode
        node = DNSParserNode(node_id="parser-2", config={}, pipeline_id="test")
        # DNSParserNode splits strings by whitespace: "query_name query_type src_ip timestamp"
        state = {"raw_data": "test.com A 192.168.1.1 2026-02-11T00:00:00Z"}
        result = asyncio.get_event_loop().run_until_complete(node.process(state))
        assert result["domain"] == "test.com"
        assert result["src_ip"] == "192.168.1.1"


class TestWhitelistNode:
    def test_whitelisted_domain(self):
        from dag.nodes.filter.whitelist import WhitelistNode
        node = WhitelistNode(
            node_id="wl-1",
            config={"static": ["google.com", "microsoft.com"]},
            pipeline_id="test",
        )
        state = {"domain": "google.com", "score": 0.9, "is_dga": True, "rules_applied": []}
        result = asyncio.get_event_loop().run_until_complete(node.process(state))
        assert result["is_dga"] is False
        assert result["score"] == 0.0

    def test_non_whitelisted_domain(self):
        from dag.nodes.filter.whitelist import WhitelistNode
        node = WhitelistNode(
            node_id="wl-2",
            config={"static": ["google.com"]},
            pipeline_id="test",
        )
        state = {"domain": "evil.com", "score": 0.9, "is_dga": True, "rules_applied": []}
        result = asyncio.get_event_loop().run_until_complete(node.process(state))
        assert result["is_dga"] is True
        assert result["score"] == 0.9


class TestThresholdNode:
    def test_above_threshold(self):
        from dag.nodes.filter.threshold import ThresholdNode
        node = ThresholdNode(
            node_id="th-1",
            config={"default": 0.7},
            pipeline_id="test",
        )
        state = {"score": 0.8, "tenant_id": "default", "rules_applied": []}
        result = asyncio.get_event_loop().run_until_complete(node.process(state))
        assert result["is_dga"] is True
        assert result["severity"] == "MEDIUM"

    def test_critical_severity(self):
        from dag.nodes.filter.threshold import ThresholdNode
        node = ThresholdNode(
            node_id="th-2",
            config={"default": 0.7},
            pipeline_id="test",
        )
        state = {"score": 0.96, "tenant_id": "default", "rules_applied": []}
        result = asyncio.get_event_loop().run_until_complete(node.process(state))
        assert result["is_dga"] is True
        assert result["severity"] == "CRITICAL"

    def test_below_threshold(self):
        from dag.nodes.filter.threshold import ThresholdNode
        node = ThresholdNode(
            node_id="th-3",
            config={"default": 0.7},
            pipeline_id="test",
        )
        state = {"score": 0.3, "tenant_id": "default", "rules_applied": []}
        result = asyncio.get_event_loop().run_until_complete(node.process(state))
        assert result["is_dga"] is False
        assert result["severity"] == "LOW"


class TestCheckpointManager:
    def test_save_and_get_offset(self):
        from dag.checkpoint import CheckpointManager
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock()
        mock_redis.get = AsyncMock(return_value="100")
        mgr = CheckpointManager(redis_client=mock_redis, key_prefix="ckpt:")
        asyncio.get_event_loop().run_until_complete(mgr.save_offset("topic-1", 0, 100))
        mock_redis.set.assert_called()
        offset = asyncio.get_event_loop().run_until_complete(mgr.get_offset("topic-1", 0))
        assert offset == 100

    def test_mark_and_check_processed(self):
        from dag.checkpoint import CheckpointManager
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock()
        mock_redis.exists = AsyncMock(return_value=1)
        mgr = CheckpointManager(redis_client=mock_redis, key_prefix="ckpt:")
        asyncio.get_event_loop().run_until_complete(mgr.mark_processed("evt-001"))
        result = asyncio.get_event_loop().run_until_complete(mgr.is_processed("evt-001"))
        assert result is True

    def test_not_processed(self):
        from dag.checkpoint import CheckpointManager
        mock_redis = AsyncMock()
        mock_redis.exists = AsyncMock(return_value=0)
        mgr = CheckpointManager(redis_client=mock_redis, key_prefix="ckpt:")
        result = asyncio.get_event_loop().run_until_complete(mgr.is_processed("evt-999"))
        assert result is False
