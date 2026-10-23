# RunIQ - Architecture

## Layers

```
┌────────────────────────── FRONTEND (Streamlit, multi-page) ──────────────────────────┐
│ main.py (Home) · pages/1_Matches … 12_Data_and_Settings                                │
│ utils/theme.py (dark / light CSS, top bar, cards, tables, charts) · utils/icons.py     │
│ utils/branding.py (embedded logo) · utils/ui_helpers.py (page setup, friendly errors)  │
└───────────────┬────────────────────────────────────────────────┬───────────────────────┘
                │ calls                                          │ calls (cached)
┌───────────────▼────────────── SERVICE LAYER ────────────────┐  ┌▼──────────────────────┐
│ catalog_service  (teams, players, matches, series, venues,   │  │ utils/api_cache.py    │
│                   records - read-only SQL)                   │  │ (st.cache_data)       │
│ analytics_service (Q1-Q25, guarded custom SQL)               │  └┬──────────────────────┘
│ base_crud_service + player / match / career / venue services │   │
│ cricsheet_importer (download, parse, load, derive)           │   │
│ sync_service (API -> SQL) · ranking_service (snapshots)      │   │
│ api_parsers (pure JSON -> objects) · card_builders · api_probe│  │
└───────────────┬──────────────────────────────────────────────┘   │
                │                                                  │
┌───────────────▼───────────────────┐         ┌────────────────────▼─────────────┐
│ DATABASE LAYER                     │         │ API LAYER                         │
│ utils/db_connection.py (engine,    │         │ api/cricbuzz_client.py            │
│  transactions, run_query)          │         │  - auth headers, timeouts         │
│ models/schema.py · views.py        │         │  - retries (429 / 5xx)            │
│ SQLite | PostgreSQL | MySQL        │         │  - route fallback (v1 / newer)    │
└────────────────────────────────────┘         │ api/endpoints.py (all routes)     │
                                               └────────────────┬─────────────────┘
                                                                │ HTTPS
                                                      Cricbuzz Cricket API (RapidAPI)
Cricsheet zips ─(requests)─> services/cricsheet_importer.py ─> database
CONFIG: config.py + .env      UTILITY: logger, exceptions, validators, sql_guard
```

## Data flows
1. **Import:** Cricsheet zip -> `parse_match` (pure) -> `_Writer` (teams, venues, players, series, matches, innings, performances) in batches of 200 matches -> `finalize_import` (main team, roles, venue country / capacity, series dates, career stats).
2. **Live pages:** page -> `api_cache` (cached) -> `CricbuzzClient.call` (route fallback, retries, error mapping) -> `api_parsers` -> cards / tables.
3. **Archive pages:** page -> `catalog_service` (parameterised SQL) -> DataFrame -> `theme.render_table` / charts.
4. **Sync:** *Save to database* -> `MatchSyncService` -> upsert teams, venues, series, matches (an API match that Cricsheet already has is *linked*, not duplicated) -> `api_sync_log`.
5. **CRUD:** form -> column validators -> cross-field rules -> INSERT / UPDATE / DELETE in a transaction -> friendly message.

## Why each module exists
| Module | Reason |
|---|---|
| `config.py` | secrets and tunables from the environment; nothing hard-coded |
| `utils/db_connection.py` | the single, swappable database gateway required by the brief |
| `models/schema.py` | database-agnostic tables, constraints and indexes |
| `services/cricsheet_importer.py` | turns real ball-by-ball files into relational data |
| `services/api_parsers.py` | all API JSON knowledge in one pure, unit-tested place |
| `api/endpoints.py` | all routes in one file with fallbacks |
| `services/catalog_service.py` | every read query for the pages (parameterised) |
| `sql/queries.py` | the 25 questions as data (title, concepts, SQL, parameters) |
| `utils/sql_guard.py` | defence in depth for the custom-SQL box |
| `utils/theme.py` | Cricbuzz-inspired dark / light look and reusable HTML components |

## Development milestones (suggested 14-day plan)
| Day | Milestone | Output |
|---|---|---|
| 1 | environment, Git, structure | venv, `.gitignore`, skeleton |
| 2-3 | database design and implementation | schema, indexes, views |
| 4-5 | Cricsheet import and derived data | importer + tests |
| 6-7 | API client and parsers | resilient client, parsed live data |
| 8-9 | SQL analytics Q1-Q25 | queries + page |
| 10-11 | pages and visuals | 12 pages, charts, dark / light theme |
| 12 | CRUD, testing, error-handling review | 117 tests |
| 13 | documentation, deployment | README, docs |
| 14 | demo recording and polish | video |

## Deployment options
* **Streamlit Community Cloud:** push to GitHub, create the app with `main.py`, add `RAPIDAPI_KEY` in *Secrets*. The local SQLite file is lost on every redeploy - use a hosted PostgreSQL via `DATABASE_URL` and import once.
* **Docker / Render / Railway / Azure / AWS:** `pip install -r requirements.txt`, then `streamlit run main.py --server.port $PORT --server.address 0.0.0.0` with `DATABASE_URL` and `RAPIDAPI_KEY` as environment variables; run `python -m scripts.import_cricsheet` once.

## Common mistakes avoided
hard-coded keys · string-built SQL · HTTP calls without timeouts · silent exception swallowing · duplicate rows when re-importing or re-syncing · calling the API on every Streamlit rerun · a single giant dropdown with 12,000 players.
