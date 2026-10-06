from api.app.security import decrypt_provider_secret, encrypt_provider_secret


def test_provider_secret_encryption_round_trips_without_plaintext_leakage() -> None:
    secret = "provider-secret-value"
    encryption_key = "test-provider-encryption-key-at-least-32-chars"

    encrypted = encrypt_provider_secret(secret, encryption_key)

    assert secret.encode() not in encrypted
    assert decrypt_provider_secret(encrypted, encryption_key) == secret
    assert encrypt_provider_secret(secret, encryption_key) != encrypted
