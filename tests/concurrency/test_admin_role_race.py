from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg.errors import InsufficientPrivilege

SEEDED_ADMIN_ID = UUID("22222222-2222-4222-8222-222222222222")


@pytest.mark.database
def test_concurrent_cross_deactivation_preserves_one_active_admin(
    database_url: str,
) -> None:
    first = uuid4()
    second = uuid4()
    with psycopg.connect(database_url) as connection:
        connection.execute(
            """INSERT INTO users (id, email, display_name, password_hash, role, is_active, is_approved, email_verified_at)
               VALUES (%s, %s, 'Race Admin One', 'unused', 'super_admin', TRUE, TRUE, now()),
                      (%s, %s, 'Race Admin Two', 'unused', 'super_admin', TRUE, TRUE, now())""",
            (first, f"admin-race-{first}@example.com", second, f"admin-race-{second}@example.com"),
        )
        connection.execute(
            """UPDATE users SET role = 'user', is_active = FALSE
               WHERE role = 'super_admin' AND id NOT IN (%s, %s)""",
            (first, second),
        )

    barrier = Barrier(2)

    def deactivate(actor_id: UUID, target_id: UUID) -> str:
        try:
            with psycopg.connect(database_url) as connection:
                barrier.wait()
                connection.execute(
                    "SELECT admin_update_user(%s, %s, NULL, FALSE, FALSE, TRUE, NULL, FALSE)",
                    (target_id, actor_id),
                )
            return "deactivated"
        except InsufficientPrivilege:
            return "admin_required"

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(
                executor.map(
                    lambda pair: deactivate(*pair),
                    ((first, second), (second, first)),
                )
            )
        assert sorted(results) == ["admin_required", "deactivated"]
        with psycopg.connect(database_url) as connection:
            active_count = connection.execute(
                "SELECT count(*) FROM users WHERE role = 'super_admin' AND is_active"
            ).fetchone()[0]
        assert active_count == 1
    finally:
        with psycopg.connect(database_url) as connection:
            connection.execute(
                "UPDATE users SET role = 'super_admin', is_active = TRUE WHERE id = %s",
                (SEEDED_ADMIN_ID,),
            )
            connection.execute(
                "UPDATE users SET role = 'user', is_active = FALSE WHERE id IN (%s, %s)",
                (first, second),
            )
