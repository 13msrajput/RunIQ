"""A fake Cricbuzz client that returns realistic sample payloads (used by the UI and probe tests)."""

from __future__ import annotations

from tests.test_api_parsers import MATCHES

SCORECARD = {
    "scoreCard": [
        {
            "inningsId": 1,
            "batTeamDetails": {
                "batTeamName": "India",
                "batsmenData": {
                    "bat_1": {
                        "batName": "S Samson",
                        "runs": 16,
                        "balls": 7,
                        "fours": 2,
                        "sixes": 1,
                        "strikeRate": 228.57,
                        "outDesc": "b Springer",
                        "isKeeper": True,
                    }
                },
            },
            "bowlTeamDetails": {
                "bowlersData": {
                    "bowl_1": {
                        "bowlName": "S Springer",
                        "overs": 2,
                        "maidens": 0,
                        "runs": 30,
                        "wickets": 2,
                        "economy": 15,
                    }
                }
            },
            "scoreDetails": {"runs": 118, "wickets": 5, "overs": 7.4, "runRate": 15.3},
            "wicketsData": {
                "wkt_1": {
                    "wktNbr": 1,
                    "wktRuns": 20,
                    "batName": "S Samson",
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
COMMENTARY = {
    "commentaryList": [
        {
            "commText": "B0$ to B1$, SIX",
            "overNumber": 7.1,
            "event": "six",
            "commentaryFormats": {
                "bold": {
                    "formatId": ["B0$", "B1$"],
                    "formatValue": ["Shamar Springer", "Naman Dhir"],
                }
            },
        }
    ]
}
INFO = {
    "matchInfo": {
        "matchDescription": "5th T20I",
        "tossResults": {"tossWinnerName": "West Indies", "decision": "BOWLING"},
        "venueInfo": {
            "ground": "M.Chinnaswamy Stadium",
            "city": "Bengaluru",
            "country": "India",
            "id": 9,
        },
        "team1": {
            "name": "India",
            "playerDetails": [
                {"fullName": "Abhishek Sharma", "role": "Batting Allrounder"}
            ],
        },
        "team2": {"name": "West Indies", "playerDetails": []},
    }
}
SERIES = {
    "seriesMapProto": [
        {
            "date": "OCTOBER 2026",
            "series": [
                {
                    "id": 77,
                    "name": "West Indies tour of India, 2026",
                    "startDt": "1760000000000",
                    "endDt": "1761000000000",
                }
            ],
        }
    ]
}
TEAMS = {
    "list": [
        {"teamName": "TEST TEAMS"},
        {"teamId": 2, "teamName": "India", "teamSName": "IND"},
    ]
}
PLAYERS = {
    "player": [
        {"name": "BATSMEN"},
        {
            "id": 1,
            "name": "Abhishek Sharma",
            "battingStyle": "Left-hand bat",
            "bowlingStyle": "Left-arm orthodox",
        },
    ]
}
RANKS = {
    "rank": [
        {
            "rank": "1",
            "name": "Abhishek Sharma",
            "country": "India",
            "rating": "907",
            "points": "907",
            "trend": "Flat",
        },
        {
            "rank": "2",
            "name": "Travis Head",
            "country": "Australia",
            "rating": "855",
            "points": "855",
            "trend": "Up",
        },
    ]
}
TOP = {
    "headers": ["Player", "Matches", "Runs"],
    "values": [
        {"values": ["Abhishek Sharma", "30", "1100"]},
        {"values": ["Travis Head", "28", "900"]},
    ],
}
SEARCH = {
    "player": [
        {"id": 1413, "name": "Virat Kohli", "teamName": "India", "dob": "1988-11-05"}
    ]
}
PLAYER = {
    "name": "Virat Kohli",
    "role": "Batsman",
    "bat": "Right Handed Bat",
    "intlTeam": "India",
    "DoB": "Nov 05, 1988",
    "bio": "<p>Run machine.</p>",
}
TABLE = {
    "headers": ["ROWHEADER", "Test", "ODI"],
    "values": [
        {"values": ["Matches", "123", "295"]},
        {"values": ["Runs", "9230", "13906"]},
    ],
}
NEWS = {
    "storyList": [
        {
            "story": {
                "id": 5,
                "hline": "Big win for India",
                "intro": "India clinch the series",
                "pubTime": "1760000000000",
                "context": "India",
                "source": "Cricbuzz Staff",
            }
        }
    ]
}
NEWS_DETAIL = {
    "headline": "Big win for India",
    "intro": "India clinch the series",
    "content": [
        {"content": {"contentType": "Text", "contentValue": "<p>First paragraph.</p>"}}
    ],
}
VENUE = {
    "ground": "M.Chinnaswamy Stadium",
    "city": "Bengaluru",
    "country": "India",
    "capacity": "40000",
}
RESPONSES = {
    "live": MATCHES,
    "recent": MATCHES,
    "upcoming": MATCHES,
    "match_info": INFO,
    "scorecard": SCORECARD,
    "commentary": COMMENTARY,
    "overs": {},
    "series_list": SERIES,
    "series_matches": MATCHES,
    "teams_list": TEAMS,
    "team_players": PLAYERS,
    "team_schedule": MATCHES,
    "team_results": MATCHES,
    "venue_info": VENUE,
    "rankings": RANKS,
    "top_stats": TOP,
    "player_search": SEARCH,
    "player_info": PLAYER,
    "player_batting": TABLE,
    "player_bowling": TABLE,
    "news_list": NEWS,
    "news_detail": NEWS_DETAIL,
}


class FakeApi:
    """Same interface as ``CricbuzzClient`` but answers from ``RESPONSES`` (no network)."""

    def __init__(self, *args, **kwargs):
        self.calls: list[str] = []

    def call(self, endpoint, /, **values):
        self.calls.append(endpoint)
        return RESPONSES[endpoint]

    def get_live_matches(self):
        return self.call("live")

    def get_recent_matches(self):
        return self.call("recent")

    def get_upcoming_matches(self):
        return self.call("upcoming")

    def get_match_info(self, match_id):
        return self.call("match_info")

    def get_scorecard(self, match_id):
        return self.call("scorecard")

    def get_commentary(self, match_id):
        return self.call("commentary")

    def get_series_list(self, category="international"):
        return self.call("series_list")

    def get_series_matches(self, series_id):
        return self.call("series_matches")

    def get_teams(self, category="international"):
        return self.call("teams_list")

    def get_team_players(self, team_id):
        return self.call("team_players")

    def get_team_schedule(self, team_id):
        return self.call("team_schedule")

    def get_team_results(self, team_id):
        return self.call("team_results")

    def get_venue(self, venue_id):
        return self.call("venue_info")

    def get_rankings(self, category="batsmen", format_type="test", is_women=False):
        return self.call("rankings")

    def get_top_stats(self, stats_type="mostRuns", stats_id=0):
        return self.call("top_stats")

    def search_player(self, name):
        return self.call("player_search")

    def get_player_info(self, player_id):
        return self.call("player_info")

    def get_player_batting(self, player_id):
        return self.call("player_batting")

    def get_player_bowling(self, player_id):
        return self.call("player_bowling")

    def get_news(self):
        return self.call("news_list")

    def get_news_detail(self, news_id):
        return self.call("news_detail")
