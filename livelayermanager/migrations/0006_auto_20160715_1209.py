# -*- coding: utf-8 -*-
# Generated by Django 1.9.7 on 2016-07-15 04:09
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('livelayermanager', '0005_auto_20160628_1456'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='layer',
            name='abstract',
        ),
        migrations.RemoveField(
            model_name='layer',
            name='title',
        ),
    ]
