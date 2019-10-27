import os
import json

import pytest
from django.utils import timezone
from django.core.management import call_command
from django.core.exceptions import ValidationError

from sports import get_version
from sports import importers
from sports import admin
from sports import models as sports


def get_results(**kwargs):
    return {'sequence': kwargs.get('sequence', 1), 'season': 1993, 'type': 'REG', 'games': [{
        'home': kwargs.get('home', 'HUF'),
        'away': kwargs.get('away', 'GRF'),
        'home_score': kwargs.get('home_score', 150),
        'away_score': kwargs.get('away_score', 200),
        'status': kwargs.get('status', 'Half'),
    }]}


@pytest.mark.django_db
class TestMisc:

    def test_version(self):
        assert all([s.isdigit() for s in get_version().split('.')])

    def test_admin(self, league, gamesets):
        f = admin.GameSetForm(instance=gamesets[0])
        assert 'byes' in f.fields


@pytest.mark.django_db
class TestGameSet:

    def test_results(self, league, gamesets):
        gameset = gamesets[0]
        with pytest.raises(ValueError):
            gameset.update_results(None)

        bad_seq = get_results()
        bad_seq['sequence'] = 2
        with pytest.raises(ValueError):
            gameset.update_results(bad_seq)

        results = get_results()
        assert 0 == gameset.update_results(results)

        results['games'][0]['status'] = 'Final'
        assert 1 == gameset.update_results(results)
        assert gameset.last_game.score == (None, None)

        gameset = gamesets[-1]
        results = get_results(sequence=3, away='HUF', home='RVN', status='Final')
        assert 1 == gameset.update_results(results)
        assert gameset.last_game.score == (200, 150)

    def test_misc(self, league, gamesets):
        gameset = gamesets[0]
        games = list(gameset.games.all())
        assert gameset.end_time == games[-1].end_time

        game = games[0]
        assert isinstance(str(game), str)
        assert isinstance(game.short_description, str)

        assert not gameset.is_open
        assert gameset.has_started
        assert not gameset.in_progress
        assert timezone.now() > gameset.start_time

        gameset.reset_games_status()
        assert 2 == gameset.games.filter(status='U').count()


@pytest.mark.django_db
class TestGame:

    def test_manager(self, league, gamesets):
        assert sports.Game.objects.games_started().count() == 6

    def test_game(self, league, gamesets):
        grf = league.teams.get(abbr='GRF')
        sly = league.teams.get(abbr='SLY')
        g1, g2, g3 = list(grf.schedule())
        g1.set_scores(1, 0)
        g2.set_scores(1, 1)
        g3.set_scores(1, 0)

        assert sports.Game.objects.played().count() == 3
        res = list(
            i[1]
            for i in sports.Game.objects.display_results().items()
            if i[0] in [g1.id, g2.id, g3.id]
        )
        
        assert res[0] == {'id': 1, 'home__abbr': 'HUF', 'home_score': 0, 'away__abbr': 'GRF', 'away_score': 1, 'winner': 'GRF'}  # noqa
        assert res[1] == {'id': 3, 'home__abbr': 'RVN', 'home_score': 1, 'away__abbr': 'GRF', 'away_score': 1, 'winner': '__TIE__'}  # noqa
        assert res[2] == {'id': 5, 'home__abbr': 'GRF', 'home_score': 0, 'away__abbr': 'SLY', 'away_score': 1, 'winner': 'SLY'}  # noqa

        assert grf.record_as_string == '1-1-1'
        assert grf.complete_record() == [[0, 1, 0], [1, 0, 1], [1, 1, 1]]

        assert g2.is_tie
        assert not g2.is_home_win
        assert not g2.is_away_win

        assert not g1.is_tie
        assert not g1.is_home_win
        assert g1.is_away_win

        assert not g3.is_tie
        assert not g1.is_home_win
        assert g1.is_away_win

        assert g1.has_started
        assert g1.vs_description == 'Lions vs Badgers'
        assert g1.winner == grf

        assert g2.winner is None
        assert g3.winner == sly

        last = sports.Game.objects.last()
        last.set_scores(0, 1)
        assert last.winner.abbr == 'RVN'
        assert not last.in_progress


