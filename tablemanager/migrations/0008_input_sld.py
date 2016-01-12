# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import tablemanager.models


class Migration(migrations.Migration):

    dependencies = [
        ('tablemanager', '0007_auto_20150610_1156'),
    ]

    operations = [
        migrations.AddField(
            model_name='input',
            name='sld',
            field=tablemanager.models.XMLField(help_text='Styled Layer Descriptor', null=True, blank=True),
            preserve_default=True,
        ),
    ]
