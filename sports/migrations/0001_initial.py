# Generated by Django 2.2.6 on 2019-10-27 18:00

from django.db import migrations, models
import django.db.models.deletion
import sports.models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Conference',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=50)),
                ('abbr', models.CharField(db_index=True, max_length=8)),
            ],
        ),
        migrations.CreateModel(
            name='Division',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=50)),
                ('conference', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='divisions', to='sports.Conference')),
            ],
        ),
        migrations.CreateModel(
            name='League',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=50, unique=True)),
                ('abbr', models.CharField(db_index=True, max_length=8, unique=True)),
                ('logo', models.ImageField(blank=True, null=True, upload_to='sports/logos')),
                ('current_season', models.IntegerField(blank=True, null=True)),
                ('slug', models.SlugField(default=sports.models.temp_slug)),
                ('avg_game_duration', models.PositiveIntegerField(default=240)),
            ],
        ),
        migrations.CreateModel(
            name='Team',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=50)),
                ('abbr', models.CharField(blank=True, max_length=8, validators=[sports.models.valid_team_abbr])),
                ('nickname', models.CharField(blank=True, max_length=50)),
                ('location', models.CharField(blank=True, max_length=100)),
                ('coach', models.CharField(blank=True, max_length=50)),
                ('colors', models.CharField(blank=True, max_length=40, validators=[sports.models.valid_team_colors])),
                ('logo', models.ImageField(blank=True, null=True, upload_to='sports/logos')),
                ('notes', models.TextField(blank=True, default='')),
                ('conference', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='teams', to='sports.Conference')),
                ('division', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='teams', to='sports.Division')),
                ('league', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='teams', to='sports.League')),
            ],
            options={
                'ordering': ('name',),
            },
        ),
        migrations.CreateModel(
            name='GameSet',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('season', models.PositiveSmallIntegerField(db_index=True)),
                ('sequence', models.PositiveSmallIntegerField()),
                ('opens', models.DateTimeField()),
                ('closes', models.DateTimeField()),
                ('description', models.CharField(blank=True, default='', max_length=60)),
                ('byes', models.ManyToManyField(blank=True, related_name='bye_set', to='sports.Team', verbose_name='Bye Teams')),
                ('league', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='gamesets', to='sports.League')),
            ],
            options={
                'ordering': ('season', 'sequence'),
            },
        ),
        migrations.CreateModel(
            name='Game',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('home_score', models.IntegerField(blank=True, null=True)),
                ('away_score', models.IntegerField(blank=True, null=True)),
                ('start_time', models.DateTimeField()),
                ('tv', models.CharField(blank=True, max_length=8, verbose_name='TV')),
                ('notes', models.TextField(blank=True)),
                ('category', models.CharField(choices=[('REG', 'Regular Season'), ('POST', 'Post Season'), ('PRE', 'Pre Season'), ('FRND', 'Friendly')], db_index=True, default='REG', max_length=4)),
                ('status', models.CharField(choices=[('U', 'Unplayed'), ('T', 'Tie'), ('H', 'Home Win'), ('A', 'Away Win'), ('X', 'Cancelled')], db_index=True, default='U', max_length=1)),
                ('location', models.CharField(blank=True, default='', max_length=60)),
                ('description', models.CharField(blank=True, default='', max_length=60)),
                ('away', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='away_games', to='sports.Team')),
                ('gameset', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='games', to='sports.GameSet')),
                ('home', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='home_games', to='sports.Team')),
            ],
            options={
                'ordering': ('start_time', 'away'),
            },
        ),
        migrations.AddField(
            model_name='conference',
            name='league',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='conferences', to='sports.League'),
        ),
        migrations.CreateModel(
            name='Alias',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=50)),
                ('team', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='aliases', to='sports.Team')),
            ],
        ),
    ]
