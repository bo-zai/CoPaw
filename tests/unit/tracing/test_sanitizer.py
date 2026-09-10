# -*- coding: utf-8 -*-
"""Tests for data sanitization utilities."""

import pytest

from swe.tracing.sanitizer import (
    SENSITIVE_KEYS,
    register_sensitive_values,
    sanitize_dict,
    sanitize_string,
    sanitize_trace_value,
    sanitize_user_message,
)


class TestSensitiveKeys:
    """Tests for SENSITIVE_KEYS constant."""

    def test_contains_common_keys(self):
        """Test that common sensitive keys are included."""
        assert "api_key" in SENSITIVE_KEYS
        assert "password" in SENSITIVE_KEYS
        assert "token" in SENSITIVE_KEYS
        assert "secret" in SENSITIVE_KEYS
        assert "authorization" in SENSITIVE_KEYS
        assert "credential" in SENSITIVE_KEYS

    def test_is_frozenset(self):
        """Test that SENSITIVE_KEYS is a frozenset."""
        assert isinstance(SENSITIVE_KEYS, frozenset)


class TestSanitizeDict:
    """Tests for sanitize_dict function."""

    def test_sanitize_none(self):
        """Test sanitizing None returns None."""
        result = sanitize_dict(None)
        assert result is None

    def test_sanitize_empty_dict(self):
        """Test sanitizing empty dict returns empty dict."""
        result = sanitize_dict({})
        assert result == {}

    def test_sanitize_normal_dict(self):
        """Test that normal keys are not modified."""
        data = {"name": "test", "count": 10, "enabled": True}
        result = sanitize_dict(data)

        assert result == data

    def test_sanitize_api_key(self):
        """Test that api_key is redacted."""
        data = {"api_key": "secret123", "name": "test"}
        result = sanitize_dict(data)

        assert result["api_key"] == "[REDACTED]"
        assert result["name"] == "test"

    def test_sanitize_password(self):
        """Test that password is redacted."""
        data = {"password": "mypass", "username": "user1"}
        result = sanitize_dict(data)

        assert result["password"] == "[REDACTED]"
        assert result["username"] == "user1"

    def test_sanitize_case_insensitive(self):
        """Test that key matching is case insensitive."""
        data = {"API_KEY": "secret", "Password": "pass", "SECRET_KEY": "s"}
        result = sanitize_dict(data)

        assert result["API_KEY"] == "[REDACTED]"
        assert result["Password"] == "[REDACTED]"
        assert result["SECRET_KEY"] == "[REDACTED]"

    def test_sanitize_partial_key_match(self):
        """Test that partial key matches are redacted."""
        data = {
            "my_api_key": "secret",
            "user_password_hash": "hash",
            "bearer_token": "token",
        }
        result = sanitize_dict(data)

        assert result["my_api_key"] == "[REDACTED]"
        assert result["user_password_hash"] == "[REDACTED]"
        assert result["bearer_token"] == "[REDACTED]"

    def test_sanitize_nested_dict(self):
        """Test that nested dicts are sanitized recursively."""
        data = {
            "config": {
                "api_key": "secret",
                "settings": {"password": "pass"},
            },
            "name": "test",
        }
        result = sanitize_dict(data)

        assert result["config"]["api_key"] == "[REDACTED]"
        assert result["config"]["settings"]["password"] == "[REDACTED]"
        assert result["name"] == "test"

    def test_sanitize_string_truncation(self):
        """Test that long strings are truncated."""
        long_value = "x" * 1000
        data = {"content": long_value}
        result = sanitize_dict(data, max_length=500)

        assert len(result["content"]) == 503  # 500 + "..."
        assert result["content"].endswith("...")

    def test_sanitize_list_values(self):
        """Test that list values are handled correctly."""
        data = {
            "items": [
                {"api_key": "secret1"},
                {"api_key": "secret2"},
                "normal_string",
            ],
        }
        result = sanitize_dict(data)

        assert result["items"][0]["api_key"] == "[REDACTED]"
        assert result["items"][1]["api_key"] == "[REDACTED]"
        assert result["items"][2] == "normal_string"

    def test_sanitize_list_with_long_strings(self):
        """Test that long strings in lists are truncated."""
        long_string = "x" * 1000
        data = {"items": [long_string, "short"]}
        result = sanitize_dict(data, max_length=100)

        assert len(result["items"][0]) == 103  # 100 + "..."
        assert result["items"][1] == "short"

    def test_sanitize_list_string_values_by_registered_secret(self):
        """列表中的字符串也应按登记的 secret 值脱敏。"""
        register_sensitive_values(["tenant-secret"])
        data = {"items": ["tenant-secret", "ok"]}

        result = sanitize_dict(data)

        assert result["items"] == ["[REDACTED]", "ok"]

    def test_sanitize_all_sensitive_keys(self):
        """Test that all SENSITIVE_KEYS are redacted."""
        data = {key: f"value_{key}" for key in SENSITIVE_KEYS}
        result = sanitize_dict(data)

        for key in SENSITIVE_KEYS:
            assert result[key] == "[REDACTED]"


