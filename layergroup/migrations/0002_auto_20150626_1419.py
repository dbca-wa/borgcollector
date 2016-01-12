# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('layergroup', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='layergroup',
            name='srs',
            field=models.CharField(max_length=320, choices=[(b'EPSG:4283', b'EPSG:4283'), (b'EPSG:4326', b'EPSG:4326')]),
            preserve_default=True,
        ),
    ]
