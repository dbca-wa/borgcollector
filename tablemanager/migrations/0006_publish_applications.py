# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('tablemanager', '0005_auto_20150610_0842'),
    ]

    operations = [
        migrations.AddField(
            model_name='publish',
            name='applications',
            field=models.TextField(null=True, editable=False, blank=True),
            preserve_default=True,
        ),
    ]
