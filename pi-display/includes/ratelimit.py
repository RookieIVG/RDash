"""Einfaches Rate-Limiting nach dem Token-Bucket-Verfahren."""

import threading
import time


class TokenBucket:
    def __init__(self, rate_per_sec, burst):
        self.rate = float(rate_per_sec)
        self.capacity = float(burst)
        self.tokens = self.capacity
        self.updated = time.monotonic()
        self._lock = threading.Lock()

    def allow(self, cost=1.0):
        with self._lock:
            now = time.monotonic()
            self.tokens = min(self.capacity, self.tokens + (now - self.updated) * self.rate)
            self.updated = now
            if self.tokens >= cost:
                self.tokens -= cost
                return True
            return False


class KeyedRateLimiter:
    """Ein Bucket pro Schlüssel (z. B. IP- oder Bluetooth-Adresse)."""

    def __init__(self, rate_per_sec, burst, max_keys=1000):
        self.rate = rate_per_sec
        self.burst = burst
        self.max_keys = max_keys
        self._buckets = {}
        self._lock = threading.Lock()

    def allow(self, key):
        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                if len(self._buckets) >= self.max_keys:
                    self._buckets.clear()  # Schutz vor Speicherwachstum
                bucket = self._buckets[key] = TokenBucket(self.rate, self.burst)
        return bucket.allow()
