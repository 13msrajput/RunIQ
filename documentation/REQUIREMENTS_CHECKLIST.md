# Requirements checklist (project brief: Cricbuzz LiveStats)

## Mandatory
- [x] REST API integration with `requests` (timeouts, retries, error mapping) - `api/`
- [x] Multi-page Streamlit app - `main.py` + `pages/`
- [x] Home page: project description, tools used, navigation, how to use
- [x] Live Matches: live / recent / upcoming matches, scorecards (batting, bowling, extras, fall of wickets), match status, venue details - **Matches** + **Match Centre**
- [x] Top Player Stats: ICC rankings and career leaders (API) with charts, plus database leaders - **Rankings**, **Stats**, **Players**
- [x] SQL Queries & Analytics: the 25 questions with tabular output and the SQL shown - **SQL Analytics**
- [x] CRUD: create, read, update, delete players (plus matches, career stats, venues) with validation - **Manage Data**
- [x] Database-agnostic design with a centralised `utils/db_connection.py`
- [x] Indexes on frequently queried columns; NULL handling (COALESCE / NULLIF)
- [x] Beginner, intermediate and advanced SQL (JOINs, subqueries, CTEs, window functions)
- [x] Error handling for API, database, validation and imports
- [x] Secure credentials (`.env`, `.gitignore`)
- [x] Modular code, PEP 8 style, comments and docstrings
- [x] Git usage (`.gitignore`, commit instructions)
- [x] `requirements.txt`, schema (`sql/schema.sql`), documentation, tests

## Beyond the brief (done)
- [x] **Real data** for every international match, men and women, from Cricsheet; career stats derived from it
- [x] Match Centre charts (worm, Manhattan, run rate), head-to-head, series, venue and team records
- [x] Dark (default) and light theme, RunIQ logo embedded in code, professional icons
- [x] API -> SQL sync with duplicate linking, ranking snapshots, API key / endpoint tester
- [x] Custom SQL box with a safety guard, CSV download
- [x] 117 automated tests including every page in both themes

## Still yours to do
- [ ] Run the real import (`python -m scripts.import_cricsheet`) and add your RapidAPI key
- [ ] Run `python -m scripts.check_api` and send me the output if any endpoint fails
- [ ] Record the demo video (`DEMO_VIDEO_SCRIPT.md`) and push to GitHub
- [ ] Optional: `python -m scripts.export_sql --data` to create a SQL data dump for submission
