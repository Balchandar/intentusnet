"""
Tests for idempotency enforcement.
"""

import tempfile
import shutil

import pytest

from intentusnet.wal.idempotency import IdempotencyStore


class TestIdempotency:
    """Test idempotency key enforcement."""

    def setup_method(self):
        self.store_dir = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.store_dir, ignore_errors=True)

    def test_first_registration(self):
        """Test registering new idempotency key."""
        store = IdempotencyStore(self.store_dir)

        idempotency_key = "test-key-001"
        execution_id = "exec-001"

        # First registration
        existing = store.check(idempotency_key)
        assert existing is None

        store.register(idempotency_key, execution_id)

        # Check returns execution_id
        existing = store.check(idempotency_key)
        assert existing == execution_id

    def test_duplicate_detection(self):
        """Test duplicate idempotency key detection."""
        store = IdempotencyStore(self.store_dir)

        idempotency_key = "test-key-002"
        execution_id_1 = "exec-001"

        store.register(idempotency_key, execution_id_1)

        # Duplicate check
        existing = store.check(idempotency_key)
        assert existing == execution_id_1

    def test_duplicate_with_different_execution_id(self):
        """Test duplicate key with different execution_id raises error."""
        store = IdempotencyStore(self.store_dir)

        idempotency_key = "test-key-003"
        execution_id_1 = "exec-001"
        execution_id_2 = "exec-002"

        store.register(idempotency_key, execution_id_1)

        # Attempting to register same key with different execution_id
        with pytest.raises(ValueError):
            store.register(idempotency_key, execution_id_2)

    def test_compute_key(self):
        """Test deterministic key computation."""
        store = IdempotencyStore(self.store_dir)

        envelope_1 = {"intent": {"name": "search"}, "params": {"q": "test"}}
        envelope_2 = {"intent": {"name": "search"}, "params": {"q": "test"}}
        envelope_3 = {"intent": {"name": "search"}, "params": {"q": "different"}}

        key_1 = store.compute_key(envelope_1)
        key_2 = store.compute_key(envelope_2)
        key_3 = store.compute_key(envelope_3)

        # Same envelope → same key
        assert key_1 == key_2

        # Different envelope → different key
        assert key_1 != key_3

    def test_persistence(self):
        """Test idempotency store persistence."""
        idempotency_key = "test-key-004"
        execution_id = "exec-001"

        # Register in first store instance
        store1 = IdempotencyStore(self.store_dir)
        store1.register(idempotency_key, execution_id)

        # Load in second store instance
        store2 = IdempotencyStore(self.store_dir)
        existing = store2.check(idempotency_key)

        assert existing == execution_id


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
