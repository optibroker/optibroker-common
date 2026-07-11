import os
import threading
import time

# Default time-to-live for cached Keycloak realm/cert data, in seconds.
# Can be overridden per-process with the KEYCLOAK_CACHE_TTL_SECONDS env var.
DEFAULT_TTL_SECONDS = int(os.environ.get("KEYCLOAK_CACHE_TTL_SECONDS", "300"))


class TTLCache:
    """
    A minimal thread-safe in-memory cache with per-entry time-to-live.

    Entries expire after ``ttl_seconds``. Expired values are still retained so
    they can be served as a stale fallback (see ``get_stale``) when a fresh
    fetch fails - this keeps authentication working through a brief Keycloak
    outage.
    """

    def __init__(self, ttl_seconds=DEFAULT_TTL_SECONDS):
        self._ttl = ttl_seconds
        self._store = {}
        self._lock = threading.Lock()

    def get(self, key):
        """Return the cached value if present and not expired, else None."""
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            value, expires_at = entry
            if time.monotonic() > expires_at:
                return None
            return value

    def get_stale(self, key):
        """Return the cached value ignoring expiry, or None if never cached."""
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            return entry[0]

    def set(self, key, value):
        """Store ``value`` under ``key`` with a fresh TTL."""
        with self._lock:
            self._store[key] = (value, time.monotonic() + self._ttl)

    def invalidate(self, key=None):
        """Drop a single key, or the whole cache when ``key`` is None."""
        with self._lock:
            if key is None:
                self._store.clear()
            else:
                self._store.pop(key, None)
