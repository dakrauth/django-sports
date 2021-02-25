import random
import itertools
from datetime import timedelta
from collections import ChainMap

from django.db import models
from django.urls import reverse
from django.conf import settings
from django.dispatch import Signal
from django.db import OperationalError
from django.utils.functional import cached_property
from django.utils import timezone
from django.core.exceptions import ValidationError

from dateutil.parser import parse as parse_dt
from choice_enum import ChoiceEnumeration

from .exceptions import PickerResultException
from . import managers
from . import utils
from . import importers
from .utils import temporary_slug

LOGOS_DIR = getattr(settings, 'DJANGO_SPORTS', {}).get('logos_upload_dir', 'sports/logos')


class League(models.Model):
    name = models.CharField(max_length=50, unique=True)
    abbr = models.CharField(max_length=8)
    logo = models.ImageField(upload_to=LOGOS_DIR, blank=True, null=True)
    current_season = models.IntegerField(blank=True, null=True)
    slug = models.SlugField(default=temporary_slug)
    avg_game_duration = models.PositiveIntegerField(default=240)

    objects = managers.LeagueManager()

    class Meta:
        permissions = (("can_update_score", "Can update scores"),)

    def __str__(self):
        return self.name

    def _reverse(self, name):
        return reverse(name, args=[self.slug])

    def get_absolute_url(self):
        return self._reverse('sports:home')

    def teams_url(self):
        return self._reverse('sports:teams')

    def schedule_url(self):
        return self._reverse('sports:schedule')

    def to_dict(self):
        return {
            'schema': 'complete',
            'league': {
                'schema': 'league',
                'name': self.name,
                'slug': self.slug,
                'abbr': self.abbr,
                'current_season': self.current_season,
                'teams': [team.to_dict() for team in self.teams.all()]
            },
            'season': {
                'schema': 'season',
                'league': self.abbr,
                'season': self.current_season,
                'gamesets': [
                    gs.to_dict()
                    for gs in self.gamesets.filter(season=self.current_season)
                ]
            }
        }

    @cached_property
    def team_dict(self):
        names = {}
        for team in self.teams.all():
            names[team.abbr] = team
            names[team.id] = team
            if team.nickname:
                full_name = '{} {}'.format(team.name, team.nickname)
                names[full_name] = team

            for alias in Alias.objects.filter(team=team).values_list('name', flat=True):
                names[alias] = team

        return names

    @property
    def latest_gameset(self):
        rel = timezone.now()
        try:
            return self.gamesets.filter(points=0, opens__gte=rel).earliest('opens')
        except GameSet.DoesNotExist:
            pass

        try:
            return self.gamesets.filter(closes__lte=rel).latest('closes')
        except GameSet.DoesNotExist:
            return None

    @property
    def latest_season(self):
        gs = self.latest_gameset
        return gs.season if gs else None

    @cached_property
    def current_gamesets(self):
        rel = timezone.now()
        try:
            return self.gamesets.filter(opens__lte=rel, closes__gte=rel)
        except GameSet.DoesNotExist:
            return []

    @cached_property
    def available_seasons(self):
        return self.gamesets.order_by('-season').values_list(
            'season',
            flat=True
        ).distinct()

    def season_gamesets(self, season=None):
        season = season or self.current_season or self.latest_season
        return self.gamesets.filter(season=season)

    @classmethod
    def import_season(cls, data):
        return importers.import_season(cls, data)

    @classmethod
    def import_league(cls, data):
        return importers.import_league(cls, data)


class Conference(models.Model):
    name = models.CharField(max_length=50)
    short_name = models.CharField(max_length=15, blank=True)
    abbr = models.CharField(max_length=8, db_index=True)
    league = models.ForeignKey(League, on_delete=models.CASCADE, related_name='conferences')

    def __str__(self):
        return self.name


class Division(models.Model):
    name = models.CharField(max_length=50)
    short_name = models.CharField(max_length=15, blank=True)
    conference = models.ForeignKey(Conference, on_delete=models.CASCADE, related_name='divisions')

    def __str__(self):
        return '{} ({})'.format(self.name, self.conference.name)


def valid_team_abbr(value):
    if value.startswith('__'):
        raise ValidationError('Team abbr cannot start with "__"')


