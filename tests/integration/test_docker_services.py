"""
T092 — 静态验证 docker-compose.yml 包含全部 14 个服务及其配置
无需 Docker 运行，仅解析 YAML。
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

_COMPOSE_PATH = Path(__file__).resolve().parent.parent.parent / "docker-compose.yml"

# 平台要求的 14 个服务（注意 docker-compose 中 zookeeper 已被 KRaft 替代，
# 实际使用 kafka 内置 controller；kibana 由 jaeger 替代用于 tracing。
# 按需求文档列出的 14 个逻辑服务映射到 compose 中的 service 名称）
REQUIRED_SERVICES = {
    "gateway",
    "scoring-service",
    "agent-layer",
    "dag-engine",
    "postgres",
    "redis",
    "elasticsearch",
    "kafka",
    "starrocks-fe",
    "starrocks-be",
    "prometheus",
    "grafana",
    "jaeger",
    "frontend",
}

# 需要暴露端口的关键服务
PORT_SERVICES = {
    "gateway": "8000",
    "scoring-service": "8001",
    "redis": "6379",
    "elasticsearch": "9200",
    "postgres": "5432",
    "kafka": "9092",
    "prometheus": "9090",
    "grafana": "3001",
    "frontend": "3000",
}


@pytest.fixture(scope="module")
def compose_data() -> dict:
    assert _COMPOSE_PATH.exists(), f"docker-compose.yml not found at {_COMPOSE_PATH}"
    return yaml.safe_load(_COMPOSE_PATH.read_text(encoding="utf-8"))


class TestDockerServices:
    """Static validation of docker-compose.yml."""

    def test_all_required_services_present(self, compose_data):
        """docker-compose.yml must define all 14 required services."""
        services = set(compose_data.get("services", {}).keys())
        missing = REQUIRED_SERVICES - services
        assert not missing, f"Missing services: {missing}"

    def test_services_have_healthcheck_or_depends_on(self, compose_data):
        """Each service should have a healthcheck or depends_on configured."""
        services = compose_data.get("services", {})
        unconfigured = []
        for name, cfg in services.items():
            has_health = "healthcheck" in cfg
            has_depends = "depends_on" in cfg
            if not has_health and not has_depends:
                unconfigured.append(name)
        # Allow at most a few infrastructure services without either
        assert len(unconfigured) <= 2, (
            f"Services without healthcheck or depends_on: {unconfigured}"
        )

    def test_key_services_have_port_mappings(self, compose_data):
        """Key services must expose the expected ports."""
        services = compose_data.get("services", {})
        missing_ports = []
        for svc_name, expected_port in PORT_SERVICES.items():
            cfg = services.get(svc_name, {})
            ports = cfg.get("ports", [])
            port_strs = [str(p) for p in ports]
            found = any(expected_port in ps for ps in port_strs)
            if not found:
                missing_ports.append((svc_name, expected_port))
        assert not missing_ports, f"Missing port mappings: {missing_ports}"

    def test_network_defined(self, compose_data):
        """A shared network should be defined."""
        networks = compose_data.get("networks", {})
        assert len(networks) >= 1, "No networks defined in docker-compose.yml"

    def test_application_services_have_env_file(self, compose_data):
        """Application services (gateway, scoring, agent, dag) should use .env."""
        app_services = ["gateway", "scoring-service", "agent-layer", "dag-engine"]
        services = compose_data.get("services", {})
        for svc in app_services:
            cfg = services.get(svc, {})
            assert "env_file" in cfg, f"{svc} missing env_file"
