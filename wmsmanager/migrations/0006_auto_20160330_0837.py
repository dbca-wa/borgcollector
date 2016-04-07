# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('wmsmanager', '0005_auto_20160217_1637'),
    ]

    operations = [
        migrations.AddField(
            model_name='wmslayer',
            name='bbox',
            field=models.CharField(max_length=128, null=True, editable=False),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='wmslayer',
            name='crs',
            field=models.CharField(max_length=64, null=True, editable=False),
            preserve_default=True,
        ),
    ]