class Team(models.Model):
    '''
    Common team attributes.
    '''

    name = models.CharField(max_length=50)
    abbr = models.CharField(max_length=8, blank=True, validators=[valid_team_abbr])
    nickname = models.CharField(max_length=50, blank=True)
    location = models.CharField(max_length=100, blank=True)
    coach = models.CharField(max_length=50, blank=True)
    league = models.ForeignKey(League, on_delete=models.CASCADE, related_name='teams')
    conference = models.ForeignKey(
        Conference,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='teams'
    )
    division = models.ForeignKey(
        Division,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='teams'
    )
    colors = models.CharField(max_length=40, blank=True)
    logo = models.ImageField(upload_to=LOGOS_DIR, blank=True, null=True)
    notes = models.TextField(blank=True, default='')

    class Meta:
        ordering = ('name',)

    def __str__(self):
        return '{} {}'.format(self.name, self.nickname)

    def get_absolute_url(self):
        return reverse('sports-team', args=[self.league.slug, self.abbr])

    def to_dict(self):
        return {
            'abbr': self.abbr,
            'logo': self.logo.name,
            'name': self.name,
            'nickname': self.nickname,
            'sub': [
                self.conference.name,
                self.division.name
            ],
            'aliases': list(self.aliases.values_list('name', flat=True)),
            'coach': self.coach,
            'location': self.location,
        }

    def season_record(self, season=None):
        season = season or self.league.current_season
        wins, losses, ties = (0, 0, 0)
        for status, home_abbr, away_abbr in Game.objects.filter(
            models.Q(home=self) | models.Q(away=self),
            gameset__season=season,
        ).exclude(
            status__in=[Game.Status.UNPLAYED, Game.Status.CANCELLED]
        ).values_list('status', 'home__abbr', 'away__abbr'):
            if status == Game.Status.TIE:
                ties += 1
            else:
                if (
                    (status == Game.Status.HOME_WIN and self.abbr == home_abbr) or
                    (status == Game.Status.AWAY_WIN and self.abbr == away_abbr)
                ):
                    wins += 1
                else:
                    losses += 1

        return (wins, losses, ties)

    def season_points(self, season=None):
        season = season or self.league.current_season
        w, l, t = self.season_record(season)
        return w * 2 + t

    @property
    def record(self):
        return self.season_record(self.league.current_season)

    @property
    def record_as_string(self):
        record = self.record
        if not record[2]:
            record = record[:2]
        return '-'.join(str(s) for s in record)

    @property
    def color_options(self):
        return self.colors.split(',') if self.colors else []

    def schedule(self, season=None):
        return Game.objects.select_related('gameset').filter(
            models.Q(away=self) | models.Q(home=self),
            gameset__season=season or self.league.current_season
        )

    def byes(self, season=None):
        return self.bye_set.filter(season=season or self.league.current_season)

    def complete_record(self):
        home_games = [0, 0, 0]
        away_games = [0, 0, 0]

        for games, accum, status in (
            (self.away_games, away_games, Game.Status.AWAY_WIN),
            (self.home_games, home_games, Game.Status.HOME_WIN),
        ):
            for res in games.exclude(status=Game.Status.UNPLAYED).values_list(
                'status',
                flat=True
            ):
                if res == status:
                    accum[0] += 1
                elif res == Game.Status.TIE:
                    accum[2] += 1
                else:
                    accum[1] += 1

        return [home_games, away_games, [
            away_games[0] + home_games[0],
            away_games[1] + home_games[1],
            away_games[2] + home_games[2]
        ]]


class Alias(models.Model):
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='aliases')
    name = models.CharField(max_length=50)

    def __str__(self):
        return self.name


class GameSet(models.Model):
    league = models.ForeignKey(League, on_delete=models.CASCADE, related_name='gamesets')
    season = models.PositiveSmallIntegerField()
    sequence = models.PositiveSmallIntegerField()
    points = models.PositiveSmallIntegerField(default=0)
    opens = models.DateTimeField()
    closes = models.DateTimeField()
    description = models.CharField(max_length=60, default='', blank=True)
    byes = models.ManyToManyField(
        Team,
        blank=True,
        verbose_name='Bye Teams',
        related_name='bye_set'
    )

    class Meta:
        ordering = ('season', 'sequence')

    def __str__(self):
        return '{}:{}'.format(self.sequence, self.season)

    def get_absolute_url(self):
        return reverse(
            'sports-game-sequence',
            args=[self.league.slug, str(self.season), str(self.sequence)]
        )

    def to_dict(self):
        return {
            'byes': list(self.byes.values_list('abbr', flat=True)),
            'opens': self.opens.isoformat(),
            'closes': self.closes.isoformat(),
            'games': [
                g.to_dict() for g in self.games.select_related('home', 'away')
            ]
        }

    def import_games(self, data, teams=None):
        teams = teams or self.league.team_dict
        byes = data.get('byes')
        if byes:
            self.byes.add(*[teams[t] for t in byes])

        games = []
        for dct in data['games']:
            start_time = parse_dt(dct['start'])
            game, is_new = self.games.get_or_create(
                home=teams.get(dct['home']),
                away=teams.get(dct['away']),
                defaults={'start_time': start_time}
            )
            game.start_time = start_time
            game.description = dct.get('description', game.description)
            game.tv = dct.get('tv', game.tv)
            game.location = dct.get('location', game.location)
            game.notes = dct.get('notes', game.notes)
            game.save()
            games.append([game, is_new])

        return games

    @property
    def last_game(self):
        return self.games.last()

    @property
    def first_game(self):
        return self.games.first()

    @cached_property
    def start_time(self):
        return self.first_game.start_time

    @property
    def end_time(self):
        return self.last_game.end_time

    @property
    def in_progress(self):
        return self.end_time >= timezone.now() >= self.start_time

    @property
    def has_started(self):
        return timezone.now() >= self.start_time

    @property
    def is_open(self):
        return timezone.now() < self.last_game.start_time

    def pick_for_user(self, user):
        try:
            return self.picksets.select_related().get(user=user)
        except PickSet.DoesNotExist:
            return None

    def reset_games_status(self):
        UNPLAYED = Game.Status.UNPLAYED
        self.games.exclude(status=UNPLAYED).update(status=UNPLAYED)

    def update_results(self, results):
        '''
        results schema: {'sequence': 1, 'season': 2018, 'games': [{
            "home": "HOME",
            "away": "AWAY",
            "home_score": 15,
            "away_score": 10,
            "status": "Final",
            "winner": "HOME",
        }]}
        '''

        if not results:
            raise PickerResultException('Results unavailable')

        if results['sequence'] != self.sequence or results['season'] != self.season:
            raise PickerResultException('Results not updated, wrong season or week')

        completed = {g['home']: g for g in results['games'] if g['status'].startswith('F')}
        if not completed:
            return (0, None)

        count = 0
        for game in self.games.incomplete(home__abbr__in=completed.keys()):
            result = completed.get(game.home.abbr, None)
            if result:
                winner = result['winner']
                game.winner = (
                    game.home if game.home.abbr == winner
                    else game.away if game.away.abbr == winner else None
                )
                count += 1

        last_game = self.last_game
        if not self.points and last_game.winner:
            now = timezone.now()
            if now > last_game.end_time:
                result = completed.get(last_game.home.abbr, None)
                if result:
                    self.points = result['home_score'] + result['away_score']
                    self.save()

        if count:
            self.update_pick_status()

        return (count, self.points)

    def winners(self):
        if self.points:
            yield from itertools.takewhile(lambda i: i.place == 1, self.results())

    def update_pick_status(self):
        winners = set(w.id for w in self.winners())
        for wp in self.picksets.all():
            wp.update_status(wp.id in winners)

    def results(self):
        picks = list(self.picksets.select_related())
        return utils.sorted_standings(picks, key=PickSet.sort_key, reverse=True)


