"""Pipeline YAML 加载器测试"""

import pytest
import tempfile
from pathlib import Path

import yaml


class TestPipelineLoader:
    def _write_yaml(self, content: dict) -> str:
        f = tempfile.NamedTemporaryFile(suffix=".yaml", delete=False, mode="w")
        yaml.dump(content, f)
        f.close()
        return f.name

    def test_load_valid_pipeline(self):
        from dag_engine.loader import load_pipeline
        config = {
            "pipeline": {"name": "test-pipe", "mode": "stream", "version": "1.0"},
            "nodes": [
                {"id": "parse", "type": "dns_parser", "config": {"fields": ["query_name"]}},
            ],
        }
        path = self._write_yaml(config)
        pipe = load_pipeline(path)
        assert pipe.name == "test-pipe"
        assert pipe.mode == "stream"
        assert len(pipe.nodes) == 1

    def test_load_unknown_node_type(self):
        from dag_engine.loader import load_pipeline
        config = {
            "pipeline": {"name": "test", "mode": "batch"},
            "nodes": [
                {"id": "x", "type": "nonexistent_type", "config": {}},
            ],
        }
        path = self._write_yaml(config)
        pipe = load_pipeline(path)
        assert len(pipe.nodes) == 0  # unknown type skipped

    def test_load_multi_sink_expansion(self):
        from dag_engine.loader import load_pipeline
        config = {
            "pipeline": {"name": "test", "mode": "stream"},
            "nodes": [
                {"id": "sink", "type": "multi_sink", "config": {
                    "targets": [
                        {"type": "kafka", "topic": "alerts"},
                        {"type": "es", "index": "events"},
                    ]
                }},
            ],
        }
        path = self._write_yaml(config)
        pipe = load_pipeline(path)
        assert len(pipe.nodes) == 2  # expanded to 2 sink nodes
