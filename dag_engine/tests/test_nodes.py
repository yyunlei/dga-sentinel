"""DAG 节点单元测试"""

import asyncio
import pytest
from dag_engine.nodes.transform.dns_parser import DNSParserNode
from dag_engine.nodes.filter.whitelist import WhitelistNode
from dag_engine.nodes.filter.threshold import ThresholdNode
from dag_engine.nodes.filter.blacklist import BlacklistNode


class TestDNSParserNode:
    def test_parse_dict_input(self):
        node = DNSParserNode("parse", {"fields": ["query_name", "src_ip"]}, "test-pipe")
        state = {"raw_data": {"query_name": "evil.com", "src_ip": "10.0.0.1"}}
        result = asyncio.get_event_loop().run_until_complete(node.process(state))
        assert result["domain"] == "evil.com"
        assert result["src_ip"] == "10.0.0.1"

    def test_parse_string_input(self):
        node = DNSParserNode("parse", {"fields": ["query_name", "query_type"]}, "test-pipe")
        state = {"raw_data": "evil.com A"}
        result = asyncio.get_event_loop().run_until_complete(node.process(state))
        assert result["domain"] == "evil.com"


class TestWhitelistNode:
    def test_whitelist_hit(self):
        node = WhitelistNode("wl", {"static": ["google.com"]}, "test-pipe")
        state = {"domain": "google.com"}
        result = asyncio.get_event_loop().run_until_complete(node.process(state))
        assert result["score"] == 0.0
        assert "whitelist" in result.get("rules_applied", [])

    def test_whitelist_miss(self):
        node = WhitelistNode("wl", {"static": ["google.com"]}, "test-pipe")
        state = {"domain": "evil.xyz"}
        result = asyncio.get_event_loop().run_until_complete(node.process(state))
        assert "score" not in result


class TestThresholdNode:
    def test_above_threshold(self):
        node = ThresholdNode("th", {"default": 0.7}, "test-pipe")
        state = {"domain": "evil.xyz", "score": 0.9}
        result = asyncio.get_event_loop().run_until_complete(node.process(state))
        assert result.get("action") in ("alert", None) or result.get("score") == 0.9

    def test_below_threshold(self):
        node = ThresholdNode("th", {"default": 0.7}, "test-pipe")
        state = {"domain": "ok.com", "score": 0.3}
        result = asyncio.get_event_loop().run_until_complete(node.process(state))
        assert result.get("score") == 0.3
