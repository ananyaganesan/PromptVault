from uuid import uuid4

import pytest
from api.app.errors import AppError
from api.app.schemas.prompts import PromptCreate
from api.app.schemas.versions import PromptVersionCreate
from api.app.services.prompt_versioning import extract_variables
from pydantic import ValidationError


def test_extract_variables_preserves_first_seen_order_without_duplicates() -> None:
    assert extract_variables(
        "Use {{ customer_message }} for {{order_id}} and {{customer_message}}."
    ) == ["customer_message", "order_id"]


def test_extract_variables_rejects_malformed_names() -> None:
    with pytest.raises(AppError) as error:
        extract_variables("Hello {{not-valid}}")

    assert error.value.status_code == 422
    assert error.value.code == "validation_error"


def test_prompt_creation_rejects_server_derived_version_fields() -> None:
    with pytest.raises(ValidationError):
        PromptCreate.model_validate(
            {
                "key": "support-reply",
                "name": "Support Reply",
                "template_body": "Hello {{name}}",
                "model_config": {
                    "provider": "gemini",
                    "model": "gemini-3.5-flash-lite",
                    "temperature": 0,
                    "max_output_tokens": 100,
                },
                "commit_message": "Initial",
                "version_number": 99,
                "variables": ["attacker_controlled"],
                "parent_version_id": str(uuid4()),
            }
        )


def test_prompt_and_version_requests_reject_internal_model_configuration_name() -> None:
    model_configuration = {
        "provider": "gemini",
        "model": "gemini-3.5-flash-lite",
        "temperature": 0,
        "max_output_tokens": 100,
    }
    with pytest.raises(ValidationError):
        PromptCreate.model_validate(
            {
                "key": "support-reply",
                "name": "Support Reply",
                "template_body": "Hello",
                "model_configuration": model_configuration,
                "commit_message": "Initial",
            }
        )
    with pytest.raises(ValidationError):
        PromptVersionCreate.model_validate(
            {
                "parent_version_id": str(uuid4()),
                "template_body": "Hello",
                "model_configuration": model_configuration,
                "commit_message": "Next",
            }
        )
