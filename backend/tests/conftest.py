import pytest

from app.main import app


@pytest.fixture(autouse=True)
def disable_rate_limiting():
    """The rate limiter is correct production behavior, but it would otherwise
    throttle the test suite itself since TestClient requests all share one
    'IP'. Disabling it here is standard practice - it's a CI concern, not a
    statement that the feature doesn't work (see test_phase6_bonus.py for a
    dedicated test that rate limiting actually fires when enabled)."""
    app.state.limiter.enabled = False
    yield
    app.state.limiter.enabled = True
