"""SQLAlchemy mapped entities and read projections for schema revision 031.

Migrations exclusively own DDL. Context projections derive relationships/config
without persisting redundant columns in lifecycle tables.
"""

from typing import Any

from sqlalchemy import CHAR, BigInteger, Boolean, Integer, Text, text
from sqlalchemy.dialects.postgresql import (
    BYTEA,
    CITEXT,
    ENUM,
    JSONB,
    NUMERIC,
    TIMESTAMP,
    UUID,
    VARCHAR,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class RunInput(Base):
    __tablename__ = "run_inputs"
    run_id: Mapped[Any] = mapped_column(UUID(), primary_key=True)
    run_created_at: Mapped[Any] = mapped_column(TIMESTAMP(timezone=True), primary_key=True)
    name: Mapped[Any] = mapped_column(Text(), primary_key=True)
    value: Mapped[Any] = mapped_column(Text(), nullable=False)


class User(Base):
    __tablename__ = "users"
    id: Mapped[Any] = mapped_column(
        UUID(), primary_key=True, server_default=text("gen_random_uuid()")
    )
    email: Mapped[Any] = mapped_column(CITEXT(), nullable=False)
    display_name: Mapped[Any] = mapped_column(VARCHAR(length=120), nullable=False)
    password_hash: Mapped[Any] = mapped_column(Text(), nullable=False)
    role: Mapped[Any] = mapped_column(
        ENUM("user", "admin", name="user_role"),
        nullable=False,
        server_default=text("'user'::user_role"),
    )
    is_active: Mapped[Any] = mapped_column(Boolean(), nullable=False, server_default=text("true"))
    created_at: Mapped[Any] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at: Mapped[Any] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    email_verified_at: Mapped[Any] = mapped_column(TIMESTAMP(timezone=True), nullable=True)


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[Any] = mapped_column(
        UUID(), primary_key=True, server_default=text("gen_random_uuid()")
    )
    name: Mapped[Any] = mapped_column(VARCHAR(length=160), nullable=False)
    key: Mapped[Any] = mapped_column(VARCHAR(length=63), nullable=False)
    description: Mapped[Any] = mapped_column(Text(), nullable=True)
    owner_id: Mapped[Any] = mapped_column(UUID(), nullable=False)
    created_at: Mapped[Any] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at: Mapped[Any] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


class ProjectMember(Base):
    __tablename__ = "project_members"
    project_id: Mapped[Any] = mapped_column(UUID(), primary_key=True)
    user_id: Mapped[Any] = mapped_column(UUID(), primary_key=True)
    added_by: Mapped[Any] = mapped_column(UUID(), nullable=True)
    created_at: Mapped[Any] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


class Prompt(Base):
    __tablename__ = "prompts"
    id: Mapped[Any] = mapped_column(
        UUID(), primary_key=True, server_default=text("gen_random_uuid()")
    )
    project_id: Mapped[Any] = mapped_column(UUID(), nullable=False)
    key: Mapped[Any] = mapped_column(VARCHAR(length=63), nullable=False)
    name: Mapped[Any] = mapped_column(VARCHAR(length=160), nullable=False)
    description: Mapped[Any] = mapped_column(Text(), nullable=True)
    created_at: Mapped[Any] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at: Mapped[Any] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


class PromptVersion(Base):
    __tablename__ = "prompt_versions"
    id: Mapped[Any] = mapped_column(
        UUID(), primary_key=True, server_default=text("gen_random_uuid()")
    )
    prompt_id: Mapped[Any] = mapped_column(UUID(), nullable=False)
    version_number: Mapped[Any] = mapped_column(Integer(), nullable=False)
    template_body: Mapped[Any] = mapped_column(Text(), nullable=False)
    commit_message: Mapped[Any] = mapped_column(VARCHAR(length=500), nullable=False)
    created_by: Mapped[Any] = mapped_column(UUID(), nullable=False)
    created_at: Mapped[Any] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    provider: Mapped[Any] = mapped_column(VARCHAR(length=80), nullable=False)
    model: Mapped[Any] = mapped_column(VARCHAR(length=160), nullable=False)
    temperature: Mapped[Any] = mapped_column(NUMERIC(), nullable=True)
    max_output_tokens: Mapped[Any] = mapped_column(Integer(), nullable=True)


class Run(Base):
    __tablename__ = "runs"
    id: Mapped[Any] = mapped_column(
        UUID(), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[Any] = mapped_column(UUID(), nullable=False)
    version_id: Mapped[Any] = mapped_column(UUID(), nullable=False)
    status: Mapped[Any] = mapped_column(
        ENUM("completed", "failed", "blocked", name="run_status"), nullable=False
    )
    output_text: Mapped[Any] = mapped_column(Text(), nullable=True)
    prompt_tokens: Mapped[Any] = mapped_column(Integer(), nullable=False, server_default=text("0"))
    completion_tokens: Mapped[Any] = mapped_column(
        Integer(), nullable=False, server_default=text("0")
    )
    latency_ms: Mapped[Any] = mapped_column(Integer(), nullable=False, server_default=text("0"))
    cost: Mapped[Any] = mapped_column(
        NUMERIC(precision=18, scale=6), nullable=False, server_default=text("0")
    )
    error_code: Mapped[Any] = mapped_column(VARCHAR(length=80), nullable=True)
    request_id: Mapped[Any] = mapped_column(VARCHAR(length=128), nullable=True)
    created_at: Mapped[Any] = mapped_column(
        TIMESTAMP(timezone=True), primary_key=True, server_default=text("CURRENT_TIMESTAMP")
    )


class RunReservation(Base):
    __tablename__ = "run_reservations"
    id: Mapped[Any] = mapped_column(
        UUID(), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[Any] = mapped_column(UUID(), nullable=False)
    version_id: Mapped[Any] = mapped_column(UUID(), nullable=False)
    idempotency_key: Mapped[Any] = mapped_column(VARCHAR(length=128), nullable=False)
    request_fingerprint: Mapped[Any] = mapped_column(CHAR(length=64), nullable=False)
    claim_token: Mapped[Any] = mapped_column(UUID(), nullable=False)
    estimated_cost: Mapped[Any] = mapped_column(NUMERIC(precision=18, scale=6), nullable=False)
    status: Mapped[Any] = mapped_column(VARCHAR(length=20), nullable=False)
    error_code: Mapped[Any] = mapped_column(VARCHAR(length=80), nullable=True)
    created_at: Mapped[Any] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at: Mapped[Any] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


class Deployment(Base):
    __tablename__ = "deployments"
    id: Mapped[Any] = mapped_column(
        UUID(), primary_key=True, server_default=text("gen_random_uuid()")
    )
    version_id: Mapped[Any] = mapped_column(UUID(), nullable=False)
    environment: Mapped[Any] = mapped_column(
        ENUM("dev", "staging", "prod", name="deployment_environment"), nullable=False
    )
    status: Mapped[Any] = mapped_column(
        ENUM(
            "pending",
            "active",
            "rejected",
            "cancelled",
            "superseded",
            "rolled_back",
            name="deployment_status",
        ),
        nullable=False,
    )
    request_note: Mapped[Any] = mapped_column(Text(), nullable=True)
    review_note: Mapped[Any] = mapped_column(Text(), nullable=True)
    requested_by: Mapped[Any] = mapped_column(UUID(), nullable=False)
    reviewed_by: Mapped[Any] = mapped_column(UUID(), nullable=True)
    requested_at: Mapped[Any] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    reviewed_at: Mapped[Any] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    activated_at: Mapped[Any] = mapped_column(TIMESTAMP(timezone=True), nullable=True)


class ApiToken(Base):
    __tablename__ = "api_tokens"
    id: Mapped[Any] = mapped_column(
        UUID(), primary_key=True, server_default=text("gen_random_uuid()")
    )
    project_id: Mapped[Any] = mapped_column(UUID(), nullable=False)
    name: Mapped[Any] = mapped_column(VARCHAR(length=120), nullable=False)
    token_prefix: Mapped[Any] = mapped_column(VARCHAR(length=20), nullable=False)
    token_hash: Mapped[Any] = mapped_column(CHAR(length=64), nullable=False)
    created_by: Mapped[Any] = mapped_column(UUID(), nullable=False)
    created_at: Mapped[Any] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    expires_at: Mapped[Any] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    revoked_at: Mapped[Any] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    revoked_by: Mapped[Any] = mapped_column(UUID(), nullable=True)


class ProviderKey(Base):
    __tablename__ = "provider_keys"
    id: Mapped[Any] = mapped_column(
        UUID(), primary_key=True, server_default=text("gen_random_uuid()")
    )
    provider: Mapped[Any] = mapped_column(VARCHAR(length=80), nullable=False)
    alias: Mapped[Any] = mapped_column(VARCHAR(length=120), nullable=False)
    encrypted_secret: Mapped[Any] = mapped_column(BYTEA(), nullable=False)
    created_by: Mapped[Any] = mapped_column(UUID(), nullable=False)
    created_at: Mapped[Any] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    deactivated_at: Mapped[Any] = mapped_column(TIMESTAMP(timezone=True), nullable=True)


class ModelPrice(Base):
    __tablename__ = "model_pricing"
    id: Mapped[Any] = mapped_column(
        UUID(), primary_key=True, server_default=text("gen_random_uuid()")
    )
    provider: Mapped[Any] = mapped_column(VARCHAR(length=80), nullable=False)
    model: Mapped[Any] = mapped_column(VARCHAR(length=160), nullable=False)
    input_price_per_million: Mapped[Any] = mapped_column(
        NUMERIC(precision=18, scale=6), nullable=False
    )
    output_price_per_million: Mapped[Any] = mapped_column(
        NUMERIC(precision=18, scale=6), nullable=False
    )
    effective_from: Mapped[Any] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    effective_to: Mapped[Any] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    created_by: Mapped[Any] = mapped_column(UUID(), nullable=True)
    created_at: Mapped[Any] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


class Budget(Base):
    __tablename__ = "budgets"
    id: Mapped[Any] = mapped_column(
        UUID(), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[Any] = mapped_column(UUID(), nullable=True)
    project_id: Mapped[Any] = mapped_column(UUID(), nullable=True)
    monthly_limit: Mapped[Any] = mapped_column(NUMERIC(precision=18, scale=6), nullable=False)
    timezone: Mapped[Any] = mapped_column(
        VARCHAR(length=64), nullable=False, server_default=text("'UTC'::character varying")
    )
    created_by: Mapped[Any] = mapped_column(UUID(), nullable=True)
    created_at: Mapped[Any] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at: Mapped[Any] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    id: Mapped[Any] = mapped_column(UUID(), primary_key=True)
    user_id: Mapped[Any] = mapped_column(UUID(), nullable=False)
    issued_at: Mapped[Any] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    expires_at: Mapped[Any] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    revoked_at: Mapped[Any] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    revocation_reason: Mapped[Any] = mapped_column(Text(), nullable=True)
    created_at: Mapped[Any] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


class EmailVerificationToken(Base):
    __tablename__ = "email_verification_tokens"
    id: Mapped[Any] = mapped_column(
        UUID(), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[Any] = mapped_column(UUID(), nullable=False)
    token_hash: Mapped[Any] = mapped_column(CHAR(length=64), nullable=False)
    expires_at: Mapped[Any] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    used_at: Mapped[Any] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    created_at: Mapped[Any] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"
    id: Mapped[Any] = mapped_column(
        UUID(), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[Any] = mapped_column(UUID(), nullable=False)
    token_hash: Mapped[Any] = mapped_column(CHAR(length=64), nullable=False)
    expires_at: Mapped[Any] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    used_at: Mapped[Any] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    created_at: Mapped[Any] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


class PasswordHistory(Base):
    __tablename__ = "password_history"
    id: Mapped[Any] = mapped_column(
        UUID(), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[Any] = mapped_column(UUID(), nullable=False)
    password_hash: Mapped[Any] = mapped_column(Text(), nullable=False)
    created_at: Mapped[Any] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[Any] = mapped_column(BigInteger(), primary_key=True)
    actor_user_id: Mapped[Any] = mapped_column(UUID(), nullable=True)
    action: Mapped[Any] = mapped_column(VARCHAR(length=120), nullable=False)
    entity_type: Mapped[Any] = mapped_column(VARCHAR(length=80), nullable=False)
    entity_id: Mapped[Any] = mapped_column(UUID(), nullable=True)
    before_data: Mapped[Any] = mapped_column(JSONB(astext_type=Text()), nullable=True)
    after_data: Mapped[Any] = mapped_column(JSONB(astext_type=Text()), nullable=True)
    request_id: Mapped[Any] = mapped_column(VARCHAR(length=128), nullable=True)
    created_at: Mapped[Any] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


class ProjectInvitation(Base):
    __tablename__ = "project_invitations"
    id: Mapped[Any] = mapped_column(
        UUID(), primary_key=True, server_default=text("gen_random_uuid()")
    )
    project_id: Mapped[Any] = mapped_column(UUID(), nullable=False)
    user_id: Mapped[Any] = mapped_column(UUID(), nullable=False)
    invited_by: Mapped[Any] = mapped_column(UUID(), nullable=False)
    token_hash: Mapped[Any] = mapped_column(Text(), nullable=False)
    created_at: Mapped[Any] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    expires_at: Mapped[Any] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    accepted_at: Mapped[Any] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    revoked_at: Mapped[Any] = mapped_column(TIMESTAMP(timezone=True), nullable=True)


class SchemaMigration(Base):
    __tablename__ = "schema_migrations"
    version: Mapped[Any] = mapped_column(BigInteger(), primary_key=True)
    name: Mapped[Any] = mapped_column(Text(), nullable=False)
    checksum: Mapped[Any] = mapped_column(CHAR(length=64), nullable=False)
    applied_at: Mapped[Any] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


class VersionParent(Base):
    __tablename__ = "prompt_version_parents"
    version_id: Mapped[Any] = mapped_column(UUID(), primary_key=True)
    parent_version_id: Mapped[Any] = mapped_column(UUID(), nullable=False)


class VersionVariable(Base):
    __tablename__ = "prompt_version_variables"
    version_id: Mapped[Any] = mapped_column(UUID(), primary_key=True)
    ordinal: Mapped[Any] = mapped_column(Integer(), primary_key=True)
    name: Mapped[Any] = mapped_column(Text(), nullable=False)


class ReservationResult(Base):
    __tablename__ = "reservation_results"
    reservation_id: Mapped[Any] = mapped_column(UUID(), primary_key=True)
    run_id: Mapped[Any] = mapped_column(UUID(), nullable=False)
    run_created_at: Mapped[Any] = mapped_column(TIMESTAMP(timezone=True), nullable=False)


class DeploymentRollback(Base):
    __tablename__ = "deployment_rollbacks"
    deployment_id: Mapped[Any] = mapped_column(UUID(), primary_key=True)
    rollback_of_id: Mapped[Any] = mapped_column(UUID(), nullable=False)
    reason: Mapped[Any] = mapped_column(Text(), nullable=False)


class VersionContext(Base):
    __tablename__ = "version_context"
    id: Mapped[Any] = mapped_column(UUID(), primary_key=True)
    prompt_id: Mapped[Any] = mapped_column(UUID(), nullable=True)
    version_number: Mapped[Any] = mapped_column(Integer(), nullable=True)
    template_body: Mapped[Any] = mapped_column(Text(), nullable=True)
    commit_message: Mapped[Any] = mapped_column(VARCHAR(length=500), nullable=True)
    created_by: Mapped[Any] = mapped_column(UUID(), nullable=True)
    created_at: Mapped[Any] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    parent_version_id: Mapped[Any] = mapped_column(UUID(), nullable=True)
    model_config: Mapped[Any] = mapped_column(JSONB(astext_type=Text()), nullable=True)
    variables: Mapped[Any] = mapped_column(JSONB(astext_type=Text()), nullable=True)


class RunContext(Base):
    __tablename__ = "run_context"
    id: Mapped[Any] = mapped_column(UUID(), primary_key=True)
    user_id: Mapped[Any] = mapped_column(UUID(), nullable=True)
    version_id: Mapped[Any] = mapped_column(UUID(), nullable=True)
    status: Mapped[Any] = mapped_column(
        ENUM("completed", "failed", "blocked", name="run_status"), nullable=True
    )
    output_text: Mapped[Any] = mapped_column(Text(), nullable=True)
    prompt_tokens: Mapped[Any] = mapped_column(Integer(), nullable=True)
    completion_tokens: Mapped[Any] = mapped_column(Integer(), nullable=True)
    latency_ms: Mapped[Any] = mapped_column(Integer(), nullable=True)
    cost: Mapped[Any] = mapped_column(NUMERIC(precision=18, scale=6), nullable=True)
    error_code: Mapped[Any] = mapped_column(VARCHAR(length=80), nullable=True)
    request_id: Mapped[Any] = mapped_column(VARCHAR(length=128), nullable=True)
    created_at: Mapped[Any] = mapped_column(TIMESTAMP(timezone=True), primary_key=True)
    prompt_id: Mapped[Any] = mapped_column(UUID(), nullable=True)
    project_id: Mapped[Any] = mapped_column(UUID(), nullable=True)
    provider: Mapped[Any] = mapped_column(VARCHAR(length=80), nullable=True)
    model: Mapped[Any] = mapped_column(VARCHAR(length=160), nullable=True)
    input_variables: Mapped[Any] = mapped_column(JSONB(astext_type=Text()), nullable=True)


class ReservationContext(Base):
    __tablename__ = "reservation_context"
    id: Mapped[Any] = mapped_column(UUID(), primary_key=True)
    user_id: Mapped[Any] = mapped_column(UUID(), nullable=True)
    version_id: Mapped[Any] = mapped_column(UUID(), nullable=True)
    idempotency_key: Mapped[Any] = mapped_column(VARCHAR(length=128), nullable=True)
    request_fingerprint: Mapped[Any] = mapped_column(CHAR(length=64), nullable=True)
    claim_token: Mapped[Any] = mapped_column(UUID(), nullable=True)
    estimated_cost: Mapped[Any] = mapped_column(NUMERIC(precision=18, scale=6), nullable=True)
    status: Mapped[Any] = mapped_column(VARCHAR(length=20), nullable=True)
    error_code: Mapped[Any] = mapped_column(VARCHAR(length=80), nullable=True)
    created_at: Mapped[Any] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    updated_at: Mapped[Any] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    prompt_id: Mapped[Any] = mapped_column(UUID(), nullable=True)
    project_id: Mapped[Any] = mapped_column(UUID(), nullable=True)
    run_id: Mapped[Any] = mapped_column(UUID(), nullable=True)
    run_created_at: Mapped[Any] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    actual_cost: Mapped[Any] = mapped_column(NUMERIC(), nullable=True)


class DeploymentContext(Base):
    __tablename__ = "deployment_context"
    id: Mapped[Any] = mapped_column(UUID(), primary_key=True)
    version_id: Mapped[Any] = mapped_column(UUID(), nullable=True)
    environment: Mapped[Any] = mapped_column(
        ENUM("dev", "staging", "prod", name="deployment_environment"), nullable=True
    )
    status: Mapped[Any] = mapped_column(
        ENUM(
            "pending",
            "active",
            "rejected",
            "cancelled",
            "superseded",
            "rolled_back",
            name="deployment_status",
        ),
        nullable=True,
    )
    request_note: Mapped[Any] = mapped_column(Text(), nullable=True)
    review_note: Mapped[Any] = mapped_column(Text(), nullable=True)
    requested_by: Mapped[Any] = mapped_column(UUID(), nullable=True)
    reviewed_by: Mapped[Any] = mapped_column(UUID(), nullable=True)
    requested_at: Mapped[Any] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    reviewed_at: Mapped[Any] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    activated_at: Mapped[Any] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    prompt_id: Mapped[Any] = mapped_column(UUID(), nullable=True)
    rollback_of_id: Mapped[Any] = mapped_column(UUID(), nullable=True)
    rollback_reason: Mapped[Any] = mapped_column(Text(), nullable=True)


def fields(model: type[Any]) -> tuple[Any, ...]:
    return tuple(getattr(model, column.key) for column in model.__table__.columns)
