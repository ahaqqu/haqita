"""Unit tests for scripts/common/http_client.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest
from unittest.mock import patch

from scripts.common.http_client import (
    QuotaExhaustedError,
    parse_retry_delay,
    retry_call,
)


class TestParseRetryDelay:
    def test_parses_retry_in_seconds(self):
        assert parse_retry_delay("429 retry in 30s") == 45

    def test_parses_decimal_seconds(self):
        assert parse_retry_delay("Please retry in 55.0s") == 70

    def test_parses_retryDelay_field(self):
        assert parse_retry_delay('retryDelay: "44s"') == 59

    def test_returns_none_when_no_match(self):
        assert parse_retry_delay("Some random error") is None


class TestRetryCallSuccess:
    def test_returns_result_on_success(self):
        result = retry_call(lambda: "ok", context="test")
        assert result == "ok"


class TestRetryCallTransient:
    @patch("scripts.common.http_client.time.sleep")
    def test_503_retries_then_succeeds(self, mock_sleep):
        attempts = {"n": 0}

        def flaky():
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise Exception("503 UNAVAILABLE. high demand")
            return "ok"

        result = retry_call(flaky, max_retries=3, context="test")
        assert result == "ok"
        assert attempts["n"] == 3
        assert mock_sleep.call_count == 2

    @patch("scripts.common.http_client.time.sleep")
    def test_503_exhausts_retries_raises(self, mock_sleep):
        def always_fail():
            raise Exception("503 UNAVAILABLE")

        with pytest.raises(Exception, match="503"):
            retry_call(always_fail, max_retries=2, context="test")
        assert mock_sleep.call_count == 1


class TestRetryCallRateLimit:
    @patch("scripts.common.http_client.time.sleep")
    def test_429_per_minute_waits_parsed_delay(self, mock_sleep):
        attempts = {"n": 0}

        def fn():
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise Exception("429 RESOURCE_EXHAUSTED: Please retry in 30s")
            return "ok"

        result = retry_call(fn, max_retries=2, context="test")
        assert result == "ok"
        mock_sleep.assert_called_once_with(45)

    @patch("scripts.common.http_client.time.sleep")
    def test_429_daily_quota_raises_quota_exhausted(self, mock_sleep):
        def fn():
            raise Exception(
                "429 RESOURCE_EXHAUSTED: Quota exceeded for quota metric GenerateRequests per day"
            )

        with pytest.raises(QuotaExhaustedError, match="Daily quota exhausted"):
            retry_call(fn, max_retries=3, context="test")
        assert mock_sleep.call_count == 0


class TestRetryCallPropagation:
    @patch("scripts.common.http_client.time.sleep")
    def test_quota_exhausted_propagates_without_retry(self, mock_sleep):
        def fn():
            raise QuotaExhaustedError("already exhausted")

        with pytest.raises(QuotaExhaustedError, match="already exhausted"):
            retry_call(fn, max_retries=3, context="test")
        assert mock_sleep.call_count == 0
        assert mock_sleep.call_args_list == []


class TestRetryCallContext:
    @patch("scripts.common.http_client.time.sleep")
    def test_context_appears_in_log(self, mock_sleep):
        def fn():
            raise Exception("503 high demand")

        with patch("scripts.common.http_client.logger") as mock_logger:
            try:
                retry_call(fn, max_retries=2, context="gemini_ocr")
            except Exception:
                pass
            warning_calls = [
                c for c in mock_logger.warning.call_args_list if "gemini_ocr" in str(c)
            ]
            assert len(warning_calls) >= 1
