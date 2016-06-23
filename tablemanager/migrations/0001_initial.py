# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import re
import tablemanager.models
import django.utils.timezone
import django.core.validators


class Migration(migrations.Migration):

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='DataSource',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(unique=True, max_length=255)),
                ('last_modify_time', models.DateTimeField(default=django.utils.timezone.now, auto_now_add=True)),
            ],
            options={
                'ordering': ['name'],
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='ForeignServer',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.SlugField(unique=True, max_length=255)),
                ('user', models.CharField(max_length=320)),
                ('password', models.CharField(max_length=320)),
                ('sql', tablemanager.models.SQLField(default="CREATE SERVER {{self.name}} FOREIGN DATA WRAPPER oracle_fdw OPTIONS (dbserver '//<hostname>/<sid>');")),
                ('last_modify_time', models.DateTimeField(default=django.utils.timezone.now, auto_now_add=True)),
            ],
            options={
                'ordering': ['name'],
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='ForeignTable',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.SlugField(unique=True, max_length=255)),
                ('sql', tablemanager.models.SQLField(default="CREATE FOREIGN TABLE {{self.name}} () SERVER {{self.server.name}} OPTIONS (schema '<schema>', table '<table>');")),
                ('last_modify_time', models.DateTimeField(default=django.utils.timezone.now, auto_now_add=True)),
                ('server', models.ForeignKey(to='tablemanager.ForeignServer')),
            ],
            options={
                'ordering': ['name'],
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='Input',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('job_batch_id', models.CharField(max_length=64, null=True, editable=False)),
                ('job_id', models.IntegerField(null=True, editable=False, db_index=True)),
                ('job_state', models.CharField(max_length=64, null=True, editable=False)),
                ('job_status', models.NullBooleanField(editable=False)),
                ('job_message', models.TextField(null=True, editable=False)),
                ('job_run_time', models.DateTimeField(null=True, editable=False)),
                ('name', models.SlugField(help_text='Name of table in harvest DB', unique=True, max_length=255, validators=[django.core.validators.RegexValidator(re.compile('^[a-z0-9_]+$'), 'Slug can only contain lowercase letters, numbers and underscores', 'invalid')])),
                ('generate_rowid', models.BooleanField(default=False, help_text="If true, a _rowid column will be generated with row data's hash value")),
                ('source', tablemanager.models.XMLField(default='<OGRVRTDataSource>\n    <OGRVRTLayer name="tablename">\n        <SrcDataSource>PG:dbname=databasename host=\'addr\' port=\'5432\' user=\'x\' password=\'y\'</SrcDataSource>\n    </OGRVRTLayer>\n</OGRVRTDataSource>', help_text='GDAL VRT definition in xml', unique=True)),
                ('info', models.TextField(editable=False)),
                ('spatial_type', models.IntegerField(default=1, editable=False)),
                ('create_table_sql', models.TextField(null=True, editable=False)),
                ('last_modify_time', models.DateTimeField(default=django.utils.timezone.now, auto_now_add=True)),
                ('data_source', models.ForeignKey(to='tablemanager.DataSource')),
                ('foreign_table', models.ForeignKey(blank=True, to='tablemanager.ForeignTable', help_text='Foreign table to update VRT from', null=True)),
            ],
            options={
                'ordering': ['data_source', 'name'],
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='Normalise',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('job_batch_id', models.CharField(max_length=64, null=True, editable=False)),
                ('job_id', models.IntegerField(null=True, editable=False, db_index=True)),
                ('job_state', models.CharField(max_length=64, null=True, editable=False)),
                ('job_status', models.NullBooleanField(editable=False)),
                ('job_message', models.TextField(null=True, editable=False)),
                ('job_run_time', models.DateTimeField(null=True, editable=False)),
                ('last_modify_time', models.DateTimeField(default=django.utils.timezone.now, auto_now_add=True)),
                ('name', models.CharField(unique=True, max_length=255, validators=[django.core.validators.RegexValidator(re.compile('^[a-z0-9_]+$'), 'Slug can only contain lowercase letters, numbers and underscores', 'invalid')])),
                ('sql', tablemanager.models.SQLField(default='CREATE FUNCTION {{trans_schema}}.{{self.func_name}}() RETURNS SETOF {{normal_schema}}.{{self.output_table.name}} as $$\nBEGIN\n    RETURN QUERY SELECT * FROM {{input_schema}}.{{self.input_table.name}};\nEND;\n$$ LANGUAGE plpgsql;')),
                ('input_table', models.ForeignKey(to='tablemanager.Input')),
            ],
            options={
                'ordering': ['name'],
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='Normalise_NormalTable',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
            ],
            options={
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='NormalTable',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(unique=True, max_length=255, validators=[django.core.validators.RegexValidator(re.compile('^[a-z0-9_]+$'), 'Slug can only contain lowercase letters, numbers and underscores', 'invalid')])),
                ('create_sql', tablemanager.models.SQLField(default='CREATE TABLE {{self.name}} (name varchar(32) unique);')),
                ('priority', models.PositiveIntegerField(default=1000)),
                ('last_modify_time', models.DateTimeField(default=django.utils.timezone.now, auto_now_add=True)),
                ('normalise', models.OneToOneField(null=True, editable=False, to='tablemanager.Normalise')),
            ],
            options={
                'ordering': ['name'],
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='Publish',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('job_batch_id', models.CharField(max_length=64, null=True, editable=False)),
                ('job_id', models.IntegerField(null=True, editable=False, db_index=True)),
                ('job_state', models.CharField(max_length=64, null=True, editable=False)),
                ('job_status', models.NullBooleanField(editable=False)),
                ('job_message', models.TextField(null=True, editable=False)),
                ('job_run_time', models.DateTimeField(null=True, editable=False)),
                ('last_modify_time', models.DateTimeField(default=django.utils.timezone.now, auto_now_add=True)),
                ('name', models.CharField(db_index=True, max_length=255, validators=[django.core.validators.RegexValidator(re.compile('^[a-z0-9_]+$'), 'Slug can only contain lowercase letters, numbers and underscores', 'invalid')])),
                ('interval', models.CharField(default=b'Weekly', max_length=64, choices=[(b'Manually', b'Manually'), (b'Hourly', b'Hourly'), (b'Daily', b'Daily'), (b'Weekly', b'Weekly'), (b'Monthly', b'Monthly')])),
                ('status', models.CharField(default=b'Enabled', max_length=32, choices=[(b'Enabled', b'Enabled'), (b'Disabled', b'Disabled')])),
                ('sql', tablemanager.models.SQLField(default='CREATE FUNCTION {{trans_schema}}.{{self.func_name}}() RETURNS SETOF {{input_table_schema}}.{{input_table_name}} as $$\nBEGIN\n    RETURN QUERY SELECT * FROM {{input_table_schema}}.{{input_table_name}};\nEND;\n$$ LANGUAGE plpgsql;')),
                ('spatial_type', models.IntegerField(default=1, editable=False)),
                ('create_extra_index_sql', tablemanager.models.SQLField(null=True, blank=True)),
                ('priority', models.PositiveIntegerField(default=1000)),
                ('pgdump_file', models.FileField(null=True, editable=False)),
                ('style_file', models.FileField(null=True, editable=False)),
                ('create_table_sql', tablemanager.models.SQLField(null=True, editable=False)),
                ('running', models.PositiveIntegerField(default=0, editable=False)),
                ('completed', models.PositiveIntegerField(default=0, editable=False)),
                ('failed', models.PositiveIntegerField(default=0, editable=False)),
                ('waiting', models.PositiveIntegerField(default=0, editable=False)),
                ('job_create_time', models.DateTimeField(null=True, editable=False)),
                ('job_start_time', models.DateTimeField(null=True, editable=False)),
                ('job_end_time', models.DateTimeField(null=True, editable=False)),
                ('input_table', models.ForeignKey(blank=True, to='tablemanager.Input', null=True)),
            ],
            options={
                'abstract': False,
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='Publish_NormalTable',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('normal_table_1', models.ForeignKey(related_name='publish_normaltable_1', blank=True, to='tablemanager.NormalTable', null=True)),
                ('normal_table_2', models.ForeignKey(related_name='publish_normaltable_2', blank=True, to='tablemanager.NormalTable', null=True)),
                ('normal_table_3', models.ForeignKey(related_name='publish_normaltable_3', blank=True, to='tablemanager.NormalTable', null=True)),
                ('normal_table_4', models.ForeignKey(related_name='publish_normaltable_4', blank=True, to='tablemanager.NormalTable', null=True)),
                ('publish', models.ForeignKey(blank=True, to='tablemanager.Publish', null=True)),
            ],
            options={
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='PublishChannel',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.SlugField(help_text='Name of publish destination', unique=True, max_length=255, validators=[django.core.validators.RegexValidator(re.compile('^[a-z0-9_]+$'), 'Slug can only contain lowercase letters, numbers and underscores', 'invalid')])),
                ('sync_postgres_data', models.BooleanField(default=True)),
                ('sync_geoserver_data', models.BooleanField(default=True)),
                ('last_modify_time', models.DateTimeField(default=django.utils.timezone.now, auto_now_add=True)),
            ],
            options={
                'ordering': ['name'],
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='Replica',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('active', models.BooleanField(default=True)),
                ('namespace', models.BooleanField(default=True, help_text='Use schemas to namespace replicated tables, if not will use a prefix')),
                ('name', models.CharField(max_length=255, validators=[django.core.validators.RegexValidator(re.compile('^[a-z0-9_]+$'), 'Slug can only contain lowercase letters, numbers and underscores', 'invalid')])),
                ('link', models.TextField(default="CREATE SERVER {{self.name}} FOREIGN DATA WRAPPER postgres_fdw OPTIONS (dbserver '//<hostname>/<sid>');")),
                ('includes', models.ManyToManyField(help_text='Published tables to include, all if blank', to='tablemanager.Publish', blank=True)),
            ],
            options={
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='Workspace',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(max_length=255, validators=[django.core.validators.RegexValidator(re.compile('^[a-z0-9_]+$'), 'Slug can only contain lowercase letters, numbers and underscores', 'invalid')])),
                ('publish_channel', models.ForeignKey(to='tablemanager.PublishChannel')),
            ],
            options={
                'ordering': ['publish_channel', 'name'],
            },
            bases=(models.Model,),
        ),
        migrations.AlterUniqueTogether(
            name='workspace',
            unique_together=set([('publish_channel', 'name')]),
        ),
        migrations.AddField(
            model_name='publish',
            name='relation_1',
            field=models.OneToOneField(related_name='publish_1', null=True, blank=True, editable=False, to='tablemanager.Publish_NormalTable'),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='publish',
            name='relation_2',
            field=models.OneToOneField(related_name='publish_2', null=True, blank=True, editable=False, to='tablemanager.Publish_NormalTable'),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='publish',
            name='relation_3',
            field=models.OneToOneField(related_name='publish_3', null=True, blank=True, editable=False, to='tablemanager.Publish_NormalTable'),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='publish',
            name='workspace',
            field=models.ForeignKey(to='tablemanager.Workspace'),
            preserve_default=True,
        ),
        migrations.AlterUniqueTogether(
            name='publish',
            unique_together=set([('workspace', 'name')]),
        ),
        migrations.AddField(
            model_name='normalise_normaltable',
            name='normal_table_1',
            field=models.ForeignKey(related_name='normalise_normaltable_1', blank=True, to='tablemanager.NormalTable', null=True),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='normalise_normaltable',
            name='normal_table_2',
            field=models.ForeignKey(related_name='normalise_normaltable_2', blank=True, to='tablemanager.NormalTable', null=True),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='normalise_normaltable',
            name='normal_table_3',
            field=models.ForeignKey(related_name='normalise_normaltable_3', blank=True, to='tablemanager.NormalTable', null=True),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='normalise_normaltable',
            name='normal_table_4',
            field=models.ForeignKey(related_name='normalise_normaltable_4', blank=True, to='tablemanager.NormalTable', null=True),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='normalise_normaltable',
            name='normalise',
            field=models.ForeignKey(blank=True, to='tablemanager.Normalise', null=True),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='normalise',
            name='relation_1',
            field=models.OneToOneField(related_name='normalise_1', null=True, blank=True, editable=False, to='tablemanager.Normalise_NormalTable'),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='normalise',
            name='relation_2',
            field=models.OneToOneField(related_name='normalise_2', null=True, blank=True, editable=False, to='tablemanager.Normalise_NormalTable'),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='normalise',
            name='relation_3',
            field=models.OneToOneField(related_name='normalise_3', null=True, blank=True, editable=False, to='tablemanager.Normalise_NormalTable'),
            preserve_default=True,
        ),
    ]
