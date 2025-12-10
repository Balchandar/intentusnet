from intentusnet.security.emcl.simple_hmac import SimpleHMACEMCLProvider

provider = SimpleHMACEMCLProvider(b"key-xyz-123")

payload = {"intent": "ResearchIntent", "payload": {"topic": "Networks"}}
wrapped = provider.encrypt(payload)
print("Encrypted:", wrapped)

decrypted = provider.decrypt(wrapped)
print("Decrypted:", decrypted)
