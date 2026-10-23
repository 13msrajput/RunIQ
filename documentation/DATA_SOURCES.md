# Data sources, derived fields and definitions

## Sources
| Data | Source | Licence / terms |
|---|---|---|
| Matches, innings, ball-by-ball figures (Tests, ODIs, T20Is, men and women) | **Cricsheet** - `tests_json.zip`, `odis_json.zip`, `t20s_json.zip` (each contains both genders), `recently_added_N_json.zip` for updates | Open Data Commons Attribution License (ODC-By). Attribution is shown in the app footer |
| Live matches, scorecards, commentary, rankings, news, player profiles | **Cricbuzz Cricket API** on RapidAPI | RapidAPI terms; requires your own key |
| Static reference lists (city -> country, approximate stadium capacities, team codes) | `models/venue_reference.py` (public, rounded figures) | - |

Not used: cricbuzz.com web pages. Cricsheet withholds some matches (for example Afghanistan's); see its downloads page.

## Derived fields (estimates - Cricsheet does not provide them)
| Field | How it is derived |
|---|---|
| Player **main team** | the team the player appeared for most often |
| **Playing role** | Wicket-keeper: >= 3 stumpings and >= 4 per 100 matches. Bowler: bowled in >= 55 % of matches. All-rounder: bowled in >= 30 % of matches and bats no lower than about position 8. Otherwise Batsman |
| **Active** | played in the last two years |
| **Venue country** | city / venue name lookup, else the team that appears in >= 70 % of matches there |
| **Stadium capacity** | static approximate list |
| **Batting position** | order in which a batter first appears at the crease (striker or non-striker) |
| **Batting average** | runs / dismissals (retired-hurt is not a dismissal) |
| **Balls faced** | every ball except wides; **balls bowled** = legal deliveries; **runs conceded** = bat runs + wides + no-balls |
| **Bowler wickets** | bowled, caught, caught and bowled, lbw, stumped, hit wicket |
| **Career stats** | recomputed from the stored performances after each import |

## SQL question definitions worth knowing
* Q13 / Q24 "partnership" = two batters in **consecutive batting positions** of the same innings (as the brief describes); the runs are the sum of their individual scores.
* Q12 home / away uses the derived venue country.
* Q23 considers players who played in the last 12 months and have 10 innings.
* Q15 needs 5 close matches so one big innings cannot top the list.
