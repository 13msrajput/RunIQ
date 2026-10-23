"""Shared pytest fixtures: a database loaded with simulated Cricsheet-format matches (never the real DB)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(
    0, str(Path(__file__).resolve().parent.parent)
)  # make project modules importable

from services import cricsheet_importer as importer_module  # noqa: E402
from services.cricsheet_importer import CricsheetImporter  # noqa: E402
from tests.cricsheet_fixture import build_zips  # noqa: E402
from utils import db_connection  # noqa: E402

REAL_LOAD_PEOPLE = (
    importer_module.load_people_register
)  # the genuine function (tests that need it import this name)


@pytest.fixture(autouse=True)
def no_network_for_people_register(monkeypatch):
    """The Cricsheet people register is optional; tests never touch the network for it."""
    monkeypatch.setattr(importer_module, "load_people_register", lambda *a, **k: {})


@pytest.fixture(scope="session")
def fixture_zips(tmp_path_factory):
    """Zip files in the Cricsheet layout (simulated matches, created once per test session)."""
    return build_zips(tmp_path_factory.mktemp("zips"))


@pytest.fixture(scope="session")
def seeded_db(tmp_path_factory, fixture_zips):
    """A database filled by the REAL importer from the fixture zips."""
    path = tmp_path_factory.mktemp("db") / "test.db"
    db_connection.set_database_url(f"sqlite:///{path.as_posix()}")
    db_connection.reset_database()
    patch = (
        pytest.MonkeyPatch()
    )  # a session fixture cannot use the function-scoped monkeypatch
    patch.setattr(
        importer_module, "load_people_register", lambda *a, **k: {}
    )  # no network in tests
    try:
        summary = CricsheetImporter().run(zips=list(fixture_zips.values()))
    finally:
        patch.undo()
    assert summary.imported > 300 and summary.failed == 0, summary
    return path


@pytest.fixture()
def use_seeded(seeded_db):
    """Point the shared engine at the seeded database (earlier tests may have switched it)."""
    db_connection.set_database_url(f"sqlite:///{seeded_db.as_posix()}")
    return seeded_db


@pytest.fixture()
def use_seeded_copy(seeded_db, tmp_path):
    """A private COPY of the seeded database (for tests that write, e.g. the API sync) so other tests stay unaffected."""
    import shutil

    target = tmp_path / "copy.db"
    shutil.copy(seeded_db, target)
    db_connection.set_database_url(f"sqlite:///{target.as_posix()}")
    return target


@pytest.fixture()
def empty_db(tmp_path):
    """A fresh empty schema with two men's teams, one women's team and one venue (for CRUD / sync tests)."""
    db_connection.set_database_url(f"sqlite:///{(tmp_path / 'empty.db').as_posix()}")
    db_connection.reset_database()
    with db_connection.get_connection() as conn:
        from sqlalchemy import text

        conn.execute(
            text(
                "INSERT INTO teams (team_name, gender, display_name, short_name, country) VALUES ('India','male','India','IND','India'), ('Australia','male','Australia','AUS','Australia'), ('India','female','India Women','IND','India')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO venues (venue_name, city, country, capacity) VALUES ('Eden Gardens','Kolkata','India',66000)"
            )
        )
    return tmp_path
