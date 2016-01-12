# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('application', '0002_auto_20150911_1218'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='application_layers',
            unique_together=set([('application', 'wmslayer'), ('application', 'publish')]),
        ),
    ]
