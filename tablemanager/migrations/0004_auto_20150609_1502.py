# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import re
import django.core.validators
import tablemanager.models


class Migration(migrations.Migration):

    dependencies = [
        ('tablemanager', '0003_publish_geoserver_setting'),
    ]

    operations = [
        migrations.CreateModel(
            name='Application',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(db_index=True, max_length=255, validators=[django.core.validators.RegexValidator(re.compile('^[a-z0-9_]+$'), 'Slug can only contain lowercase letters, numbers and underscores', 'invalid')])),
                ('description', models.TextField(blank=True)),
            ],
            options={
            },
            bases=(models.Model, tablemanager.models.SignalEnable),
        ),
        migrations.AddField(
            model_name='publish',
            name='applications',
            field=models.ManyToManyField(help_text='The applications which can list this layer.', to='tablemanager.Application', blank=True),
            preserve_default=True,
        ),
    ]
