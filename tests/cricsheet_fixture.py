"""Test-only generator of Cricsheet-FORMAT match files (JSON version 1.3.0 layout).

IMPORTANT: the matches produced here are SIMULATED and exist only so the importer,
the 25 SQL queries and the UI can be tested offline in CI. They are never used by
the application itself - the app imports real matches from cricsheet.org.
"""

from __future__ import annotations

import json
import random
import zipfile
from datetime import date, timedelta
from pathlib import Path

MALE = [
    "India",
    "Australia",
    "England",
    "Pakistan",
    "South Africa",
    "New Zealand",
    "Sri Lanka",
    "West Indies",
]
FEMALE = ["India", "Australia", "England", "New Zealand", "South Africa"]
GROUNDS = {  # team -> [(venue name as printed by Cricsheet, city)]
    "India": [
        ("Wankhede Stadium, Mumbai", "Mumbai"),
        ("Eden Gardens, Kolkata", "Kolkata"),
        ("Narendra Modi Stadium, Ahmedabad", "Ahmedabad"),
    ],
    "Australia": [
        ("Melbourne Cricket Ground", "Melbourne"),
        ("Sydney Cricket Ground", "Sydney"),
        ("Adelaide Oval", "Adelaide"),
    ],
    "England": [
        ("Lord's", "London"),
        ("Old Trafford, Manchester", "Manchester"),
        ("Edgbaston, Birmingham", "Birmingham"),
    ],
    "Pakistan": [
        ("Gaddafi Stadium, Lahore", "Lahore"),
        ("National Stadium, Karachi", "Karachi"),
    ],
    "South Africa": [
        ("Newlands, Cape Town", "Cape Town"),
        ("Wanderers Stadium, Johannesburg", "Johannesburg"),
    ],
    "New Zealand": [
        ("Eden Park, Auckland", "Auckland"),
        ("Hagley Oval, Christchurch", "Christchurch"),
    ],
    "Sri Lanka": [
        ("R Premadasa Stadium, Colombo", "Colombo"),
        ("Galle International Stadium", "Galle"),
    ],
    "West Indies": [
        ("Kensington Oval, Bridgetown", "Bridgetown"),
        ("Sabina Park, Kingston", "Kingston"),
    ],
    "UAE": [
        ("Dubai International Cricket Stadium", "Dubai"),
        ("Sharjah Cricket Stadium", "Sharjah"),
    ],
}
FIRST = list("ABCDEFGHJKLMNPRSTVW")
LAST = [
    "Sharma",
    "Verma",
    "Iyer",
    "Nair",
    "Reddy",
    "Patel",
    "Singh",
    "Thompson",
    "Walker",
    "Harris",
    "Mitchell",
    "Cooper",
    "Bennett",
    "Clarke",
    "Davies",
    "Ellis",
    "Foster",
    "Malik",
    "Qureshi",
    "Siddiqui",
    "Botha",
    "Naidoo",
    "Pretorius",
    "Venter",
    "Anderson",
    "Campbell",
    "Wilson",
    "Perera",
    "Fernando",
    "Silva",
    "Brathwaite",
    "Charles",
    "Edwards",
    "Francis",
    "Hossain",
    "Rahman",
    "Khan",
    "Roberts",
    "Turner",
    "Wells",
]
PROFILE = {
    "male": {"T20": (150, 20, 4), "ODI": (270, 50, 10), "Test": (330, 70, None)},
    "female": {"T20": (125, 20, 4), "ODI": (230, 50, 10), "Test": (280, 70, None)},
}
KINDS = [
    ("caught", 0.45),
    ("bowled", 0.22),
    ("lbw", 0.13),
    ("run out", 0.08),
    ("stumped", 0.05),
    ("caught and bowled", 0.05),
    ("hit wicket", 0.02),
]


