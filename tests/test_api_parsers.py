"""Parser tests with realistic sample payloads (no network)."""

from services.api_parsers import (
    dig,
    format_score,
    parse_any_matches,
    parse_commentary,
    parse_match_info,
    parse_matches_response,
    parse_news_detail,
    parse_news_list,
    parse_player_info,
    parse_rankings,
    parse_scorecard,
    parse_series_list,
    parse_table_payload,
    parse_team_players,
    parse_teams_list,
    parse_venue,
)

MATCHES = {
    "typeMatches": [
        {
            "matchType": "International",
            "seriesMatches": [
                {
                    "seriesAdWrapper": {
                        "seriesId": 77,
                        "seriesName": "WI tour of India",
                        "matches": [
                            {
                                "matchInfo": {
                                    "matchId": 1001,
                                    "seriesId": 77,
                                    "matchDesc": "5th T20I",
                                    "matchFormat": "T20",
                                    "state": "Complete",
                                    "status": "No result",
                                    "startDate": "1760000000000",
                                    "team1": {
                                        "teamId": 2,
                                        "teamName": "India",
                                        "teamSName": "IND",
                                    },
                                    "team2": {
                                        "teamId": 4,
                                        "teamName": "West Indies",
                                        "teamSName": "WI",
                                    },
                                    "venueInfo": {
                                        "id": 9,
                                        "ground": "M.Chinnaswamy Stadium",
                                        "city": "Bengaluru",
                                    },
                                },
                                "matchScore": {
                                    "team1Score": {
                                        "inngs1": {
                                            "runs": 118,
                                            "wickets": 5,
                                            "overs": 7.4,
                                        }
                                    }
                                },
                            }
                        ],
                    }
                },
                {"adDetail": {"name": "ad"}},
            ],
        },
        {
            "matchType": "Women",
            "seriesMatches": [
                {
                    "seriesAdWrapper": {
                        "seriesName": "W series",
                        "matches": [
                            {
                                "matchInfo": {
                                    "matchId": 2002,
                                    "team1": {"teamName": "India Women"},
                                    "team2": {"teamName": "Australia Women"},
                                }
                            }
                        ],
                    }
                }
            ],
        },
    ]
}


def test_dig_and_format_score():
    assert dig({"a": [{"b": 1}]}, "a", 0, "b") == 1 and dig({}, "a", default="x") == "x"
    assert (
        format_score({"inngs1": {"runs": 100, "wickets": 3, "overs": 20}})
        == "100/3 (20)"
    )
    assert (
        format_score(
            {"inngs1": {"runs": 400, "wickets": 8, "overs": 90, "isDeclared": True}}
        )
        == "400/8d (90)"
    )
    assert format_score(None) == "-"


def test_matches_parsing_and_women_flag():
    parsed = parse_matches_response(MATCHES)
    assert [m.match_id for m in parsed] == [1001, 2002]
    first = parsed[0]
    assert (
        first.team1_score == "118/5 (7.4)"
        and first.venue == "M.Chinnaswamy Stadium"
        and not first.is_women
    )
    assert (
        parsed[1].is_women
        and parse_matches_response(MATCHES, only_type="Women")[0].match_id == 2002
    )
    assert {m.match_id for m in parse_any_matches({"x": [MATCHES]})} == {
        1001,
        2002,
    }  # recursive extractor


def test_match_info():
    info = parse_match_info(
        {
            "matchInfo": {
                "matchDescription": "5th T20I",
                "tossResults": {"tossWinnerName": "WI", "decision": "BOWLING"},
                "venueInfo": {"ground": "G", "city": "C", "country": "India"},
                "team1": {
                    "name": "India",
                    "playerDetails": [{"fullName": "A", "captain": True}],
                },
                "team2": {"name": "WI", "playerDetails": []},
            }
        }
    )
    assert (
        info["toss"].startswith("WI chose")
        and info["venue"] == "G"
        and info["squads"]["India"][0]["Captain"]
    )


