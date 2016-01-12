# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import tablemanager.models


class Migration(migrations.Migration):

    dependencies = [
        ('tablemanager', '0016_input_advanced_options'),
    ]

    operations = [
        migrations.AlterField(
            model_name='input',
            name='advanced_options',
            field=models.CharField(help_text='Advanced ogr2ogr options', max_length=128, null=True, editable=False, blank=True),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='input',
            name='generate_rowid',
            field=models.BooleanField(default=False, help_text="If true, a _rowid column will be added and filled with row data's hash value"),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='input',
            name='source',
            field=tablemanager.models.DatasourceField(default='<OGRVRTDataSource>\n    <OGRVRTLayer name="tablename">\n        <SrcDataSource>PG:dbname=databasename host=\'addr\' port=\'5432\' user=\'x\' password=\'y\'</SrcDataSource>\n    </OGRVRTLayer>\n</OGRVRTDataSource>', help_text='GDAL VRT definition in xml', unique=True),
            preserve_default=True,
        ),
    ]