class World:
    """Teams, squads and venues used by one fixture build."""

    def __init__(self, rng: random.Random) -> None:
        self.rng, self.used_names, self.squads, self.skill, self.people = (
            rng,
            set(),
            {},
            {},
            {},
        )
        for gender, teams in (("male", MALE), ("female", FEMALE)):
            for team in teams:
                squad = []
                for slot in range(15):
                    while True:
                        name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
                        if name not in self.used_names:
                            self.used_names.add(name)
                            break
                    role = (
                        "bat"
                        if slot < 5
                        else (
                            "keeper"
                            if slot == 5
                            else "ar" if slot < 8 else "bowl" if slot < 13 else "bat"
                        )
                    )
                    bat = {
                        "bat": rng.uniform(1.0, 1.4),
                        "keeper": rng.uniform(0.8, 1.1),
                        "ar": rng.uniform(0.7, 1.0),
                        "bowl": rng.uniform(0.3, 0.5),
                    }[role]
                    bowl = {
                        "bat": 0.1,
                        "keeper": 0.0,
                        "ar": rng.uniform(0.5, 0.9),
                        "bowl": rng.uniform(0.9, 1.3),
                    }[role]
                    squad.append((name, role))
                    self.skill[name] = (
                        bat,
                        bowl,
                        rng.gauss(0, 0.08),
                    )  # (batting, bowling, yearly form drift)
                    self.people[name] = "".join(
                        rng.choice("0123456789abcdef") for _ in range(8)
                    )
                self.squads[(team, gender)] = squad

    def xi(self, team: str, gender: str) -> list[str]:
        squad, rng = self.squads[(team, gender)], self.rng
        pick = lambda role, n: rng.sample(
            [n_ for n_, r in squad if r == role], n
        )  # noqa: E731
        return pick("keeper", 1) + pick("bat", 4) + pick("ar", 2) + pick("bowl", 4)


def _outcome_prob(fmt: str, skill: float) -> list[tuple[str, float]]:
    base = {
        "T20": dict(w=0.055, d=0.30, f=0.13, s=0.08),
        "ODI": dict(w=0.035, d=0.42, f=0.09, s=0.03),
        "Test": dict(w=0.028, d=0.62, f=0.07, s=0.005),
    }[fmt]
    wicket = base["w"] / skill
    return [
        ("W", wicket),
        ("0", base["d"]),
        ("4", base["f"] * skill),
        ("6", base["s"] * skill),
        ("2", 0.07),
        ("1", 0.30),
        ("wd", 0.035),
        ("nb", 0.008),
    ]


def simulate_innings(
    world: World,
    team_xi: list[str],
    bowl_xi: list[str],
    fmt: str,
    gender: str,
    target: int | None,
    years: float,
    max_overs: int,
    max_bowler_overs: int | None,
) -> dict:
    rng = world.rng
    order = sorted(
        team_xi, key=lambda n: world.skill[n][0] * rng.uniform(0.8, 1.2), reverse=True
    )
    bowlers = sorted(bowl_xi, key=lambda n: world.skill[n][1], reverse=True)[:5]
    striker, non, nxt, wickets, runs, overs, bowled_overs, last = (
        order[0],
        order[1],
        2,
        0,
        0,
        [],
        {b: 0 for b in bowlers},
        None,
    )
    done = False
    for over_no in range(max_overs):
        eligible = [
            b
            for b in bowlers
            if b != last
            and (max_bowler_overs is None or bowled_overs[b] < max_bowler_overs)
        ] or bowlers
        bowler = rng.choice(eligible)
        bowled_overs[bowler] += 1
        last = bowler
        dels, legal = [], 0
        while legal < 6 and not done:
            skill = world.skill[striker][0] * pow(
                2.718, world.skill[striker][2] * years
            )
            kinds, weights = zip(*_outcome_prob(fmt, skill))
            outcome = rng.choices(kinds, weights=weights)[0]
            d = {
                "batter": striker,
                "bowler": bowler,
                "non_striker": non,
                "runs": {"batter": 0, "extras": 0, "total": 0},
            }
            if outcome in ("wd", "nb"):
                d["extras"] = {"wides": 1} if outcome == "wd" else {"noballs": 1}
                d["runs"] = {"batter": 0, "extras": 1, "total": 1}
            elif outcome == "W":
                kind = rng.choices(
                    [k for k, _ in KINDS], weights=[w for _, w in KINDS]
                )[0]
                out = (
                    striker
                    if rng.random() < 0.85
                    or kind
                    in (
                        "bowled",
                        "lbw",
                        "caught",
                        "stumped",
                        "caught and bowled",
                        "hit wicket",
                    )
                    else non
                )
                wk = {"kind": kind, "player_out": out}
                fielders = [n for n in bowl_xi if n != bowler]
                if kind == "caught":
                    wk["fielders"] = [{"name": rng.choice(fielders)}]
                elif kind == "stumped":
                    wk["fielders"] = [
                        {"name": bowl_xi[0]}
                    ]  # first name in the XI is the keeper
                elif kind == "run out":
                    wk["fielders"] = [
                        {"name": n} for n in rng.sample(fielders, rng.choice([1, 2]))
                    ]
                d["wickets"] = [wk]
                wickets += 1
                legal += 1
                if wickets >= 10 or nxt >= len(order):
                    done = True
                else:
                    if out == striker:
                        striker = order[nxt]
                    else:
                        non = order[nxt]
                    nxt += 1
            else:
                r = int(outcome)
                d["runs"] = {"batter": r, "extras": 0, "total": r}
                legal += 1
            runs += d["runs"]["total"]
            dels.append(d)
            if outcome in ("1",) and not done:
                striker, non = non, striker
            if target is not None and runs >= target:
                done = True
        overs.append({"over": over_no, "deliveries": dels})
        if not done:
            striker, non = non, striker
        if done:
            break
    return {"overs": overs, "runs": runs, "wickets": wickets, "all_out": wickets >= 10}