def test_scorecard_fow_partnerships():
    card = {
        "scoreCard": [
            {
                "inningsId": 1,
                "batTeamDetails": {
                    "batTeamName": "India",
                    "batsmenData": {
                        "bat_2": {"batName": "B", "runs": 5, "balls": 4},
                        "bat_1": {
                            "batName": "A",
                            "runs": 16,
                            "balls": 7,
                            "isKeeper": True,
                            "outDesc": "b X",
                        },
                    },
                },
                "bowlTeamDetails": {
                    "bowlersData": {
                        "bowl_1": {"bowlName": "X", "overs": 2, "wickets": 2}
                    }
                },
                "scoreDetails": {
                    "runs": 118,
                    "wickets": 5,
                    "overs": 7.4,
                    "runRate": 15.3,
                },
                "wicketsData": {
                    "wkt_1": {
                        "wktNbr": 1,
                        "wktRuns": 20,
                        "batName": "A",
                        "wktOver": 1.4,
                    }
                },
                "partnershipsData": {
                    "pat_1": {
                        "bat1Name": "A",
                        "bat1Runs": 1,
                        "bat2Name": "B",
                        "bat2Runs": 6,
                        "totalRuns": 13,
                        "totalBalls": 5,
                    }
                },
                "extrasData": {"total": 3, "wides": 2, "legByes": 1},
            }
        ]
    }
    inn = parse_scorecard(card)[0]
    assert (
        inn.total == "118-5 (7.4 Ov)"
        and list(inn.batting["Batter"]) == ["A (wk)", "B"]
        and inn.fow.loc[0, "Score"] == 20
        and inn.partnerships.loc[0, "Runs"] == 13
    )
    assert parse_scorecard({}) == []


def test_commentary_tokens():
    entries = parse_commentary(
        {
            "commentaryList": [
                {
                    "commText": "B0$ to B1$, FOUR",
                    "overNumber": 6.3,
                    "event": "four",
                    "commentaryFormats": {
                        "bold": {
                            "formatId": ["B0$", "B1$"],
                            "formatValue": ["Keemo Paul", "Shreyas Iyer"],
                        }
                    },
                },
                {"overSeparator": {}},
            ]
        }
    )
    assert entries == [
        {"over": 6.3, "event": "FOUR", "text": "Keemo Paul to Shreyas Iyer, FOUR"}
    ]


def test_lists_and_stats_parsers():
    assert (
        parse_series_list(
            {
                "seriesMapProto": [
                    {
                        "date": "OCTOBER 2026",
                        "series": [
                            {
                                "id": 1,
                                "name": "S",
                                "startDt": "1760000000000",
                                "endDt": "1761000000000",
                            }
                        ],
                    }
                ]
            }
        ).loc[0, "Series"]
        == "S"
    )
    assert list(
        parse_teams_list(
            {
                "list": [
                    {"teamName": "TEST TEAMS"},
                    {"teamId": 2, "teamName": "India", "teamSName": "IND"},
                ]
            }
        )["Team"]
    ) == ["India"]
    squad = parse_team_players(
        {
            "player": [
                {"name": "BATSMEN"},
                {"id": 1, "name": "A"},
                {"name": "BOWLERS"},
                {"id": 2, "name": "B"},
            ]
        }
    )
    assert list(squad["Role"]) == ["Batsmen", "Bowlers"]
    assert (
        parse_rankings(
            {
                "rank": [
                    {
                        "rank": "1",
                        "name": "X",
                        "country": "IND",
                        "rating": "900",
                        "trend": "Up",
                    }
                ]
            }
        ).loc[0, "Rating"]
        == 900
    )
    assert (
        parse_table_payload(
            {"headers": ["Player", "Runs"], "values": [{"values": ["A", "10"]}]}
        ).loc[0, "Runs"]
        == 10
        and parse_table_payload({}).empty
    )
    assert (
        parse_player_info(
            {"name": "V Kohli", "bat": "Right Handed Bat", "bio": "<p>Hello</p>"}
        )["Bio"]
        == "Hello"
    )
    assert parse_venue({"ground": "G", "capacity": "30000"})["Capacity"] == "30000"


def test_news():
    stories = parse_news_list(
        {
            "storyList": [
                {
                    "story": {
                        "id": 5,
                        "hline": "Big win",
                        "intro": "<b>Intro</b>",
                        "pubTime": "1760000000000",
                    }
                },
                {"ad": {}},
            ]
        }
    )
    assert (
        len(stories) == 1
        and stories[0]["intro"] == "Intro"
        and stories[0]["published"] is not None
    )
    detail = parse_news_detail(
        {
            "headline": "H",
            "content": [
                {"content": {"contentType": "Text", "contentValue": "<p>Para</p>"}},
                {"content": {"contentType": "Image"}},
            ],
        }
    )
    assert detail["paragraphs"] == ["Para"]
