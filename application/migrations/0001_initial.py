# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import re
import django.core.validators
import borg_utils.signal_enable


class Migration(migrations.Migration):

    dependencies = [
        ('tablemanager', '0007_auto_20150610_1156'),
        ('wmsmanager', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Application',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(db_index=True, max_length=255, validators=[django.core.validators.RegexValidator(re.compile(b'^[a-z0-9_]+$'), b'Slug can only contain lowercase letters, numbers and underscores', b'invalid')])),
                ('description', models.TextField(blank=True)),
            ],
            options={
            },
            bases=(models.Model, borg_utils.signal_enable.SignalEnable),
        ),
        migrations.CreateModel(
            name='Application_Layers',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('order', models.PositiveIntegerField()),
                ('application', models.ForeignKey(to='application.Application')),
                ('publish', models.ForeignKey(blank=True, to='tablemanager.Publish', null=True)),
                ('wmslayer', models.ForeignKey(blank=True, to='wmsmanager.WmsLayer', null=True)),
            ],
            options={
                'verbose_name': "Application's Layer",
            },
            bases=(models.Model, borg_utils.signal_enable.SignalEnable),
        ),
        migrations.AlterUniqueTogether(
            name='application_layers',
            unique_together=set([('application', 'publish', 'wmslayer'), ('application', 'order')]),
        ),
    ]
