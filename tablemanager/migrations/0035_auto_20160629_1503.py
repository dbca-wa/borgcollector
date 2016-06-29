# -*- coding: utf-8 -*-
# Generated by Django 1.9.7 on 2016-06-29 07:03
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('tablemanager', '0034_auto_20160629_1432'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='replica',
            name='includes',
        ),
        migrations.AlterUniqueTogether(
            name='style',
            unique_together=set([]),
        ),
        migrations.RemoveField(
            model_name='style',
            name='publish',
        ),
        migrations.DeleteModel(
            name='Replica',
        ),
        migrations.DeleteModel(
            name='Style',
        ),
    ]
