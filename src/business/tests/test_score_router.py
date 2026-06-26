"""
business/routers/score.py 域名校验单元测试
"""

import pytest
from fastapi import HTTPException

from business.routers.score import _validate_domains


def test_valid_domains():
    result = _validate_domains(["google.com", "example.org", "sub.domain.co.uk"])
    assert result == ["google.com", "example.org", "sub.domain.co.uk"]


def test_strips_and_lowercases():
    result = _validate_domains(["  Google.COM  ", " Example.ORG"])
    assert result == ["google.com", "example.org"]


def test_skips_empty():
    result = _validate_domains(["google.com", "", "  ", "example.org"])
    assert result == ["google.com", "example.org"]


def test_domain_too_long():
    long_domain = "a" * 254
    with pytest.raises(HTTPException) as exc_info:
        _validate_domains([long_domain])
    assert exc_info.value.status_code == 400
    assert "too long" in exc_info.value.detail.lower()


def test_invalid_domain_chars():
    with pytest.raises(HTTPException) as exc_info:
        _validate_domains(["bad_domain!.com"])
    assert exc_info.value.status_code == 400
    assert "invalid domain" in exc_info.value.detail.lower()


def test_batch_size_exceeded():
    domains = [f"d{i}.com" for i in range(1001)]
    with pytest.raises(HTTPException) as exc_info:
        _validate_domains(domains)
    assert exc_info.value.status_code == 400
    assert "batch size" in exc_info.value.detail.lower()


def test_batch_at_limit():
    domains = [f"d{i}.com" for i in range(1000)]
    result = _validate_domains(domains)
    assert len(result) == 1000
