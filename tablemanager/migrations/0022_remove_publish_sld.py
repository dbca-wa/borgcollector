# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('tablemanager', '0021_auto_20160219_0803'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='publish',
            name='sld',
        ),
    ]
