# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import tablemanager.models


class Migration(migrations.Migration):

    dependencies = [
        ('tablemanager', '0026_auto_20160229_0844'),
    ]

    operations = [
        migrations.AddField(
            model_name='datasource',
            name='vrt',
            field=tablemanager.models.XMLField(default='', help_text='GDAL VRT template in xml'),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='foreigntable',
            name='server',
            field=models.ForeignKey(to='tablemanager.DataSource'),
            preserve_default=True,
        ),
        migrations.DeleteModel(
            name='ForeignServer',
        ),
        migrations.AlterField(
            model_name='input',
            name='source',
            field=tablemanager.models.DatasourceField(default='<OGRVRTDataSource>\n    <OGRVRTLayer name="{{self.foreign_table.name}}">\n        <SrcDataSource>PG:dbname={{db.NAME}} host=\'{{db.HOST}}\' port=\'{{db.PORT}}\' user=\'{{db.USER}}\' password=\'{{db.PASSWORD}}\'</SrcDataSource>\n    </OGRVRTLayer>\n</OGRVRTDataSource>\n', help_text='GDAL VRT definition in xml', unique=True),
            preserve_default=True,
        ),
    ]
