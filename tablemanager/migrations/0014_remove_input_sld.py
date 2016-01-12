# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('tablemanager', '0013_auto_20151109_1555'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='input',
            name='sld',
        ),
    ]
