import pytest
from api.app.schemas.auth import LoginRequest, RegisterRequest
from pydantic import ValidationError


def test_registration_normalizes_email_and_display_name() -> None:
    request = RegisterRequest(
        email="  Alex@Example.COM ",
        password="CorrectHorse2026!",
        display_name="  Alex Morgan  ",
    )

    assert request.email == "alex@example.com"
    assert request.display_name == "Alex Morgan"


def test_registration_rejects_client_supplied_role() -> None:
    with pytest.raises(ValidationError):
        RegisterRequest.model_validate(
            {
                "email": "alex@example.com",
                "password": "CorrectHorse2026!",
                "display_name": "Alex Morgan",
                "role": "admin",
            }
        )


@pytest.mark.parametrize("password", ["", "x" * 129])
def test_login_enforces_password_length(password: str) -> None:
    with pytest.raises(ValidationError):
        LoginRequest(email="alex@example.com", password=password)


def test_login_accepts_short_password_for_credential_check() -> None:
    request = LoginRequest(email="alex@example.com", password="short")

    assert request.password.get_secret_value() == "short"


@pytest.mark.parametrize("password", ["short", "x" * 129])
def test_registration_enforces_password_length(password: str) -> None:
    with pytest.raises(ValidationError):
        RegisterRequest(
            email="alex@example.com",
            password=password,
            display_name="Alex Morgan",
        )


def test_login_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        LoginRequest.model_validate(
            {
                "email": "alex@example.com",
                "password": "CorrectHorse2026!",
                "role": "admin",
            }
        )