class Game(models.Model):

    class Category(ChoiceEnumeration):
        REGULAR = ChoiceEnumeration.Option('REG', 'Regular Season', default=True)
        POST = ChoiceEnumeration.Option('POST', 'Post Season')
        PRE = ChoiceEnumeration.Option('PRE', 'Pre Season')
        FRIENDLY = ChoiceEnumeration.Option('FRND', 'Friendly')

    class Status(ChoiceEnumeration):
        UNPLAYED = ChoiceEnumeration.Option('U', 'Unplayed', default=True)
        TIE = ChoiceEnumeration.Option('T', 'Tie')
        HOME_WIN = ChoiceEnumeration.Option('H', 'Home Win')
        AWAY_WIN = ChoiceEnumeration.Option('A', 'Away Win')
        CANCELLED = ChoiceEnumeration.Option('X', 'Cancelled')

    home = models.ForeignKey(
        Team,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='home_games'
    )
    away = models.ForeignKey(
        Team,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='away_games'
    )
    gameset = models.ForeignKey(GameSet, on_delete=models.CASCADE, related_name='games')
    start_time = models.DateTimeField()
    tv = models.CharField('TV', max_length=8, blank=True)
    notes = models.TextField(blank=True)
    category = models.CharField(max_length=4, choices=Category.CHOICES, default=Category.DEFAULT)
    status = models.CharField(max_length=1, choices=Status.CHOICES, default=Status.DEFAULT)
    location = models.CharField(blank=True, default='', max_length=60)
    description = models.CharField(max_length=60, default='', blank=True)

    objects = managers.GameManager()

    class Meta:
        ordering = ('start_time', 'away')

    def __str__(self):
        return '{} @ {} {}'.format(self.away.abbr, self.home.abbr, self.gameset)

    def to_dict(self):
        return {
            'away': self.away.abbr,
            'home': self.home.abbr,
            'start': self.start_time.isoformat(),
            'tv': self.tv,
            'location': self.location
        }

    @property
    def is_tie(self):
        return self.status == self.Status.TIE

    @property
    def has_started(self):
        return timezone.now() >= self.start_time

    @property
    def short_description(self):
        return '%s @ %s' % (self.away, self.home)

    @property
    def vs_description(self):
        return '%s vs %s' % (self.away.nickname, self.home.nickname)

    @property
    def is_home_win(self):
        return self.status == self.Status.HOME_WIN

    @property
    def is_away_win(self):
        return self.status == self.Status.AWAY_WIN

    @property
    def winner(self):
        if self.status == self.Status.HOME_WIN:
            return self.home

        if self.status == self.Status.AWAY_WIN:
            return self.away

        return None

    @winner.setter
    def winner(self, team):
        if team is None:
            self.status = self.Status.TIE
        elif team == self.away:
            self.status = self.Status.AWAY_WIN
        elif team == self.home:
            self.status = self.Status.HOME_WIN
        else:
            return

        self.save()

    def get_random_winner(self):
        return random.choice((self.home, self.away))

    @property
    def end_time(self):
        return self.start_time + timedelta(minutes=self.gameset.league.avg_game_duration)

    @property
    def in_progress(self):
        now = timezone.now()
        return self.end_time >= now >= self.start_time
