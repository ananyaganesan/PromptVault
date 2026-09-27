"""Query-plan regression tests over a representative partitioned run ledger."""

from collections.abc import Iterator
from typing import Any

import psycopg
import pytest

from api.app.db.representative_data import seed_representative_dataset


def walk_plan(node: dict[str, Any]) -> Iterator[dict[str, Any]]:
    yield node
    for child in node.get("Plans", []):
        yield from walk_plan(child)


@pytest.mark.database
def test_scoped_run_history_uses_an_index_and_prunes_partitions(database_url: str) -> None:
    summary = seed_representative_dataset(database_url, run_count=2_000)
    repeated = seed_representative_dataset(database_url, run_count=2_000)
    assert summary["run_count"] == repeated["run_count"] == 2_000
    with psycopg.connect(database_url) as connection:
        plan_document = connection.execute(
            """
            EXPLAIN (FORMAT JSON)
            SELECT id, status, cost, created_at
            FROM runs
            WHERE project_id = %s
              AND created_at >= date_trunc('month', CURRENT_TIMESTAMP)
              AND created_at < date_trunc('month', CURRENT_TIMESTAMP) + INTERVAL '1 month'
            ORDER BY created_at DESC
            LIMIT 25
            """,
            (summary["project_id"],),
        ).fetchone()[0]

    nodes = list(walk_plan(plan_document[0]["Plan"]))
    assert any("Index" in str(node.get("Node Type")) for node in nodes)
    relations = {str(node["Relation Name"]) for node in nodes if "Relation Name" in node}
    assert relations == {summary["partition"]}
    assert not any(
        node.get("Node Type") == "Seq Scan"
        and node.get("Relation Name") == summary["partition"]
        for node in nodes
    )


@pytest.mark.database
@pytest.mark.parametrize("scope", ["user_id", "prompt_id", "version_id"])
def test_run_scope_queries_have_index_backed_plans(database_url: str, scope: str) -> None:
    summary = seed_representative_dataset(database_url, run_count=2_000)
    with psycopg.connect(database_url) as connection:
        plan_document = connection.execute(
            f"""
            EXPLAIN (FORMAT JSON)
            SELECT id, created_at FROM runs
            WHERE {scope} = %s
              AND created_at >= date_trunc('month', CURRENT_TIMESTAMP)
              AND created_at < date_trunc('month', CURRENT_TIMESTAMP) + INTERVAL '1 month'
            ORDER BY created_at DESC
            LIMIT 25
            """,
            (summary[scope.removesuffix("_id") + "_id"],),
        ).fetchone()[0]

    nodes = list(walk_plan(plan_document[0]["Plan"]))
    assert any("Index" in str(node.get("Node Type")) for node in nodes)
    assert not any(
        node.get("Node Type") == "Seq Scan"
        and node.get("Relation Name") == summary["partition"]
        for node in nodes
    )
