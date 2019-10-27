import pytz
import pytest
from datetime import datetime, timedelta
from sports import models as sports

now = datetime(1993, 8, 18, tzinfo=pytz.utc)


@pytest.fixture
def league():
    league = sports.League.objects.create(
        name="Hogwarts Quidditch",
        slug="hq",
        abbr="HQ",
        current_season=now.year,
    )
    conf = league.conferences.create(name='Hogwarts', abbr='HW')
    for tm in [
        {"id": 1, "abbr": "GRF", "name": "Gryffindor", "logo": "sports/logos/hq/12656_Gold.jpg", "colors": "#c40002,#f39f00", "nickname": "Lions"},  # noqa
        {"id": 2, "abbr": "HUF", "name": "Hufflepuff", "logo": "sports/logos/hq/12657_Black.jpg", "colors": "#fff300,#000000", "nickname": "Badgers"},  # noqa
        {"id": 3, "abbr": "RVN", "name": "Ravenclaw", "logo": "sports/logos/hq/12654_Navy.jpg", "colors": "#0644ad,#7e4831", "nickname": "Eagles"},  # noqa
        {"id": 4, "abbr": "SLY", "name": "Slytherin", "logo": "sports/logos/hq/12655_Dark_Green.jpg", "colors": "#004101,#dcdcdc", "nickname": "Serpents"}  # noqa
    ]:
        league.teams.create(conference=conf, **tm)

    return league


@pytest.fixture
def gamesets(league):
    teams = league.team_dict
    gamesets = []

    for i, data in enumerate([
        [["GRF", "HUF"], ["RVN", "SLY"]],
        [["GRF", "RVN"], ["HUF", "SLY"]],
        [["SLY", "GRF"], ["HUF", "RVN"]]
    ]):
        rel = now + timedelta(days=i * 7)
        gs = league.gamesets.create(
            season=now.year,
            sequence=i + 1,
            opens=rel - timedelta(days=1),
            closes=rel + timedelta(days=6)
        )
        gamesets.append(gs)
        for j, (away, home) in enumerate(data, 1):
            gs.games.create(
                home=teams[home],
                away=teams[away],
                start_time=rel + timedelta(days=j),
                location='Hogwards'
            )

    return gamesets
