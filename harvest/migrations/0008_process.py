# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('harvest', '0007_auto_20160111_1343'),
    ]

    operations = [
        migrations.CreateModel(
            name='Process',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(max_length=32, editable=False)),
                ('desc', models.CharField(max_length=256, editable=False)),
                ('server', models.CharField(max_length=64, editable=False)),
                ('pid', models.IntegerField(max_length=64, editable=False)),
                ('status', models.CharField(max_length=32, editable=False)),
                ('last_message', models.TextField(null=True, editable=False)),
                ('last_starttime', models.DateTimeField(null=True, editable=False)),
                ('last_endtime', models.DateTimeField(null=True, editable=False)),
                ('next_scheduled_time', models.DateTimeField(editable=False)),
            ],
            options={
            },
            bases=(models.Model,),
        ),
    ]
