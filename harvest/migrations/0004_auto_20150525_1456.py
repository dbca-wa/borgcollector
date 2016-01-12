# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('harvest', '0003_activejob_failjob'),
    ]

    operations = [
        migrations.DeleteModel(
            name='ActiveJob',
        ),
        migrations.DeleteModel(
            name='FailJob',
        ),
        migrations.CreateModel(
            name='EffectiveJob',
            fields=[
            ],
            options={
                'verbose_name': 'Job (Effective)',
                'proxy': True,
                'verbose_name_plural': 'Jobs (Effective)',
            },
            bases=('harvest.job',),
        ),
        migrations.CreateModel(
            name='FailingJob',
            fields=[
            ],
            options={
                'verbose_name': 'Job (Failing)',
                'proxy': True,
                'verbose_name_plural': 'Jobs (Failing)',
            },
            bases=('harvest.job',),
        ),
        migrations.CreateModel(
            name='RunningJob',
            fields=[
            ],
            options={
                'verbose_name': 'Job (Running)',
                'proxy': True,
                'verbose_name_plural': 'Jobs (Running)',
            },
            bases=('harvest.job',),
        ),
    ]
