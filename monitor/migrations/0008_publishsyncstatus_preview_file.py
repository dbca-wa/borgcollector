# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import monitor.models


class Migration(migrations.Migration):

    dependencies = [
        ('monitor', '0007_slaveserver_code_version'),
    ]

    operations = [
        migrations.AddField(
            model_name='publishsyncstatus',
            name='preview_file',
            field=models.FileField(storage=monitor.models.PreviewFileSystemStorage(), upload_to=monitor.models.get_preview_file_name, null=True, editable=False),
            preserve_default=True,
        ),
    ]