@pytest.mark.django_db
class TestLeague:

    def test_no_gamesets(self, league):
        assert league.current_gameset is None
        assert league.latest_gameset is None
        assert league.latest_season is None

    def test_league_misc(self, league, gamesets):
        assert [1993] == league.available_seasons
        assert 3 == league.season_gamesets().count()

    def test_export(self, league, gamesets):
        data = league.to_dict()
        assert data['schema'] == 'complete'
        assert 'league' in data
        assert 4 == len(data['league']['teams'])
        gss = data['season']['gamesets']
        assert 3 == len(gss)
        assert [2, 2, 2] == [len(gs['games']) for gs in gss]

    def test_create(self):
        l = sports.League.objects.create(name='Foo', abbr='foo')
        assert l.slug.isdigit()

        conf = l.conferences.create(name='Conf', abbr='conf')
        div = conf.divisions.create(name='Div')
        assert str(div) == 'Conf Div'


@pytest.mark.django_db
class TestTeam:

    def test_team(self, league, gamesets):
        team = league.teams.first()
        assert len(team.color_options) == 2
        assert team.byes().count() == 0
        assert team.record  == [0, 0, 0]
        assert team.record_as_string == '0-0'
        assert team.complete_record() == [[0, 0, 0], [0, 0, 0], [0, 0, 0]]

    def test_validators(self):
        with pytest.raises(ValidationError):
            sports.valid_team_abbr('__foo')

        with pytest.raises(ValidationError):
            sports.valid_team_colors('123efg')

        assert None == sports.valid_team_colors('#abc,000123,#a9c7ef')


def load_json(filename):
    filepath = os.path.join(os.path.dirname(__file__), filename)
    with open(filepath) as fin:
        return json.load(fin)


@pytest.mark.django_db
class TestImporters:

    def test_import_schema(self):
        try:
            importers.valid_schema({}, 'complete')
        except ValueError:
            pass
        else:
            assert False

        try:
            importers.valid_schema({'schema': 'league'}, 'complete')
        except ValueError:
            pass
        else:
            assert False

    def test_management_commands(self):
        call_command('import_sports', 'tests/quidditch.json')
        data = load_json('quidditch.json')
        data['season']['gamesets'][0].update(
            opens='2018-08-18T00:30Z',
            closes='2018-09-07T12:00Z'
        )
        league = sports.League.get('hq')
        gs = league.gamesets.first()
        opens, closes = gs.opens, gs.closes
        importers.import_season(sports.League, data)
        gs = sports.GameSet.objects.first()
        assert opens != gs.opens
        assert closes != gs.closes

    def test_import(self, client):
        nfl_data = load_json('nfl2019.json')

        league_info, teams_info = sports.League.import_league(nfl_data['league'])
        league, created = league_info
        assert created is True

        assert league.slug == 'nfl'
        assert league.abbr == 'NFL'
        assert league.current_season == 2019
        assert league.conferences.count() == 2
        assert sports.Division.objects.count() == 8
        assert league.teams.count() == 32

        info = league.import_season(nfl_data['season'])
        assert len(info) == 17
        assert league.gamesets.first().sequence == 1
        for gs, is_new, games in info:
            assert is_new is True
            assert all(is_new for g, is_new in games)
        assert sports.Game.objects.incomplete().count() == 256

        assert sports.Alias.objects.count() == 10
        td = league.team_dict
        assert td['WAS'] == td['WSH']

        tm = sports.Team.objects.get(league=league, nickname='Jaguars')
        aliases = list(tm.aliases.all())
        assert str(aliases[0]) == 'JAX'
        assert ['JAX'] == [a.name for a in aliases]

        assert tm.season_points() == 0
        assert tm.complete_record() == [[0, 0, 0], [0, 0, 0], [0, 0, 0]]
