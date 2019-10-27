from django import forms
from django.contrib import admin
from . import models as sports


@admin.register(sports.League)
class LeagueAdmin(admin.ModelAdmin):
    list_display = ('name', 'abbr', 'slug', 'current_season')


class AliasInline(admin.TabularInline):
    model = sports.Alias


@admin.register(sports.Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ('name', 'abbr', 'nickname', 'league', 'conference', 'division')
    list_filter = ('league',)
    inlines = [AliasInline]


@admin.register(sports.Conference)
class ConferenceAdmin(admin.ModelAdmin):
    list_display = ('name', 'abbr', 'league')
    list_filter = ('league',)


@admin.register(sports.Division)
class DivisionAdmin(admin.ModelAdmin):
    list_display = ('name', 'conference', 'league')
    list_filter = ('conference', 'conference__league')

    def league(self, obj):
        return obj.conference.league


class GameSetForm(forms.ModelForm):

    class Meta:
        model = sports.GameSet
        fields = '__all__'

    def __init__(self, *args, **kws):
        super(GameSetForm, self).__init__(*args, **kws)
        if self.instance and self.instance.id:
            self.fields['byes'].queryset = self.instance.league.teams.all()


class InlineGameForm(forms.ModelForm):

    class Meta:
        model = sports.Game
        exclude = ('notes', )


class GameInline(admin.TabularInline):
    model = sports.Game
    form = InlineGameForm
    extra = 0


@admin.register(sports.GameSet)
class GameSetAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'league', 'opens', 'closes', 'games')
    list_filter = ('league', 'season',)
    ordering = ('-season', 'sequence')
    filter_horizontal = ['byes']
    inlines = [GameInline]
    form = GameSetForm

    def games(self, obj):
        return obj.games.count()