def make_match(
    world: World,
    home: str,
    away: str,
    gender: str,
    fmt: str,
    when: date,
    number: int,
    series: str,
    match_id: int,
) -> dict:
    rng = world.rng
    years = (when - date(2022, 1, 1)).days / 365.25
    ground, city = rng.choice(
        GROUNDS.get(home, GROUNDS["UAE"]) if rng.random() > 0.1 else GROUNDS["UAE"]
    )
    xi = {home: world.xi(home, gender), away: world.xi(away, gender)}
    toss_winner = rng.choice([home, away])
    decision = rng.choice(["bat", "field"])
    first = (
        toss_winner if decision == "bat" else (away if toss_winner == home else home)
    )
    second = away if first == home else home
    _, max_overs, max_b = PROFILE[gender][fmt]
    innings, outcome = [], {}
    if fmt == "Test":
        order = [first, second, first, second]
        res = []
        for i, team in enumerate(order, start=1):
            bat_first_total = sum(r["runs"] for r, t in res if t == team)
            target = None
            if i == 4:
                target = (
                    sum(r["runs"] for r, t in res if t == first)
                    - sum(r["runs"] for r, t in res if t == second)
                    + 1
                )
                if target <= 0:
                    break
            r = simulate_innings(
                world,
                xi[team],
                xi[first if team == second else second],
                fmt,
                gender,
                target,
                years,
                max_overs,
                None,
            )
            res.append((r, team))
            inn = {"team": team, "overs": r["overs"]}
            if not r["all_out"] and target is None:
                inn["declared"] = True
            if target:
                inn["target"] = {"overs": max_overs, "runs": target}
            innings.append(inn)
        tot = {
            first: sum(r["runs"] for r, t in res if t == first),
            second: sum(r["runs"] for r, t in res if t == second),
        }
        last = res[-1][0]
        if len(res) == 4 and last["runs"] >= (
            tot[first] - (tot[second] - last["runs"]) + 1
        ):
            outcome = {
                "winner": second,
                "by": {"wickets": max(1, 10 - last["wickets"])},
            }
        elif len(res) == 4 and last["all_out"] and tot[first] > tot[second]:
            outcome = {"winner": first, "by": {"runs": tot[first] - tot[second]}}
        else:
            outcome = {"result": "draw"}
        dates = [(when + timedelta(days=k)).isoformat() for k in range(5)]
    else:
        r1 = simulate_innings(
            world, xi[first], xi[second], fmt, gender, None, years, max_overs, max_b
        )
        r2 = simulate_innings(
            world,
            xi[second],
            xi[first],
            fmt,
            gender,
            r1["runs"] + 1,
            years,
            max_overs,
            max_b,
        )
        innings = [
            {"team": first, "overs": r1["overs"]},
            {
                "team": second,
                "overs": r2["overs"],
                "target": {"overs": max_overs, "runs": r1["runs"] + 1},
            },
        ]
        if r2["runs"] > r1["runs"]:
            outcome = {"winner": second, "by": {"wickets": max(1, 10 - r2["wickets"])}}
        elif r2["runs"] < r1["runs"]:
            outcome = {"winner": first, "by": {"runs": r1["runs"] - r2["runs"]}}
        else:
            outcome = {"result": "tie", "eliminator": rng.choice([first, second])}
        dates = [when.isoformat()]
    names = xi[home] + xi[away]
    return {
        "meta": {"data_version": "1.3.0", "created": dates[0], "revision": 1},
        "info": {
            "balls_per_over": 6,
            "city": city,
            "venue": ground,
            "dates": dates,
            "event": {"name": series, "match_number": number},
            "gender": gender,
            "teams": [home, away],
            "outcome": outcome,
            "toss": {"decision": decision, "winner": toss_winner},
            "player_of_match": [rng.choice(names)],
            "match_type": fmt if fmt != "T20" else "T20",
            "match_type_number": match_id,
            "overs": None if fmt == "Test" else max_overs,
            "team_type": "international",
            "season": str(when.year),
            "registry": {
                "people": {n: world.people[n] for n in names},
                "venues": {ground: "abcd1234"},
            },
            "players": {home: xi[home], away: xi[away]},
        },
        "innings": innings,
    }


