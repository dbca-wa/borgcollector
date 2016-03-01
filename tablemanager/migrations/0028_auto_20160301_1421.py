# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import tablemanager.models


class Migration(migrations.Migration):

    dependencies = [
        ('tablemanager', '0027_auto_20160301_1043'),
    ]

    operations = [
        migrations.AlterField(
            model_name='input',
            name='source',
            field=tablemanager.models.DatasourceField(help_text='GDAL VRT definition in xml', unique=True),
            preserve_default=True,
        ),
    ]
