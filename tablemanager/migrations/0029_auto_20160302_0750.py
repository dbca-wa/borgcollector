# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import tablemanager.models


class Migration(migrations.Migration):

    dependencies = [
        ('tablemanager', '0028_auto_20160301_1421'),
    ]

    operations = [
        migrations.AlterField(
            model_name='datasource',
            name='sql',
            field=tablemanager.models.SQLField(null=True, blank=True),
            preserve_default=True,
        ),
    ]
