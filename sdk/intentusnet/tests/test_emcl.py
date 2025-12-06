# tests/test_emcl.py

import pytest

from intentusnet.emcl.simple_hmac import SimpleHMACEMCLProvider
from intentusnet.emcl.aes_gcm import AESGCMEMCLProvider
from intentusnet.protocol.models import EMCLEnvelope


def test_simple_hmac_emcl_roundtrip():
    provider = SimpleHMACEMCLProvider(key="test-key")
    payload = {"foo": "bar", "x": 42}

    env = provider.encrypt(payload)
    assert isinstance(env, EMCLEnvelope)
    assert env.ciphertext

    decoded = provider.decrypt(env)
    assert decoded == payload


def test_simple_hmac_identity_chain():
    provider = SimpleHMACEMCLProvider(key="key", emcl_version="1.0")
    payload = {"a": 1}

    env = provider.encrypt(payload)
    # simple_hmac currently doesn't mutate identityChain, but ensure field accessible
    assert isinstance(env.identityChain, list)


@pytest.mark.skipif(
    __import__("importlib").util.find_spec("cryptography") is None,
    reason="cryptography not installed",
)
def test_aesgcm_emcl_roundtrip():
    import os

    key = os.urandom(32)
    provider = AESGCMEMCLProvider(key=key, emcl_version="1.0", identity="aes-agent")

    payload = {"secret": "value", "n": 123}
    env = provider.encrypt(payload)
    assert env.ciphertext
    assert env.nonce
    assert isinstance(env.identityChain, list)
    assert "aes-agent" in env.identityChain

    decoded = provider.decrypt(env)
    assert decoded == payload
