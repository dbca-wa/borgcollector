# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import tablemanager.models


class Migration(migrations.Migration):

    dependencies = [
        ('tablemanager', '0010_auto_20150916_1107'),
    ]

    operations = [
        migrations.AlterField(
            model_name='foreigntable',
            name='sql',
            field=tablemanager.models.SQLField(default='CREATE FOREIGN TABLE "{{schema}}"."{{self.name}}" () SERVER {{self.server.name}} OPTIONS (schema \'<schema>\', table \'<table>\');'),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='normalise',
            name='sql',
            field=tablemanager.models.SQLField(default='CREATE FUNCTION "{{trans_schema}}"."{{self.func_name}}"() RETURNS SETOF "{{normal_schema}}"."{{self.output_table.name}}" as $$\nBEGIN\n    RETURN QUERY SELECT * FROM "{{input_schema}}"."{{self.input_table.name}}";\nEND;\n$$ LANGUAGE plpgsql;'),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='normaltable',
            name='create_sql',
            field=tablemanager.models.SQLField(default='CREATE TABLE "{{self.name}}" (name varchar(32) unique);'),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='publish',
            name='sql',
            field=tablemanager.models.SQLField(default='CREATE FUNCTION "{{trans_schema}}"."{{self.func_name}}"() RETURNS SETOF "{{input_table_schema}}"."{{input_table_name}}" as $$\nBEGIN\n    RETURN QUERY SELECT * FROM "{{input_table_schema}}"."{{input_table_name}}";\nEND;\n$$ LANGUAGE plpgsql;'),
            preserve_default=True,
        ),
    ]
