# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('harvest', '0002_auto_20150505_1136'),
    ]

    operations = [
        migrations.CreateModel(
            name='ActiveJob',
            fields=[
            ],
            options={
                'proxy': True,
            },
            bases=('harvest.job',),
        ),
        migrations.CreateModel(
            name='FailJob',
            fields=[
            ],
            options={
                'proxy': True,
            },
            bases=('harvest.job',),
        ),
    ]
