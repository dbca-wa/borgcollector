# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('layergroup', '0004_auto_20160216_0804'),
    ]

    operations = [
        migrations.AlterField(
            model_name='layergrouplayers',
            name='group',
            field=models.ForeignKey(related_name='group_layer', to='layergroup.LayerGroup'),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='layergrouplayers',
            name='sub_group',
            field=models.ForeignKey(related_name='subgroup_layer', blank=True, editable=False, to='layergroup.LayerGroup', null=True),
            preserve_default=True,
        ),
    ]
