# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('tablemanager', '0022_remove_publish_sld'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='publish',
            name='pgdump_file',
        ),
        migrations.RemoveField(
            model_name='publish',
            name='style_file',
        ),
    ]
