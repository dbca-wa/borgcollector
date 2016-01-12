# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('tablemanager', '0006_publish_applications'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='publish',
            options={'ordering': ['workspace', 'name']},
        ),
    ]
