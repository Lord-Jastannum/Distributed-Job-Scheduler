"""Retry delay calculation - shared by the worker and the reaper so both
requeue failed/stuck jobs using identical backoff logic."""
import random


def compute_retry_delay_seconds(strategy: str, attempt_number: int, base_delay: int, max_delay: int) -> float:
    """attempt_number is 1-indexed (this is the attempt that just failed)."""
    if strategy == "fixed":
        delay = base_delay
    elif strategy == "linear":
        delay = base_delay * attempt_number
    elif strategy == "exponential":
        delay = base_delay * (2 ** (attempt_number - 1))
    else:
        delay = base_delay

    delay = min(delay, max_delay)
    jitter = random.uniform(0, delay * 0.1)  # up to 10% jitter, avoids thundering herd
    return delay + jitter
