import pytest

from optibroker_common.authentication import clear_caches


@pytest.fixture(autouse=True)
def _fresh_key_and_realm_caches():
    # The signing-key and realm-list caches are per process; no test may see
    # another's entries.
    clear_caches()
    yield
    clear_caches()
