from api.app.security import generate_runtime_token, hash_runtime_token


def test_runtime_token_is_prefixed_high_entropy_and_hashes_deterministically() -> None:
    token = generate_runtime_token()

    assert token.startswith("pv_live_")
    assert len(token) >= 50
    assert hash_runtime_token(token) == hash_runtime_token(token)
    assert len(hash_runtime_token(token)) == 64
    assert token not in hash_runtime_token(token)


def test_runtime_tokens_are_unique() -> None:
    assert generate_runtime_token() != generate_runtime_token()
