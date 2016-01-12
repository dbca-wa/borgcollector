# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('tablemanager', '0002_auto_20150501_1518'),
    ]

    operations = [
        migrations.AddField(
            model_name='publish',
            name='geoserver_setting',
            field=models.TextField(null=True, editable=False, blank=True),
            preserve_default=True,
        ),
    ]
