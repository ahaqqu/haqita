import sys
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from scripts.ocr.gemini_client import QuotaExhaustedError, call_gemini_ocr


DAILY_QUOTA_ERRORS = [
    '429 You have exhausted your daily quota. QuotaID: GenerateRequestsPerDayPerProjectPerModel-FreeTier',
    '429 RESOURCE_EXHAUSTED: quota metric per day limit exceeded',
    '429 Quota exceeded for quota metric GenerateRequests per day',
    'RESOURCE_EXHAUSTED: Quota exceeded for GenerateRequestsPerDayPerProjectPerModel',
]

RATE_LIMIT_ERRORS = [
    '429 RESOURCE_EXHAUSTED: retry in 30s',
    '429 rate limit exceeded. Please retry in 55.0s',
    '429 Quota exceeded for quota metric GenerateRequests per minute',
]


@pytest.fixture
def cfg():
    return {
        'ocr': {'provider': 'gemini', 'gemini': {'model': 'test-model', 'api_key': 'test-key'}},
        'store': 'lotte',
    }


def _mock_gemini(cfg, error_msg, max_retries=3):
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = Exception(error_msg)

    with patch('scripts.ocr.gemini_client.genai.Client', return_value=mock_client), \
         patch('scripts.ocr.gemini_client.get_prompt', return_value='test prompt'), \
         patch('scripts.ocr.gemini_client.load_dotenv'), \
         patch('builtins.open', mock_open(read_data=b'fake-image')), \
         patch('scripts.common.http_client.time.sleep'):
        return call_gemini_ocr('test.jpg', cfg, max_retries=max_retries)


class TestQuotaExhaustedDetection:
    @pytest.mark.parametrize("error_msg", DAILY_QUOTA_ERRORS)
    def test_daily_quota_raises_quota_exhausted(self, error_msg, cfg):
        with pytest.raises(QuotaExhaustedError, match="Daily quota exhausted"):
            _mock_gemini(cfg, error_msg)

    @pytest.mark.parametrize("error_msg", RATE_LIMIT_ERRORS)
    def test_rate_limit_does_not_raise_quota_exhausted(self, error_msg, cfg):
        with pytest.raises(Exception) as exc_info:
            _mock_gemini(cfg, error_msg, max_retries=1)
        assert not isinstance(exc_info.value, QuotaExhaustedError)

    def test_non_quota_error_does_not_raise_quota_exhausted(self, cfg):
        with pytest.raises(Exception) as exc_info:
            _mock_gemini(cfg, "Some other error", max_retries=1)
        assert not isinstance(exc_info.value, QuotaExhaustedError)