class TestSanitizeString:
    """Tests for sanitize_string function."""

    def test_sanitize_none(self):
        """Test sanitizing None returns None."""
        result = sanitize_string(None)
        assert result is None

    def test_sanitize_short_string(self):
        """Test that short strings are not modified."""
        text = "Hello, world!"
        result = sanitize_string(text)

        assert result == text

    def test_sanitize_long_string(self):
        """Test that long strings are truncated."""
        text = "x" * 1000
        result = sanitize_string(text, max_length=500)

        assert len(result) == 503  # 500 + "..."
        assert result.endswith("...")

    def test_sanitize_exact_max_length(self):
        """Test string exactly at max_length is not truncated."""
        text = "x" * 500
        result = sanitize_string(text, max_length=500)

        assert result == text
        assert "..." not in result

    def test_sanitize_custom_max_length(self):
        """Test custom max_length parameter."""
        text = "x" * 1000
        result = sanitize_string(text, max_length=100)

        assert len(result) == 103  # 100 + "..."
        assert result.endswith("...")

    def test_redacts_registered_runtime_secret_value(self):
        """运行时注入的 secret 值应按值脱敏。"""
        register_sensitive_values(["tenant-secret"])

        result = sanitize_string("token=tenant-secret", max_length=500)

        assert result == "token=[REDACTED]"


class TestSanitizeTraceValue:
    """Tests for bounded JSON-compatible trace output values."""

    def test_redacts_nested_and_registered_secret_values(self):
        register_sensitive_values(["tenant-secret"])

        result = sanitize_trace_value(
            {
                "authorization": "Bearer direct-secret",
                "message": "cookie: sid=abc; token=tenant-secret",
                "nested": {"private_key": "secret-key-material"},
            },
        )

        assert result.value["authorization"] == "[REDACTED]"
        assert "tenant-secret" not in result.value["message"]
        assert "sid=abc" not in result.value["message"]
        assert result.value["nested"]["private_key"] == "[REDACTED]"

    @pytest.mark.parametrize(
        "value, secret_fragment",
        [
            ("Authorization: Bearer abcdefghijklmnop", "abcdefghijklmnop"),
            ("Cookie: sid=abcdef", "sid=abcdef"),
            (
                "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.signature",
                "eyJhbGciOiJIUzI1NiJ9",
            ),
            ("postgres://alice:password@db.example/app", "alice:password"),
            (
                "-----BEGIN "
                + "PRIVATE KEY-----\\nsecret\\n-----END "
                + "PRIVATE KEY-----",
                "secret",
            ),
        ],
    )
    def test_redacts_sensitive_fragments_in_text(self, value, secret_fragment):
        result = sanitize_trace_value(value)

        assert secret_fragment not in result.value

    def test_bounds_utf8_depth_and_collection_size(self):
        text_result = sanitize_trace_value("你" * 20, max_bytes=16)
        nested_result = sanitize_trace_value(
            {
                "items": ["你" * 20, "discarded", "also-discarded"],
                "nested": {"a": {"b": 1}},
            },
            max_depth=2,
            max_items=2,
        )

        assert text_result.truncated is True
        assert text_result.value.endswith("...")
        assert len(text_result.value.encode("utf-8")) <= 19
        assert nested_result.value["items"] == ["你" * 20, "discarded"]
        assert nested_result.value["nested"]["a"]["b"] == (
            "<max-depth-exceeded>"
        )


class TestSanitizeUserMessage:
    """Tests for sanitize_user_message function."""

    def test_sanitize_user_message_none(self):
        """Test sanitizing None message returns None."""
        result = sanitize_user_message(None)
        assert result is None

    def test_sanitize_user_message_short(self):
        """Test that short messages are not modified."""
        message = "What is the weather today?"
        result = sanitize_user_message(message)

        assert result == message

    def test_sanitize_user_message_long(self):
        """Test that long messages are truncated."""
        message = "x" * 1000
        result = sanitize_user_message(message, max_length=500)

        assert len(result) == 503
        assert result.endswith("...")

    def test_sanitize_user_message_with_newlines(self):
        """Test that messages with newlines are handled."""
        message = "Hello\nWorld\n" + "x" * 1000
        result = sanitize_user_message(message, max_length=500)

        assert len(result) == 503
