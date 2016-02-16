# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('layergroup', '0003_auto_20151124_1425'),
    ]

    operations = [
        migrations.AlterField(
            model_name='layergroup',
            name='status',
            field=models.CharField(max_length=32, editable=False, choices=[(b'New', b'New'), (b'Updated', b'Updated'), (b'Published', b'Published'), (b'CascadePublished', b'CascadePublished'), (b'CascadePublished', b'CascadePublished'), (b'Unpublished', b'Unpublished'), (b'CascadeUnpublished', b'CascadeUnpublished')]),
            preserve_default=True,
        ),
    ]
