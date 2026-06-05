"""Generic HTTP/call client with retry logic.

Use retry_call() to wrap any no-arg callable that may raise transient errors.
The default policy handles Gemini SDK errors (rate limit, daily quota, 503);
raw HTTP errors from requests/httpx fall into the generic exponential-backoff
branch.

Example:
    from scripts.common.http_client import retry_call, QuotaExhaustedError

    def call_api():
        return client.models.generate_content(model=model, contents=prompt)

    try:
        response = retry_call(call_api, max_retries=3, context="gemini_ocr")
    except QuotaExhaustedError:
        # daily quota hit, stop calling
        ...
"""

import logging
import re
import time
from typing import Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class QuotaExhaustedError(Exception):
    """Daily quota exhausted — caller should stop making more requests."""


def parse_retry_delay(error_msg: str) -> int | None:
    """Parse retry delay (seconds) from a Gemini API error message.

    Returns parsed delay + 15s buffer, or None if no delay is mentioned.
    """
    patterns = [
        r"retry in (\d+\.?\d*)s",
        r"retrydelay.*?(\d+)s",
        r"please retry in (\d+\.?\d*)s",
    ]
    for pattern in patterns:
        match = re.search(pattern, error_msg, flags=re.IGNORECASE)
        if match:
            return int(float(match.group(1))) + 15
    return None


def _is_quota_signal(err_str: str, err_lower: str) -> bool:
    return "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "rate limit" in err_lower


def _is_daily_quota(err_str: str, err_lower: str) -> bool:
    return "quota" in err_lower and (
        "per day" in err_lower or "daily" in err_lower or "PerDay" in err_str
    )


def retry_call(
    fn: Callable[[], T],
    max_retries: int = 3,
    context: str = "call",
) -> T:
    """Run fn() with retry on transient errors.

    Retry policy:
    - QuotaExhaustedError: propagate immediately, no retry
    - 429 / RESOURCE_EXHAUSTED / "rate limit":
        - daily quota detected: raise QuotaExhaustedError
        - otherwise: sleep parsed delay (or 60s fallback)
    - Other Exception: exponential backoff 2**attempt
    - After max_retries attempts: re-raise the last exception

    Args:
        fn: no-arg callable that performs the call
        max_retries: total attempts (default 3)
        context: short label included in log messages to identify the caller

    Returns:
        Whatever fn() returns on success.
    """
    for attempt in range(max_retries):
        try:
            return fn()
        except QuotaExhaustedError:
            raise
        except Exception as e:
            err_str = str(e)
            err_lower = err_str.lower()
            if _is_quota_signal(err_str, err_lower):
                if _is_daily_quota(err_str, err_lower):
                    raise QuotaExhaustedError(
                        f"Daily quota exhausted: {err_str[:200]}"
                    ) from e
                wait_time = parse_retry_delay(err_str) or 60
                logger.warning(
                    "[%s] Rate limit hit. Sleeping %ss (attempt %d/%d)...",
                    context, wait_time, attempt + 1, max_retries,
                )
                time.sleep(wait_time)
            elif attempt < max_retries - 1:
                wait_time = 2 ** attempt
                logger.warning(
                    "[%s] Transient error: %s. Retrying in %ss (attempt %d/%d)...",
                    context, e, wait_time, attempt + 1, max_retries,
                )
                time.sleep(wait_time)
            else:
                logger.error(
                    "[%s] Failed after %d attempts: %s", context, max_retries, e
                )
                raise
    raise RuntimeError("retry_call: unreachable")
