# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('tablemanager', '0019_auto_20160120_1314'),
    ]

    operations = [
        migrations.AddField(
            model_name='workspace',
            name='auth_level',
            field=models.PositiveSmallIntegerField(default=1, choices=[(0, 'Public access'), (1, 'SSO access'), (2, 'SSO restricted role access')]),
            preserve_default=True,
        ),
        migrations.RemoveField(
            model_name='workspace',
            name='allow_authenticated',
        ),
    ]
