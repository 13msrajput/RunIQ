# Demo video script (about 7 minutes)

1. **Intro (30 s)** - name RunIQ, the problem (cricket fans, analysts, fantasy players need live scores and deep stats in one place), tech stack (Python, Streamlit, SQL, REST API, Cricsheet data).
2. **Data (45 s)** - *Data & Settings*: show the import button / CLI, the status cards, explain Cricsheet (real ball-by-ball data) and the API key check.
3. **Home and theme (30 s)** - match strip, stat cards, switch dark <-> light.
4. **Matches (60 s)** - Live / Recent / Upcoming tabs (men, women), open the **Match Centre**: scorecard, fall of wickets, charts, commentary; then the Archive tab.
5. **Players and Teams (60 s)** - search a player, career table, charts, recent innings; a team page and head-to-head.
6. **Rankings and Stats (45 s)** - ICC rankings men / women, the RunIQ Index, batting / bowling records with filters.
7. **SQL Analytics (90 s)** - one beginner, one intermediate (Q12), one advanced (Q25) query, show the SQL; try `DROP TABLE` in the custom box to show the guard.
8. **Manage Data (45 s)** - create a player, update it, trigger a validation error, delete it.
9. **Code tour (60 s)** - folder structure, `db_connection.py`, `cricsheet_importer.py`, `cricbuzz_client.py` error handling, run `pytest`.
10. **Wrap-up (15 s)** - limitations (derived roles, API plan) and future work.
