# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('tablemanager', '0009_auto_20150818_1614'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='normaltable',
            name='priority',
        ),
        migrations.AddField(
            model_name='publish',
            name='pending_actions',
            field=models.IntegerField(null=True, editable=False, blank=True),
            preserve_default=True,
        ),
    ]
