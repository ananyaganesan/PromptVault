# Database design and implementation requirements

This file records the supplied academic evaluation requirements for PromptVault.
These requirements must be satisfied and supported by evidence before final project
submission. A working application alone does not establish compliance.

## 3. Database Design Requirements

Students must design the database before implementation.

### Mandatory deliverables

- Draw an Entity Relationship (ER) Diagram.
- Create a Relational Schema from the ER Diagram.
- Prepare a Data Dictionary (recommended).

### Design requirements

- Minimum 4 primary entities.
- Minimum 3 relationships.
- Minimum 8 database tables.
- Every table shall be derived from the ER Diagram.
- Every table shall contain a Primary Key.
- Appropriate Foreign Keys shall be defined.
- Apply appropriate constraints (`NOT NULL`, `UNIQUE`, `CHECK`, `DEFAULT`, etc.).
- Normalize all tables to Third Normal Form (3NF) or higher.
- Create indexes wherever required to improve query performance.

**Evaluation note:** Database tables created without a corresponding ER Diagram
will not be considered for evaluation.

## 4. Database Implementation

Students must implement the database using a free relational database management
system (RDBMS).

### Recommended databases

- PostgreSQL.
- MySQL.
- MariaDB.
- SQLite.

### Not recommended

- MongoDB (NoSQL).
- Firebase Firestore.
- CouchDB.
- Cassandra.

### Required implementation

- Database creation.
- Minimum 8–10 related tables.
- CRUD operations.
- Joins.
- Aggregate queries.
- Views.
- Transactions.
- At least one stored procedure, where supported by the selected database.
- At least one trigger, where supported by the selected database.
- Appropriate indexes for improving query performance.

PromptVault uses PostgreSQL. The table-count wording above is preserved from the
supplied requirements; it does not state a maximum of 10 tables.

## Final submission acceptance checklist

Leave items unchecked until the final schema and supporting evidence have been
reviewed. Do not infer completion from the prototype's feature checklist.

| Check | Acceptance evidence | Primary owner |
|---|---|---|
| [ ] Database design precedes implementation | Dated design artifacts/revision history; update the design before future schema changes | Jobin, with Ananya reviewing workflows |
| [ ] ER Diagram includes at least 4 primary entities and 3 relationships | Final ER Diagram with named entities, relationships, and cardinalities | Jobin |
| [ ] Every implemented table maps to the ER Diagram | Table-to-entity inventory, including authentication/history and infrastructure tables; identify physical partitions separately | Jobin |
| [ ] Relational Schema derives from the ER Diagram | Relations listing attributes, types, primary keys, foreign keys, and constraints | Jobin |
| [ ] Data Dictionary prepared (recommended) | Column definitions, purpose, types, nullability, defaults, keys, and constraints | Jobin |
| [ ] Table-count requirements satisfied | Inventory of at least 8 related logical tables; do not inflate counts with partitions or views | Jobin |
| [ ] Every table has a Primary Key | Schema/catalog query output, including composite keys where used | Jobin |
| [ ] Appropriate Foreign Keys and constraints exist | DDL and tests demonstrating valid and invalid writes | Jobin |
| [ ] All tables satisfy 3NF or higher | Table-by-table keys and functional-dependency analysis; resolve any normalization violations | Jobin |
| [ ] Database creation is reproducible | Fresh PostgreSQL creation and migration transcript | Jobin |
| [ ] CRUD operations demonstrated | SQL/API examples and working UI flows; explain immutable/append-only table restrictions | Both |
| [ ] Joins demonstrated | Executable queries joining related tables, with results | Jobin |
| [ ] Aggregate queries demonstrated | Executable count/sum/grouping queries with results | Jobin |
| [ ] Views demonstrated | View definitions and example query results | Jobin |
| [ ] Transactions demonstrated | Atomic operations and rollback/concurrency evidence | Jobin |
| [ ] At least one stored procedure demonstrated | PostgreSQL `CREATE PROCEDURE` definition and successful `CALL` example | Jobin |
| [ ] At least one trigger demonstrated | Trigger definition and observable before/after behavior | Jobin |
| [ ] Appropriate indexes demonstrated | Index inventory and representative query-plan evidence | Jobin |
| [ ] Final design, database, and application agree | Joint review of deployed schema, documentation, and user workflows | Both |

## Existing references and gaps to review

- [ER Diagram](erd.md).
- [Normalization discussion](normalization.md).
- [Database migrations and commands](../db/README.md).
- [Migration DDL](../db/migrations/).
- [SQL showcase queries](../db/showcase/).
- [Performance evidence guidance](performance.md).
- [Testing strategy](testing.md).

At the time this reference was added, the ER Diagram lists the original domain
tables but does not include `password_reset_tokens`, `password_history`, or the
`schema_migrations` tracking table. Reconcile the complete table inventory with the
diagram and relational schema before submission.

Existing SQL business routines use PostgreSQL functions. A function is not a
`CREATE PROCEDURE` stored procedure; verify and implement the explicit procedure
requirement with a documented `CALL` demonstration.

The existing normalization discussion describes intentional JSONB snapshots and
historical ledger fields. It is not a substitute for a table-by-table 3NF review.
Document functional dependencies and resolve deviations against the mandatory
normalization requirement rather than claiming compliance without analysis.

For any future database change, update the ER Diagram and relational schema first,
then add a new migration and appropriate verification. Do not edit already-applied
migrations or represent retrospective documentation as having preceded implementation.
