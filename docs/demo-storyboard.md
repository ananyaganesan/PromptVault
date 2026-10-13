# Demo storyboard (Phase 0)

1. Register and log in as a User.
2. Create a project, email an invitation, and have the recipient accept before membership is added.
3. Create a prompt with two variables and its initial version.
4. Save two additional versions; show immutable history, diff, and lineage.
5. Run v3 with the deterministic mock provider; show output, tokens, latency, and cost.
6. Deploy to staging and show the active version.
7. Request production deployment; show it remains pending.
8. Log in as Super Admin, review the diff and run evidence, and approve.
9. Fetch the prompt through the Serve API using a runtime token.
10. Roll back to v2; fetch again and show the changed active version.
11. Lower a budget, demonstrate a database-blocked run, raise it, and rerun.
12. Show organization analytics and the audit trail for the deployment, approval, rollback, token, and budget changes.

Completion evidence: screenshots or test output for each transition, including one forbidden user action and one repeated/concurrent review conflict.
