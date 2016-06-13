# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('harvest', '0009_auto_20160219_1402'),
    ]

    operations = [
        migrations.AlterField(
            model_name='job',
            name='publish',
            field=models.ForeignKey(on_delete=django.db.models.deletion.SET_NULL, editable=False, to='tablemanager.Publish', null=True),
            preserve_default=True,
        ),
    ]
