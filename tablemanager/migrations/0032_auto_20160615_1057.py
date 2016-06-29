# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('tablemanager', '0031_auto_20160613_1522'),
    ]

    operations = [
        migrations.AlterField(
            model_name='publish',
            name='default_style',
            field=models.ForeignKey(related_name='+', on_delete=django.db.models.deletion.SET_NULL, blank=True, to='tablemanager.Style', null=True),
            preserve_default=True,
        ),
    ]
