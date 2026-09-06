# Session keyword search

`GET /api/v1/sessions?q=keyword` searches the summary, first and latest nonempty
user text, and the existing ID / Langfuse ID / agent / repository / branch fields.
The web search box uses the same API. Project, agent, time filters, pagination,
and soft deletion apply to both results and the total count.

The complete trimmed query must occur as a continuous literal substring in one
field, case-insensitively. There is no stemming, fuzzy matching, word splitting,
or query language. Chinese text works without a tokenizer. `%`, `_`, and `\`
are literal characters, not wildcards. Existing behavior is retained for queries
shorter than five characters: they do not activate the search filter. An empty
query lists sessions normally.

## Extraction and storage

`backend/app/services/session_search.py` contains extraction, the query predicate,
index creation, and historical backfill. Every POST/PUT import and upload passes
through the same persistence function; endpoint columns are written in the same
database transaction as the session. PUT replaces the stored conversation and
its endpoints, including clearing removed inputs.

The extractor uses message order, matching the importers' conversation order. It
selects the first and last nonempty user text, joining text blocks within a single
message with newlines. It excludes assistant text, tool results, image payloads,
and intermediate user turns. Supported sources include normalized
`metadata.conversation` / `metadata.messages`, Claude JSONL originals, opencode
originals, and conversations in `raw` (including `raw.metadata`). Converter
originals take precedence over their normalized copy so split or previously
omitted text blocks are preserved. With no conversation it falls back to
`user_input`. With no user text, only the existing fields are searchable.

Two nullable TEXT columns store the endpoints without truncation. Identical
endpoints, including a single-user-message session, store only one copy. These
columns are deferred in ORM reads and are not added to the API response.
`search_inputs_version` marks completed backfill rows. The full conversation is
not duplicated into a search document or indexed as JSON.

PostgreSQL uses one partial GIN expression index, `ix_agent_sessions_search_trgm`,
on the concatenated searchable fields, excluding soft-deleted sessions. The
expression is shared by migration and query generation. It consumes index space
without storing another combined TEXT column or requiring another service.
PostgreSQL automatically maintains the index on updates and deletes. A final
per-field literal check prevents matches crossing a field boundary.

This uses PostgreSQL's established [pg_trgm LIKE/ILIKE index support](https://www.postgresql.org/docs/16/pgtrgm.html#PGTRGM-INDEX),
not its similarity operators. SQLite development/tests retain an equivalent
literal predicate without the PostgreSQL performance guarantee (SQLite's native
case folding is limited for non-ASCII letters).

## Existing databases

On API startup, after adding missing columns:

1. Backfill live sessions in batches of 100, committing each batch and marking
   completed rows. Subsequent starts skip completed rows. PostgreSQL row locks
   serialize concurrent backfills with session updates.
2. Prefer stored metadata. Only if it contains no usable user conversation,
   read the original artifact from object storage once to recover raw-only inputs.
   If an artifact cannot be read, startup fails visibly and does not mark that
   batch complete; restoring access and restarting resumes the migration.
3. Install `pg_trgm` if absent, then create the index if absent.

Allow a maintenance window for the first rollout. Historical backfill may need
object-storage access; index creation uses regular `CREATE INDEX`, which blocks
writes while building. This is a one-time startup migration, consistent with the
repository's additive migration workflow. For a database role that cannot install
extensions, an administrator must preinstall `pg_trgm` in the application's
search path. Index creation still requires the table owner's privileges.
No object-storage reads or conversation parsing happen in a search request.

## Verification and performance

Run normal regression checks:

```bash
PYTHONPATH=backend .venv/bin/python -m pytest backend/tests -q
```

Run the PostgreSQL check against a disposable PostgreSQL database. It creates and
drops a uniquely named test schema, and installs `pg_trgm` in `public` if absent:

```bash
HQ_SEARCH_TEST_DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST/TEST_DATABASE \
  PYTHONPATH=backend .venv/bin/python -m pytest backend/tests/test_session_search_postgres.py -s
```

The integration check inserts 12,000 synthetic sessions with about 2 KB of total
endpoint text and 8 KB of irrelevant conversation content per session. It checks
actual `EXPLAIN (ANALYZE, BUFFERS)` plans for both pagination and count without
forcing index use, and verifies Chinese, literal escaping, update/delete
maintenance, and field-boundary correctness.

One local PostgreSQL 16 run (2026-09-07) measured:

| Measurement | Result |
| --- | ---: |
| Single-match page, database execution | 0.162 ms |
| Single-match count, database execution | 0.106 ms |
| Same count using per-field scans without the GIN predicate | 103.960 ms |
| Index build | 0.789 s |
| GIN index size | 1,957,888 bytes |
| Endpoint text, logical uncompressed bytes | 25,092,795 bytes |

These are synthetic, warm-cache database measurements, not an end-to-end latency
SLA. The fixture repeats text, so real index size will depend on vocabulary and
input lengths. Common keywords matching most sessions still require processing
many results, and queries with no extractable trigrams (such as only punctuation)
can scan the index/table. The five-character minimum does not eliminate that
case. Result serialization and network transfer retain the existing API cost.