def build_zips(
    out_dir: Path,
    seed: int = 11,
    men_series: int = 140,
    women_series: int = 36,
    today: date | None = None,
) -> dict[str, Path]:
    """Create tests_json.zip / odis_json.zip / t20s_json.zip (plus one club and one unofficial match for filter tests)."""
    today = today or date.today()
    rng = random.Random(seed)
    world = World(rng)
    files: dict[str, dict[str, dict]] = {"Test": {}, "ODI": {}, "T20": {}}
    counter = 1000
    for gender, teams, n in (
        ("male", MALE, men_series),
        ("female", FEMALE, women_series),
    ):
        for _ in range(n):
            fmt = rng.choices(
                ["Test", "ODI", "T20"],
                weights=[0.1, 0.35, 0.55] if gender == "male" else [0.03, 0.3, 0.67],
            )[0]
            home, away = rng.sample(teams, 2)
            start = date(2022, 1, 1) + timedelta(
                days=rng.randint(0, (today - date(2022, 1, 1)).days - 12)
            )
            games = rng.choice([1, 2, 3]) if fmt == "Test" else rng.choice([2, 3, 3, 5])
            series_name = (
                f"{away} {'Women ' if gender == 'female' else ''}tour of {home}"
            )
            for k in range(games):
                when = start + timedelta(days=(8 if fmt == "Test" else 3) * k)
                if when >= today:
                    continue
                counter += 1
                files[fmt][f"{counter}"] = make_match(
                    world, home, away, gender, fmt, when, k + 1, series_name, counter
                )
    # a club match and an unofficial T20 must be ignored by the importer
    club = make_match(
        world,
        "India",
        "Australia",
        "male",
        "T20",
        today - timedelta(days=5),
        1,
        "Indian Premier League",
        99999,
    )
    club["info"]["team_type"] = "club"
    files["T20"]["900001"] = club
    it20 = make_match(
        world,
        "India",
        "Australia",
        "male",
        "T20",
        today - timedelta(days=6),
        1,
        "Some Cup",
        99998,
    )
    it20["info"]["match_type"] = "IT20"
    files["T20"]["900002"] = it20
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {}
    for fmt, name in (
        ("Test", "tests_json.zip"),
        ("ODI", "odis_json.zip"),
        ("T20", "t20s_json.zip"),
    ):
        path = out_dir / name
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("README.txt", "simulated test fixture")
            for fid, doc in files[fmt].items():
                zf.writestr(f"{fid}.json", json.dumps(doc))
        paths["T20I" if fmt == "T20" else fmt] = path
    return paths
