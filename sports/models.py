import re
import random
from datetime import timedelta, datetime
from collections import OrderedDict

from django.db import models
from django.urls import reverse
from django.conf import settings
from django.utils import timezone
from django.utils.functional import cached_property
from django.core.exceptions import ValidationError

from dateutil.parser import parse as parse_dt
from choice_enum import ChoiceEnumeration

from . import importers


SPORTS_CONFIG = getattr(settings, 'SPORTS_CONFIG', {})
LOGOS_DIR = SPORTS_CONFIG.get('logos_upload_dir', 'sports/logos')


def temp_slug():
    return '{:010.0f}'.format(random.random() * 10000000000)


class League(models.Model):
    name = models.CharField(max_length=50, unique=True)
    abbr = models.CharField(max_length=8, unique=True, db_index=True)
    logo = models.ImageField(upload_to=LOGOS_DIR, blank=True, null=True)
    current_season = models.IntegerField(blank=True, null=True)
    slug = models.SlugField(default=temp_slug)
    avg_game_duration = models.PositiveIntegerField(default=240)

    def __str__(self):
        return self.name

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
            return self.gamesets.filter(opens__gte=rel).earliest('opens')
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
    def current_gameset(self):
        rel = timezone.now()
        try:
            return self.gamesets.get(opens__lte=rel, closes__gte=rel)
        except GameSet.DoesNotExist:
            return None

    @cached_property
    def available_seasons(self):
        return list(self.gamesets.order_by('-season').values_list(
            'season',
            flat=True
        ).distinct())

    def season_gamesets(self, season=None):
        season = season or self.current_season or self.latest_season
        return self.gamesets.filter(season=season)

    @classmethod
    def import_season(cls, data):
        return importers.import_season(cls, data)

    @classmethod
    def import_league(cls, data):
        return importers.import_league(cls, data)

    @classmethod
    def get(cls, abbr):
        return cls.objects.get(abbr__iexact=abbr)


class Conference(models.Model):
    name = models.CharField(max_length=50)
    abbr = models.CharField(max_length=8, db_index=True)
    league = models.ForeignKey(League, on_delete=models.CASCADE, related_name='conferences')

    def __str__(self):
        return self.name


class Division(models.Model):
    name = models.CharField(max_length=50)
    conference = models.ForeignKey(Conference, on_delete=models.CASCADE, related_name='divisions')

    def __str__(self):
        return '{} {}'.format(self.conference, self.name)


def valid_team_abbr(value):
    if value.startswith('__'):
        raise ValidationError('Team abbr cannot start with "__"')


def valid_team_colors(value):
    clr = r'#?[0-9a-f]{3}([0-9a-f]{3})?'
    if value and not re.fullmatch(r'{}(,{})*'.format(clr, clr), value):
        raise ValidationError('Team colors must be comma-separated hexidecimal values')


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
    colors = models.CharField(max_length=40, blank=True, validators=[valid_team_colors])
    logo = models.ImageField(upload_to=LOGOS_DIR, blank=True, null=True)
    notes = models.TextField(blank=True, default='')

    class Meta:
        ordering = ('name',)

    def __str__(self):
        return '{} {}'.format(self.name, self.nickname)

    def to_dict(self):
        return {
            'abbr': self.abbr,
            'logo': self.logo.name,
            'name': self.name,
            'nickname': self.nickname,
            'sub': [sub.name for sub in [self.conference, self.division] if sub],
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

        return [wins, losses, ties]

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
    season = models.PositiveSmallIntegerField(db_index=True)
    sequence = models.PositiveSmallIntegerField()
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

    def reset_games_status(self):
        UNPLAYED = Game.Status.UNPLAYED
        self.games.exclude(status=UNPLAYED).update(
            status=UNPLAYED,
            home_score=None,
            away_score=None
        )

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
            raise ValueError('Results unavailable')

        if results['sequence'] != self.sequence or results['season'] != self.season:
            raise ValueError('Results not updated, wrong season or week')

        completed = {g['home']: g for g in results['games'] if g['status'].startswith('F')}
        if not completed:
            return 0

        count = 0
        for game in self.games.incomplete(home__abbr__in=completed.keys()):
            result = completed.get(game.home.abbr, None)
            if result:
                game.set_scores(result['away_score'], result['home_score'])
                count += 1

        return count


class GameManager(models.Manager):

    def display_results(self):
        return OrderedDict([
            (item['id'], item) for item in self.games_started().annotate(
                winner=models.Case(
                    models.When(status='H', then='home__abbr'),
                    models.When(status='A', then='away__abbr'),
                    models.When(status='T', then=models.Value('__TIE__')),
                    default=None,
                    output_field=models.CharField()
                )
            ).values('id', 'home__abbr', 'home_score', 'away__abbr', 'away_score', 'winner')
        ])

    def games_started(self):
        return self.filter(start_time__lte=datetime.now())

    def incomplete(self, **kws):
        kws['status'] = self.model.Status.UNPLAYED
        return self.filter(**kws)

    def played(self, **kws):
        Status = self.model.Status
        kws['status__in'] = [Status.TIE, Status.HOME_WIN, Status.AWAY_WIN]
        return self.filter(**kws)


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

    home_score = models.IntegerField(blank=True, null=True)
    away_score = models.IntegerField(blank=True, null=True)

    gameset = models.ForeignKey(GameSet, on_delete=models.CASCADE, related_name='games')
    start_time = models.DateTimeField()
    tv = models.CharField('TV', max_length=8, blank=True)
    notes = models.TextField(blank=True)
    category = models.CharField(
        max_length=4,
        choices=Category.CHOICES,
        default=Category.DEFAULT,
        db_index=True,
    )
    status = models.CharField(
        max_length=1,
        choices=Status.CHOICES,
        default=Status.DEFAULT,
        db_index=True,
    )
    location = models.CharField(blank=True, default='', max_length=60)
    description = models.CharField(max_length=60, default='', blank=True)

    objects = GameManager()

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
    def score(self):
        return (self.away_score, self.home_score)

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

    def set_scores(self, away_score, home_score):
        self.away_score = away_score
        self.home_score = home_score

        if away_score == home_score:
            self.status = self.Status.TIE
        elif away_score > home_score:
            self.status = self.Status.AWAY_WIN
        else:
            self.status = self.Status.HOME_WIN

        self.save()

    @property
    def end_time(self):
        return self.start_time + timedelta(minutes=self.gameset.league.avg_game_duration)

    @property
    def in_progress(self):
        now = timezone.now()
        return self.end_time >= now >= self.start_time
