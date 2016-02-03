# coding=utf8
from __future__ import absolute_import, unicode_literals, division

import os
import re
import pytz
import logging
import tempfile
import subprocess
import threading
import time
import signal
import json
import codecs
import traceback
import xml.etree.ElementTree as ET
from functools import wraps
from datetime import datetime, timedelta

from django.db import models, connection,transaction,connections
from django.db.utils import load_backend, DEFAULT_DB_ALIAS
from django.conf import settings
from django.utils import timezone
from django.utils.encoding import force_text, python_2_unicode_compatible
from django.db.models.signals import pre_save, pre_delete,post_save,post_delete
from django.dispatch import receiver
from django.core.exceptions import ValidationError,ObjectDoesNotExist
from django.core.validators import RegexValidator
from django.template import Context, Template
from django.contrib import messages
from django.core.files.storage import FileSystemStorage
from django.conf import settings
from django.utils.safestring import SafeText

import hglib
from codemirror import CodeMirrorTextarea
from sqlalchemy import create_engine
from dj_database_url import parse

from borg_utils.gdal import detect_epsg
from borg_utils.spatial_table import SpatialTable
from borg_utils.borg_config import BorgConfiguration
from borg_utils.jobintervals import JobInterval,Weekly,Triggered
from borg_utils.publish_status import PublishStatus,EnabledStatus
from borg_utils.db_util import DbUtil
from borg_utils.signal_enable import SignalEnable
from borg_utils.hg_batch_push import try_set_push_owner, try_clear_push_owner, increase_committed_changes, try_push_to_repository
from borg_utils.signals import refresh_select_choices
from borg_utils.models import BorgModel

from tablemanager.publish_action import PublishAction

logger = logging.getLogger(__name__)

slug_re = re.compile(r'^[a-z0-9_]+$')
validate_slug = RegexValidator(slug_re, "Slug can only contain lowercase letters, numbers and underscores", "invalid")


class DownloadFileSystemStorage(FileSystemStorage):
    def __init__(self,**kwargs):
        kwargs["location"] = settings.DOWNLOAD_ROOT
        kwargs["base_url"] = settings.DOWNLOAD_URL
        super(DownloadFileSystemStorage,self).__init__(**kwargs)

    def save(self,name,content=None):
        #name should always points to a existing file.
        #import ipdb; ipdb.set_trace()
        return name

downloadFileSystemStorage = DownloadFileSystemStorage()

def in_schema(search, db_url=None,input_schema=None,trans_schema=None,normal_schema=None):
    if db_url:
        cursor = create_engine(db_url).connect()
    else:
        cursor = connection.cursor()

    schema = search.split(",")[0]
    schemas = {schema}
    if input_schema: schemas.add(input_schema)
    if trans_schema: schemas.add(trans_schema)
    if normal_schema: schemas.add(normal_schema)
    #import ipdb; ipdb.set_trace()
    sql = ";".join(["CREATE SCHEMA IF NOT EXISTS \"{}\"".format(s) for s in schemas])

    cursor.execute(sql)
    if hasattr(cursor,"close"): cursor.close()
    sql = None
    schemas = None
    cursor = None

    def schema_decorator(func):
        @wraps(func)
        def func_wrapper(*args, **kwargs):
            try:
                cursor = None
                if db_url:
                    cursor = create_engine(db_url).connect()
                else:
                    db = connections.databases[DEFAULT_DB_ALIAS]
                    backend = load_backend(db['ENGINE'])
                    conn = backend.DatabaseWrapper(db, DEFAULT_DB_ALIAS)
                    cursor = conn.cursor()

                cursor.execute(("SET search_path TO {};").format(search))
                kwargs["cursor"] = cursor
                kwargs["schema"] = schema
                if input_schema: kwargs["input_schema"] = input_schema
                if trans_schema: kwargs["trans_schema"] = trans_schema
                if normal_schema: kwargs["normal_schema"] = normal_schema

                result = func(*args, **kwargs)
            finally:
                if cursor:
                    cursor.execute("SET search_path TO {0};".format(BorgConfiguration.BORG_SCHEMA))
                    if hasattr(cursor,"close"): cursor.close()
                cursor = None

            return result
        return func_wrapper
    return schema_decorator

def switch_searchpath(cursor_pos=1,searchpath="{2}," + BorgConfiguration.BORG_SCHEMA):
    def switch_searchpath_decorator(func):
        @wraps(func)
        def func_wrapper(*args,**kwargs):
            previous_searchpath = None
            cursor = args[cursor_pos]
            searchpath_switched = False
            new_searchpath = searchpath.format(*args,**kwargs)
            try:
                #import ipdb; ipdb.set_trace()
                #get the current search path
                sql_result = cursor.execute("show search_path;")
                row = None
                if sql_result:
                    row = sql_result.fetchone()
                else:
                    row = cursor.fetchone()
                previous_searchpath = row[0]

                if previous_searchpath != new_searchpath:
                    searchpath_switched = True
                    cursor.execute("SET search_path TO {0}".format(new_searchpath))

                result = func(*args, **kwargs)
            finally:
                #reset to the original search path
                if searchpath_switched:
                    cursor.execute("SET search_path TO {0};".format(previous_searchpath))
            return result
        return func_wrapper
    return switch_searchpath_decorator


class XMLField(models.TextField):
    def formfield(self, **kwargs):
        field = super(XMLField, self).formfield(**kwargs)
        field.widget = CodeMirrorTextarea(mode="xml", theme="mdn-like")
        return field

class DatasourceWidget(CodeMirrorTextarea):
    def render(self,name,value,attrs=None):
        html = super(DatasourceWidget,self).render(name,value,attrs)
        html = SafeText('<script src="/static/js/borg.js"></script><input type="button" value="Insert Fields" onclick="insert_datasource_fields(this)">' + str(html))
        return html

class DatasourceField(models.TextField):
    def formfield(self, **kwargs):
        field = super(DatasourceField, self).formfield(**kwargs)
        field.widget = DatasourceWidget(mode="xml", theme="mdn-like",js_var_format="editor_%s")
        return field


class SQLField(models.TextField):
    def formfield(self, **kwargs):
        field = super(SQLField, self).formfield(**kwargs)
        field.widget = CodeMirrorTextarea(mode="text/x-sql", theme="mdn-like")
        return field

class JobFields(BorgModel):
    """
    Abstract model to group job related fields
    """
    job_batch_id = models.CharField(max_length=64,null=True,editable=False)
    job_id = models.IntegerField(null=True,editable=False,db_index=True)
    job_state = models.CharField(max_length=64,null=True, editable=False)
    job_status = models.NullBooleanField(null=True, editable=False)
    job_message = models.TextField(null=True, editable=False)
    job_run_time = models.DateTimeField(editable=False,null=True)

    class Meta:
        abstract = True

@python_2_unicode_compatible
class ForeignServer(BorgModel,SignalEnable):
    """
    Represents a foreign server from which the foreign table should be harvested.

    """
    name = models.SlugField(max_length=255, unique=True, help_text="The name of foreign server", validators=[validate_slug])
    user = models.CharField(max_length=320)
    password = models.CharField(max_length=320)
    sql = SQLField(default="CREATE SERVER {{self.name}} FOREIGN DATA WRAPPER oracle_fdw OPTIONS (dbserver '//<hostname>/<sid>');")
    last_modify_time = models.DateTimeField(auto_now=False,auto_now_add=True,editable=False,default=timezone.now,null=False)

    def drop(self,cursor,schema,name):
        """
        drop the foreign server from specified schema
        """
        cursor.execute("DROP SERVER IF EXISTS {0} CASCADE;".format(name))

    @switch_searchpath()
    def create(self,cursor,schema,name):
        """
        create the foreign server in specified schema
        """
        if self.name == name:
            #not in validation mode
            context = Context({"self": self})
            connect_sql = Template(self.sql).render(context)
        else:
            #in validation mode, use the testing name replace the regular name
            origname = self.name
            self.name = name
            context = Context({"self": self})
            connect_sql = Template(self.sql).render(context)
            #reset the name from testing name to regular name
            self.name = origname

        cursor.execute(connect_sql)
        cursor.execute("CREATE USER MAPPING FOR {} SERVER {} OPTIONS (user '{}', password '{}');".format(cursor.engine.url.username, name, self.user, self.password))

    @in_schema(BorgConfiguration.TEST_SCHEMA, db_url=settings.FDW_URL)
    def clean(self, cursor,schema):
        self.sql = None if not self.sql else self.sql.strip()
        if not self.sql:
            raise ValidationError("Sql can't be empty.")
        #check whether sql is ascii string
        try:
            self.sql = codecs.encode(self.sql,'ascii')
        except :
            raise ValidationError("Sql contains non ascii character.")

        name = "test_" + self.name
        try:
            #import ipdb; ipdb.set_trace()
            self.drop(cursor,schema,name)
            self.create(cursor,schema,name)
            #after validation, clear testing server and testing foreign table
            self.drop(cursor,schema,name)
        except ValidationError as e:
            raise e
        except Exception as e:
            raise ValidationError(e)

        self.last_modify_time = timezone.now()

    @in_schema("public", db_url=settings.FDW_URL)
    def execute(self, cursor,schema):
        """
        create a foreign server
        """
        self.drop(cursor,schema,self.name)
        self.create(cursor,schema,self.name)

    def delete(self,using=None):
        logger.info('Delete {0}:{1}'.format(type(self),self.name))
        if try_set_push_owner("foreign_server"):
            try:
                with transaction.atomic():
                    super(ForeignTable,self).delete(using)
                try_push_to_repository('foreign_server')
            finally:
                try_clear_push_owner("foreign_server")
        else:
            super(ForeignServer,self).delete(using)

    def save(self, force_insert=False, force_update=False, using=None, update_fields=None):
        with transaction.atomic():
            super(ForeignServer,self).save(force_insert,force_update,using,update_fields)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['name']


class ForeignServerEventListener(object):
    """
    Event listener for foreign table.

    Encapsulated the event listener into a class is to resolve the issue "Exception TypeError: "'NoneType' object is not callable" in <function <lambda> at 0x7f45abef8aa0> ignored"
    """
    @staticmethod
    @receiver(pre_save, sender=ForeignServer)
    def _pre_save(sender, instance,**kwargs):
        """
        Bind a foreign table to the FDW database. Pre-save hook for ForeignTable.
        """
        if not instance.save_signal_guard():
            return
        instance.execute()

    @staticmethod
    @receiver(pre_delete, sender=ForeignServer)
    def _pre_delete(sender, instance, **args):
        # drop server and foreign tables.
        # testing table and server have been droped immediately after validation.
        cursor=create_engine(settings.FDW_URL).connect()
        instance.drop(cursor, "public",instance.name)

@python_2_unicode_compatible
class ForeignTable(BorgModel,SignalEnable):
    """
    Represents a table to be harvested via a foreign data wrapper. Data will be
    proxied by adding a server and foreign table record to the Postgres
    database located at FDW_URL.

    Server has the same name as the foreignt table
    In validation phase, use the name ("test_" + name) for testing
    """
    name = models.SlugField(max_length=255, unique=True, help_text="The name of foreign table", validators=[validate_slug])
    server = models.ForeignKey(ForeignServer)
    sql = SQLField(default="CREATE FOREIGN TABLE \"{{schema}}\".\"{{self.name}}\" () SERVER {{self.server.name}} OPTIONS (schema '<schema>', table '<table>');")
    last_modify_time = models.DateTimeField(auto_now=False,auto_now_add=True,editable=False,default=timezone.now,null=False)

    ROW_COUNT_SQL = "SELECT COUNT(*) FROM \"{0}\".\"{1}\";"
    TABLE_MD5_SQL = "SELECT md5(string_agg(md5(CAST(t.* as text)),',')) FROM (SELECT *  from \"{0}\".\"{1}\") as t;"

    def drop(self,cursor,schema,name):
        """
        drop the foreign table from specified schema
        """
        cursor.execute("DROP FOREIGN TABLE IF EXISTS \"{0}\".\"{1}\" CASCADE;".format(schema,name))

    @switch_searchpath()
    def create(self,cursor,schema,name):
        """
        create the foreign table in specified schema
        """
        if self.name == name:
            #not in validation mode
            context = Context({"schema":schema,"self": self})
            create_sql = Template(self.sql).render(context)
        else:
            #in validation mode, use the testing name replace the regular name
            origname = self.name
            self.name = name
            context = Context({"schema":schema,"self": self})
            create_sql = Template(self.sql).render(context)
            #reset the name from testing name to regular name
            self.name = origname

        cursor.execute(create_sql)
        cursor.execute("SELECT COUNT(*) FROM \"{}\";".format(name))

    @in_schema(BorgConfiguration.TEST_SCHEMA, db_url=settings.FDW_URL)
    def clean(self, cursor,schema):
        #generate the testing name
        self.sql = None if not self.sql else self.sql.strip()
        if not self.sql:
            raise ValidationError("Sql can't be empty.")
        #check whether sql is ascii string
        try:
            self.sql = codecs.encode(self.sql,'ascii')
        except :
            raise ValidationError("Sql contains non ascii character.")

        name = "test_" + self.name
        try:
            #import ipdb; ipdb.set_trace()
            self.drop(cursor,schema,name)
            self.create(cursor,schema,name)
            #after validation, clear testing server and testing foreign table
            self.drop(cursor,schema,name)
        except ValidationError as e:
            raise e
        except Exception as e:
            raise ValidationError(e)

        self.last_modify_time = timezone.now()

    @in_schema("public", db_url=settings.FDW_URL)
    def execute(self, cursor,schema):
        """
        Bind a foreign table to the FDW database. Pre-save hook for ForeignTable.
        """
        self.drop(cursor,schema,self.name)
        self.create(cursor,schema,self.name)

    @in_schema("public", db_url=settings.FDW_URL)
    def table_row_count(self,cursor,schema):
        sql_result = cursor.execute(self.ROW_COUNT_SQL.format(schema,self.name))
        if sql_result:
            return sql_result.fetchone()[0]
        else:
            return cursor.fetchone()[0]

    @in_schema("public", db_url=settings.FDW_URL)
    def table_md5(self,cursor,schema):
        sql_result = cursor.execute(self.TABLE_MD5_SQL.format(schema,self.name))
        if sql_result:
            return sql_result.fetchone()[0]
        else:
            return cursor.fetchone()[0]

    def delete(self,using=None):
        logger.info('Delete {0}:{1}'.format(type(self),self.name))
        if try_set_push_owner("foreign_table"):
            try:
                with transaction.atomic():
                    super(ForeignTable,self).delete(using)
                try_push_to_repository('foreign_table')
            finally:
                try_clear_push_owner("foreign_table")
        else:
            super(ForeignTable,self).delete(using)

    def save(self, force_insert=False, force_update=False, using=None, update_fields=None):
        with transaction.atomic():
            super(ForeignTable,self).save(force_insert,force_update,using,update_fields)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['name']


class ForeignTableEventListener(object):
    """
    Event listener for foreign table.

    Encapsulated the event listener into a class is to resolve the issue "Exception TypeError: "'NoneType' object is not callable" in <function <lambda> at 0x7f45abef8aa0> ignored"
    """
    @staticmethod
    @receiver(pre_save, sender=ForeignTable)
    def _pre_save(sender, instance,**kwargs):
        """
        Bind a foreign table to the FDW database. Pre-save hook for ForeignTable.
        """
        if not instance.pk:
            instance.new_object = True

        if not instance.save_signal_guard():
            return
        instance.execute()

    @staticmethod
    @receiver(post_save, sender=ForeignTable)
    def _post_save(sender, instance, **args):
        if (hasattr(instance,"new_object") and getattr(instance,"new_object")):
            delattr(instance,"new_object")
            refresh_select_choices.send(instance,choice_family="foreigntable")

    @staticmethod
    @receiver(pre_delete, sender=ForeignTable)
    def _pre_delete(sender, instance, **args):
        # drop server and foreign tables.
        # testing table and server have been droped immediately after validation.
        cursor=create_engine(settings.FDW_URL).connect()
        instance.drop(cursor, "public",instance.name)

    @staticmethod
    @receiver(post_delete, sender=ForeignTable)
    def _post_delete(sender, instance, **args):
        refresh_select_choices.send(instance,choice_family="foreigntable")


@python_2_unicode_compatible
class DataSource(BorgModel,SignalEnable):
    """
    Represents a data source which the input is belonging to

    """
    name = models.SlugField(max_length=255, unique=True, help_text="The name of data source", validators=[validate_slug])
    last_modify_time = models.DateTimeField(auto_now=False,auto_now_add=True,editable=False,default=timezone.now,null=False)

    @in_schema(BorgConfiguration.TEST_SCHEMA, db_url=settings.FDW_URL)
    def clean(self, cursor,schema):
        #generate the testing name
        self.last_modify_time = timezone.now()

    def delete(self,using=None):
        logger.info('Delete {0}:{1}'.format(type(self),self.name))
        if try_set_push_owner("data_source"):
            try:
                with transaction.atomic():
                    super(ForeignTable,self).delete(using)
                try_push_to_repository('data_source')
            finally:
                try_clear_push_owner("data_source")
        else:
            super(DataSource,self).delete(using)

    def save(self, force_insert=False, force_update=False, using=None, update_fields=None):
        with transaction.atomic():
            super(DataSource,self).save(force_insert,force_update,using,update_fields)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['name']

@python_2_unicode_compatible
class Input(JobFields,SignalEnable):
    """
    Represents an input table in the harvest DB. Also contains source info
    (as a GDAL VRT definition) so it can be loaded using the OGR toolset.
    """
    name = models.SlugField(max_length=255, unique=True, help_text="Name of table in harvest DB", validators=[validate_slug])
    data_source = models.ForeignKey(DataSource)
    foreign_table = models.ForeignKey(ForeignTable, null=True, blank=True, help_text="Foreign table to update VRT from")
    generate_rowid = models.BooleanField(null=False, default=False, help_text="If true, a _rowid column will be added and filled with row data's hash value")
    source = DatasourceField(help_text="GDAL VRT definition in xml", default=(
        '<OGRVRTDataSource>\n'
        '    <OGRVRTLayer name="tablename">\n'
        "        <SrcDataSource>PG:dbname=databasename host='addr' port='5432' user='x' password='y'</SrcDataSource>\n"
        '    </OGRVRTLayer>\n'
        '</OGRVRTDataSource>'
    ), unique=True)
    advanced_options = models.CharField(max_length=128, null=True, editable=False,blank=True,help_text="Advanced ogr2ogr options")
    info = models.TextField(editable=False)
    spatial_type = models.IntegerField(default=1,editable=False)
    create_table_sql = models.TextField(null=True, editable=False)
    importing_info = models.TextField(max_length=255, null=True, editable=False)
    last_modify_time = models.DateTimeField(auto_now=False,auto_now_add=True,editable=False,default=timezone.now,null=False)
    ds_modify_time = models.DateTimeField(editable=False,null=True)

    ABSTRACT_TEMPLATE = """{% if info_dict.abstract %}{{ info_dict.abstract }}

{% endif %}{% if info_dict.mdDateSt %}Date: {{ info_dict.mdDateSt }}
{% endif %}{% if info_dict.lineage %}Lineage: {{ info_dict.lineage }}
{% endif %}{% if info_dict.complete %}Completeness: {{ info_dict.complete }}
{% endif %}{% if info_dict.posacc %}Positional accuracy: {{ info_dict.posacc }}
{% endif %}{% if info_dict.attracc %}Attribute accuracy: {{ info_dict.attracc }}
{% endif %}"""

    @property
    def rowid_column(self):
        return BorgConfiguration.ROWID_COLUMN

    _datasource = None
    _datasource_re = re.compile("<SrcDataSource>(?P<data_source>.*)</SrcDataSource>")
    @property
    def datasource(self):
        """
        The data source;
        If data source is a file, the value is the file path.
        If data source is foreign table, the value is the connection parameters
        """
        if not self._datasource and self.source:
            self._datasource = self._datasource_re.findall(self.source)
        return self._datasource

    _style_file = 'N/A'
    @property
    def style_file(self):
        """
        Return the style file
        if data source is not a shape file or style file does not exist, return None
        """
        #import ipdb;ipdb.set_trace()
        if self._style_file == 'N/A':
            if self.datasource:
                #datasource has valid value
                if self.datasource[0].lower().endswith(".shp"):
                    #datasource is a shape file
                    f = self.datasource[0][:-4]+".sld"
                    if os.path.exists(f):
                        #sld file exists
                        self._style_file = f
                    else:
                        #sld file not exists
                        self._style_file = None
        if self._style_file and self._style_file != "N/A":
            return self._style_file
        else:
            return None

    @property
    def vrt(self):
        """
        A temporary vrt format file which contains the data source information.
        """
        if hasattr(self, "_vrt"): return self._vrt
        self._vrt = tempfile.NamedTemporaryFile()
        self._vrt.write(Template(self.source).render(Context({"self": self})))
        self._vrt.flush()
        return self._vrt

    @property
    def info_dict(self):
        """
        A dictionary contains the key information about a data source.
        """
        now = datetime.now()
        if hasattr(self,"_info_dict"):
            if (now - self._info_dict.get("_last_update", now)) < timedelta(hours=1):
                return self._info_dict

        #import ipdb;ipdb.set_trace()
        search , info = "(Layer name: .*)\n(Geometry: .*)\n(Feature Count: .*)\n(Extent: .*)\n", self.info
        if not info.find("Extent: ") > -1:
            info = info.replace("\nLayer SRS", "\nExtent: Non Spatial\nLayer SRS")
        data = re.findall(search, info, re.M)
        if data and len(data) >= 1:
            self._info_dict = dict([(r.split(": ")[0].replace(" ", "_").lower(), r.split(": ")[1])
                for r in data[0]])
        else:
            self._info_dict = {"geometry": "Unknown", "feature_count": "Unknown", "extent": "Unknown"}

        self._info_dict["_last_update"] = now

        return self._info_dict

    @property
    def layer(self):
        """
        the layer name of the data source.
        """
        try:
            return self.info_dict["layer_name"]
        except:
            return self.get_layer_name()

    @property
    def kmi_info_dict(self):
        if not self.datasource:
            return

        info = self.info_dict
        if info.get("kmi_info_populated",False):
            return info

        if os.path.isfile(self.datasource[0] + ".xml"):
            xml_data = ET.parse(self.datasource[0] + ".xml")
            def tag_to_dict(tag):
                for i in [x.text for x in xml_data.iter(tag) if x.text]:
                    info[tag] = ' '.join(i.split())
                    return

            tag_to_dict("abstract")
            tag_to_dict("title")
            tag_to_dict("lineage")
            tag_to_dict("posacc")
            tag_to_dict("attracc")
            tag_to_dict("complete")
            tag_to_dict("mdDateSt")

            info["kmi_abstract"] = Template(self.ABSTRACT_TEMPLATE).render(Context({"info_dict": info}))

        info["kmi_info_populated"] = True

        return info



    @property
    def kmi_abstract(self):
        return self.kmi_info_dict.get("kmi_abstract","")

    @property
    def abstract(self):
        return self.kmi_info_dict.get("abstract","")

    @property
    def title(self):
        return self.kmi_info_dict.get("title", "")

    @property
    def geometry(self): return self.info_dict["geometry"]

    @property
    def count(self): return self.info_dict["feature_count"]

    @property
    def extent(self): return self.info_dict["extent"]

    @property
    def importing_dict(self):
        if not hasattr(self,"_importing_dict"):
            if self.importing_info:
                self._importing_dict = json.loads(self.importing_info)
            else:
                self._importing_dict = {}
        return self._importing_dict

    def is_up_to_date(self,job=None,enforce=False):
        """
        Returns True if up to date;otherwise return False
        """
        #import ipdb;ipdb.set_trace()
        from harvest.harveststates import Importing
        if (self.job_status or self.job_state != Importing.instance().name) and self.job_id and self.job_batch_id and self.datasource and self.job_run_time:
            if not enforce and job and job.batch_id:
                if job.batch_id == self.job_batch_id:
                    #last importing job has the same batch_id as  current job
                    return True
                elif self.importing_dict and self.importing_dict.get("check_batch_id") == job.batch_id:
                    #last checking job has the same batch_id as current job
                    return True
            try:
                if self.job_run_time <= self.last_modify_time:
                    return False

                if self.foreign_table:
                    if not job:
                        return None
                    elif job.job_type == Triggered.instance().name:
                        return False
                    elif job.batch_id:
                        if "table_md5" in self.importing_dict and "row_count" in self.importing_dict:
                            if self.foreign_table.table_row_count() != self.importing_dict["row_count"]:
                                #inputing table has different number of rows with inputed table
                                self.importing_info = None
                                self.save(update_fields=['importing_info'])
                                return False
                            if self.foreign_table.table_md5() == self.importing_dict["table_md5"]:
                                self.importing_dict["check_job_id"] = job.id
                                self.importing_dict["check_batch_id"] = job.batch_id
                                self.importing_info = json.dumps(self.importing_dict)
                                self.save(update_fields=['importing_info'])
                                return True
                            else:
                                self.importing_info = None
                                self.save(update_fields=['importing_info'])
                                return False
                        else:
                            return False
                    else:
                        return False
                else:
                    mod_time = None
                    result = True
                    if job and job.batch_id:
                        #check for harvest, should always check.
                        for ds in self.datasource:
                            if os.path.exists(ds):
                                #data source is a file
                                if self.job_run_time <= datetime.utcfromtimestamp(os.path.getmtime(ds)).replace(tzinfo=pytz.UTC):
                                    return False
                            else:
                                result = None
                    else:
                        #check for web app. check against "ds_modify_time" which is harvested by harvest job.
                        if self.ds_modify_time:
                            result = self.job_run_time > self.ds_modify_time
                        else:
                            result = None

                    return result
            except:
                return False

        return False

    def _populate_rowid(self,cursor,schema):
        """
        generate the rowid for input table
        if the input table is not required to generate rowid, return directly.
        otherwise,do the follwoing things:
        1. add a rowid column, and set rowid as primary key
        2. construnct the sql to update the rowid.
        3. execute the sql.
        """
        if not self.generate_rowid:
            return

        #check whether rowid column exists or not
        sql = "SELECT count(1) FROM pg_attribute a JOIN pg_class b ON a.attrelid = b.oid JOIN pg_namespace c ON b.relnamespace = c.oid WHERE a.attname='{2}' AND b.relname='{1}' AND c.nspname='{0}' ".format(schema,self.name,self.rowid_column)
        sql_result = cursor.execute(sql)
        column_exists = None
        if sql_result:
            column_exists = (sql_result.fetchone())[0]
        else:
            column_exists = (cursor.fetchone())[0]

        #add rowid column if required
        if not column_exists:
            #add column
            sql = "ALTER TABLE {0}.{1} ADD COLUMN {2} text".format(schema,self.name,self.rowid_column)
            cursor.execute(sql)

        #construct the update sql
        sql = "SELECT a.attname FROM pg_attribute a JOIN pg_class b ON a.attrelid = b.oid JOIN pg_namespace c ON b.relnamespace = c.oid WHERE a.attnum > 0 AND a.attname != '{2}' AND b.relname='{1}' AND c.nspname='{0}' ".format(schema,self.name,self.rowid_column)
        sql_result = cursor.execute(sql)
        input_table_columns = None
        if sql_result:
            input_table_columns = ",".join([x[0] for x in sql_result.fetchall()])
        else:
            input_table_columns = ",".join([x[0] for x in cursor.fetchall()])
        sql = "UPDATE \"{0}\".\"{1}\" set {2} = md5(CAST(({3}) AS text))".format(schema,self.name,self.rowid_column,input_table_columns)
        cursor.execute(sql)

        #set the rowid as the unique key
        #first check whether the unique key exists or not
        constraint_name = "{0}_index_{1}".format(self.name,self.rowid_column)
        sql = "SELECT count(1) FROM pg_constraint a JOIN pg_class b ON a.conrelid = b.oid JOIN pg_namespace c ON b.relnamespace = c.oid WHERE a.conname='{2}' AND b.relname='{1}' AND c.nspname='{0}' ".format(schema,self.name,constraint_name)
        sql_result = cursor.execute(sql)
        constraint_exists = None
        if sql_result:
            constraint_exists = (sql_result.fetchone())[0]
        else:
            constraint_exists = (cursor.fetchone())[0]
        if not constraint_exists:
            #unique key does not exist
            sql = "ALTER TABLE \"{0}\".\"{1}\" ADD CONSTRAINT {3} UNIQUE ({2})".format(schema,self.name,self.rowid_column,constraint_name)
            cursor.execute(sql)

    @in_schema(BorgConfiguration.INPUT_SCHEMA)
    def populate_rowid(self,cursor,schema):
        self._populate_rowid(cursor,schema)

    @in_schema(BorgConfiguration.TEST_INPUT_SCHEMA + "," + BorgConfiguration.BORG_SCHEMA)
    def clean(self,cursor,schema):
        self.source = None if not self.source else self.source.strip()
        if not self.source:
            raise ValidationError("Source can't be empty.")
    
        if self.foreign_table:
            self.source = re.sub('(<OGRVRTLayer name=")[^"]+(">)', r'\1{}\2'.format(self.foreign_table.name), self.source)
            self.source = re.sub('(<SrcDataSource>)[^<]+(</SrcDataSource>)', r"\1PG:dbname='{NAME}' host='{HOST}' user='{USER}' password='{PASSWORD}' port='{PORT}'\2".format(**parse(settings.FDW_URL)), self.source)

        self.advanced_options = None if not self.advanced_options else self.advanced_options.strip() or None

        #check whether need to do validation.
        orig = None
        if self.pk:
            orig = Input.objects.get(pk=self.pk)

        if orig and orig.source == self.source and orig.generate_rowid == self.generate_rowid and self.advanced_options == orig.advanced_options:
            #data source and generate_rowid not changed, no need to do the validation.
            return
        #import ipdb;ipdb.set_trace()
        self.last_modify_time = timezone.now()

        try:
            self._set_info(cursor)
            #automatically add a "<GeometryType>WkbNone</GeometryType>" if the data set is not a spatial data set
            if self.source.find("GeometryType") == -1 and self.source.find("GeometryField") == -1 and self.source.find("LayerSRS") == -1:
                #data source does not contain any spatial related properties.
                if self.extent.lower().find("non spatial") >= 0:
                    #data source is not a spatial data set. try to insert a element <GeometryType>wkbNone</GeometryType>
                    self.source = self.source.replace("</SrcDataSource>","</SrcDataSource>\n        <GeometryType>wkbNone</GeometryType>")
                    if hasattr(self, "_vrt"): delattr(self,"_vrt")
                    self._set_info(cursor)

            self.invoke(cursor,schema)

            self._populate_rowid(cursor,schema)

            self.create_table_sql = DbUtil.get_create_table_sql(BorgConfiguration.TEST_INPUT_SCHEMA,self.name)

            #import ipdb;ipdb.set_trace()
            #check the table is spatial or non spatial
            self.spatial_type = SpatialTable.get_instance(cursor,schema,self.name,True).spatial_type
        except ValidationError as e:
            raise e
        except Exception as e:
            raise ValidationError(e)

    def get_layer_name(self):
        """
        return the data source's layer name
        """
        if hasattr(self, "_layer_name"): return self._layer_name
        output = subprocess.check_output(["ogrinfo", "-q", "-ro", self.vrt.name], stderr=subprocess.STDOUT)
        if output.find("ERROR") > -1:
            raise Exception(l)
        else:
            self._layer_name = output.replace("1: ", "").split(" (")[0].strip()
            return self._layer_name

    _layer_name_re = re.compile('Layer name: [^\n]*\n')
    def _set_info(self,cursor,database=None,table=None):
        """
        set the data source's information dictionary
        if database is not None, read the information from table;
        if database is None, read the information from data source;
        """
        #import ipdb;ipdb.set_trace()
        if database and table:
            cmd = ["ogrinfo", "-ro", "-so", database, table]
        else:
            cmd = ["ogrinfo", "-ro","-al","-so", self.vrt.name]

        p = subprocess.Popen(cmd, stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        output = p.communicate()
        error_msg = output[1].replace("ERROR 1: Invalid geometry field index : -1","")
        if error_msg.strip():
            raise Exception(error_msg)
        try:
            delattr(self,"_info_dict")
        except:
            pass

        self.info = output[0]
        if database and table:
            #replace the layername with datasource's layer name
            self.info = Input._layer_name_re.sub("Layer name: {0}\n".format(self.get_layer_name()),output[0],count=1)
        else:
            self.info = output[0]

    def invoke(self ,cursor,schema,job_id=None):
        """
        Use ogr2ogr to copy the VRT source defined in Input into the harvest DB.
        Pre-save hook for Input.

        can be invoked by havest or user maintain action

        Return True if import successfully; False if import process is terminated.
        """
        validation = not job_id

        # Make sure DB is GIS enabled and then load using ogr2ogr
        database = "PG:dbname='{NAME}' host='{HOST}' port='{PORT}'  user='{USER}' password='{PASSWORD}'".format(**settings.DATABASES["default"])
        table = "{0}.{1}".format(schema,self.name)
        cursor.execute("CREATE EXTENSION IF NOT EXISTS postgis;")
        cmd = ["ogr2ogr", "-overwrite", "-gt", "20000", "-preserve_fid", "-skipfailures", "--config", "PG_USE_COPY", "YES",
            "-f", "PostgreSQL", database, self.vrt.name, "-nln", table, "-nlt", "PROMOTE_TO_MULTI", self.layer]

        if self.advanced_options:
            cmd += self.advanced_options.split()

        srid = detect_epsg(self.vrt.name)
        if srid:
            cmd += ['-a_srs', srid]
        logger.info(" ".join(cmd))
        cancelled = False
        p = subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        if validation:
            sleep_time = 0
            max_sleep_time = BorgConfiguration.MAX_TEST_IMPORT_TIME * 1000
            finished = False
            table_exist = False
            while sleep_time < max_sleep_time or not table_exist:
                if p.poll() is not None:
                    finished = True
                    break;
                time.sleep(0.2)
                sleep_time += 200
                if not table_exist and sleep_time>= max_sleep_time:
                    sql_result = cursor.execute("SELECT count(1) FROM pg_class a JOIN pg_namespace b ON a.relnamespace=b.oid where a.relname='{1}' and b.nspname='{0}'".format(schema,self.name))
                    table_exist = bool(sql_result.fetchone()[0] if sql_result else cursor.fetchone()[0])

            if not finished:
                logger.info("The data set is too big, terminate the test importing process for '{0}'".format(self.name))
                cancelled = True
                try:
                    p.terminate()
                except:
                    pass

            returncode = p.wait()
            output = p.communicate()
            if returncode != signal.SIGTERM * -1 and output[1].strip():
                raise Exception(output[1])

        else:
            sleep_time = 0
            cancel_time = BorgConfiguration.IMPORT_CANCEL_TIME * 1000
            from harvest.jobstates import JobStateOutcome
            cancelled = False
            while True:
                if p.poll() is not None:
                    break;
                time.sleep(0.2)
                sleep_time += 200
                if sleep_time >= cancel_time:
                    sleep_time = 0
                    job = self._get_job(cursor,job_id)
                    if job.user_action and job.user_action.lower() == JobStateOutcome.cancelled_by_custodian.lower():
                        #job cancelled
                        try:
                            p.terminate()
                        except:
                            pass
                        cancelled = True
                        logger.info("The job({1}) is cancelled, terminate the importing process for '{0}'".format(self.name,job_id))
                        break;

            returncode = p.wait()
            output = p.communicate()
            if cancelled:
                #clear the user action
                job.user_action = None
                self._save_job(cursor,job,["user_action"])
            else:
                if output[1].strip() :
                    raise Exception(output[1])
                self._set_info(cursor,database,table)

        return not cancelled

    @switch_searchpath(searchpath=BorgConfiguration.BORG_SCHEMA)
    def _get_job(self,cursor,job_id):
        from harvest.models import Job
        return Job.objects.get(pk=job_id)

    @switch_searchpath(searchpath=BorgConfiguration.BORG_SCHEMA)
    def _save_job(self,cursor,job,update_fields):
        job.save(update_fields=update_fields)

    @switch_searchpath(searchpath=BorgConfiguration.BORG_SCHEMA)
    def _post_execute(self,cursor):
        if self.foreign_table:
            self.importing_dict["row_count"] = self.foreign_table.table_row_count()
            self.importing_dict["table_md5"] = self.foreign_table.table_md5()
            if "check_job_id" in self.importing_dict: del self.importing_dict["check_job_id"]
            if "check_batch_id" in self.importing_dict: del self.importing_dict["check_batch_id"]
            #import ipdb;ipdb.set_trace()
            self.importing_info = json.dumps(self.importing_dict)
        self.save(update_fields=["importing_info","job_run_time","info"])

    @in_schema(BorgConfiguration.INPUT_SCHEMA)
    def execute(self,job_id ,cursor,schema):
        begin_time = timezone.now()
        if self.invoke(cursor,schema,job_id):
            # all data is imported
            self.job_run_time = begin_time
            #save the latest data source information to table
            self._post_execute(cursor)
        else:
            #import process is cancelled
            from harvest.jobstates import JobStateOutcome
            return (JobStateOutcome.cancelled_by_custodian,JobStateOutcome.cancelled_by_custodian)


    def drop(self,cursor,schema):
        cursor.execute("DROP TABLE IF EXISTS \"{0}\".\"{1}\" CASCADE;".format(schema,self.name))

    def create(self,cursor,schema):
        pass

    def delete(self,using=None):
        logger.info('Delete {0}:{1}'.format(type(self),self.name))
        if try_set_push_owner("input"):
            try:
                with transaction.atomic():
                    super(Input,self).delete(using)
                try_push_to_repository('input')
            finally:
                try_clear_push_owner("input")
        else:
            super(Input,self).delete(using)

    def save(self, force_insert=False, force_update=False, using=None, update_fields=None):
        with transaction.atomic():
            super(Input,self).save(force_insert,force_update,using,update_fields)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['data_source','name']

class InputEventListener(object):
    @staticmethod
    @receiver(pre_delete, sender=Input)
    def _pre_delete(sender, instance, **args):
        # drop tables in both schema
        cursor=connection.cursor()
        instance.drop(cursor, BorgConfiguration.TEST_INPUT_SCHEMA)
        instance.drop(cursor, BorgConfiguration.INPUT_SCHEMA)

    @staticmethod
    @receiver(post_delete, sender=Input)
    def _post_delete(sender, instance, **args):
        refresh_select_choices.send(instance,choice_family="input")

    @staticmethod
    @receiver(pre_save, sender=Input)
    def _pre_save(sender, instance,**kwargs):
        if not instance.pk:
            instance.new_object = True

    @staticmethod
    @receiver(post_save, sender=Input)
    def _post_save(sender, instance, **args):
        if (hasattr(instance,"new_object") and getattr(instance,"new_object")):
            delattr(instance,"new_object")
            refresh_select_choices.send(instance,choice_family="input")

@python_2_unicode_compatible
class Transform(JobFields):
    """
    Base class for a generic transform to be performed on an Input table in
    the harvest DB.
    """
    last_modify_time = models.DateTimeField(auto_now=False,auto_now_add=True,editable=False,default=timezone.now,null=False)

    def drop(self, cursor,schema):
        """
        drop the function from specified schema
        """
        cursor.execute("DROP FUNCTION IF EXISTS \"{0}\".\"{1}\"() CASCADE;".format(schema,self.func_name))

    @switch_searchpath()
    def create(self, cursor,schema,input_schema=None,normal_schema=None,input_table_schema=None,input_table_name=None):
        """
        create the function in specified schema
        """
        if input_table_schema:
            sql = Template(self.sql).render(Context({"self": self,"trans_schema":schema,"input_schema":input_schema,"normal_schema":normal_schema,"input_table_schema":input_table_schema,"input_table_name":input_table_name}))
        else:
            sql = Template(self.sql).render(Context({"self": self,"trans_schema":schema,"input_schema":input_schema,"normal_schema":normal_schema}))
        cursor.execute(sql)

    def invoke(self, **kwargs):
        """
        invoke the function to populate the table data in speicifed schema
        """
        raise NotImplementedError("Not implemented.")

    def execute(self):
        """
        execute this function
        """
        raise NotImplementedError("Not implemented.")

    def __str__(self):
        return self.name

    class Meta:
        abstract = True


class Normalise(Transform,SignalEnable):
    """
    Represents a normalisation transform to be performed on an Input table
    in the harvest DB.
    """
    TRANSFORM = [
        "CREATE FUNCTION \"{{trans_schema}}\".\"{{self.func_name}}\"() RETURNS SETOF \"{{normal_schema}}\".\"{{self.output_table.name}}\" as ",
        "\nBEGIN\n    RETURN QUERY SELECT * FROM \"{{input_schema}}\".\"{{self.input_table.name}}\";\nEND;\n",
        " LANGUAGE plpgsql;"
    ]
    name = models.CharField(unique=True, max_length=255, validators=[validate_slug],editable=True)
    input_table = models.ForeignKey(Input) # Referencing the schema which to introspect for the output of this transform
    sql = SQLField(default="$$".join(TRANSFORM).strip())
    relation_1 = models.OneToOneField('Normalise_NormalTable',blank=True,null=True,related_name="normalise_1",editable=False)
    relation_2 = models.OneToOneField('Normalise_NormalTable',blank=True,null=True,related_name="normalise_2",editable=False)
    relation_3 = models.OneToOneField('Normalise_NormalTable',blank=True,null=True,related_name="normalise_3",editable=False)

    normal_table = None


    def init_relations(self):
        """
        initialize relations
        if relations is None, create a empty one
        """
        if self.relation_1 is None:
            self.relation_1 = Normalise_NormalTable()

        if self.relation_2 is None:
            self.relation_2 = Normalise_NormalTable()

        if self.relation_3 is None:
            self.relation_3 = Normalise_NormalTable()

    def set_relation(self,pos,relation):
        """
        set the relation at position, position is based 0
        """
        if pos == 0:
            self.relation_1 = relation
        elif pos == 1:
            self.relation_2 = relation
        elif pos == 2:
            self.relation_3 = relation

    @property
    def relations(self):
        return [self.relation_1,self.relation_2,self.relation_3]

    @property
    def func_name(self):
        """
        normalise function name
        """
        return "n_{0}".format(self.name)

    @property
    def output_table(self):
        """
        The output table
        The user input value has high priority than database value.
        """
        if self.normal_table:
            return self.normal_table
        elif self.pk:
            try:
                return self.normaltable
            except:
                return None
        else:
            return None

    def is_up_to_date(self,job=None,enforce=False):
        """
        Returns True if up to date;otherwise return False
        """
        #import ipdb;ipdb.set_trace()
        if self.job_status and self.job_id and self.job_batch_id and self.job_run_time and self.normaltable and self.input_table:
            if self.job_run_time <= self.last_modify_time or self.job_run_time <= self.normaltable.last_modify_time:
                #normalise or normal table have been modified after last job run time.
                return False
            up_to_date = self.input_table.is_up_to_date(job,enforce)
            result = True
            if up_to_date == False:
                #input_table is not up to date
                return False
            elif up_to_date is None:
                result = None

            if self.job_run_time < self.input_table.job_run_time:
                #input table is up to date but input table's last job run after normalise's last job run.
                return False
            for relation in self.relations:
                if relation:
                    for normal_table in relation.normal_tables:
                        if normal_table:
                            up_to_date = normal_table.is_up_to_date(job,enforce)
                            #import ipdb;ipdb.set_trace()
                            if up_to_date == False:
                                #dependent normal table is not up to date
                                return False
                            elif up_to_date is None:
                                result = None
                            if self.job_run_time < normal_table.job_run_time:
                                #dependent normal table is up to date but its last job run after normalise's last job run.
                                return False
            return result
        else:
            return False

    @property
    def inputs(self):
        if not hasattr(self,"_inputs_cache"):
            inputs = []
            for n in self.normalises:
                if not n.input_table:
                    raise ValidationError("Normalise({0}) does not connect to a input table.".format(self.name))
                if n.input_table not in inputs:
                    inputs.append(n.input_table)

            self._inputs_cache = inputs

        return self._inputs_cache

    @property
    def normalises(self):
        """
        return  a sorted normalises including self and dependent normalises based on dependency relationship
        """
        return self._normalises()

    def _normalises(self,parents=None):
        """
        return  a sorted normalises including self and dependent normalises based on dependency relationship
        """
        if not hasattr(self,"_normalises_cache"):
            normalises = [self]
            if parents:
                parents = parents + [self]
            else:
                parents = [self]

            for relation in self.relations:
                if not relation:
                    continue
                for normal_table in relation.normal_tables:
                    if not normal_table:
                        continue
                    try:
                        if not normal_table.normalise:
                            raise ValidationError("NormalTable({0}) does not connect to a normalise function.".format(normal_table.name))
                    except ObjectDoesNotExist:
                        raise ValidationError("NormalTable({0}) does not connect to a normalise function.".format(normal_table.name))
                    if normal_table.normalise in parents:
                        raise ValidationError("Found a circular dependency:{0}".format("=>".join([n.name for n in parents + [normal_table.normalise]])))

                    for n in  normal_table.normalise._normalises(parents):
                        if n not in normalises:
                            normalises.append(n)

            self._normalises_cache = list(reversed(normalises))

        return self._normalises_cache


    def invoke(self, cursor,trans_schema,input_schema,normal_schema):
        """
        invoke the function to populate the table data in specified schema
        """
        #populate the data
        sql = "INSERT INTO \"{3}\".\"{0}\" SELECT * FROM \"{2}\".\"{1}\"();".format(self.output_table.name, self.func_name, trans_schema, normal_schema)
        cursor.execute(sql)

    @in_schema(BorgConfiguration.TEST_TRANSFORM_SCHEMA + "," + BorgConfiguration.BORG_SCHEMA,input_schema=BorgConfiguration.TEST_INPUT_SCHEMA,normal_schema=BorgConfiguration.TEST_NORMAL_SCHEMA)
    def clean(self, cursor,schema,input_schema,normal_schema):
        """
        Check whether the publish function is correct, by creating in test schema
        """
        self.sql = None if not self.sql else self.sql.strip()
        if not self.sql:
            raise ValidationError("Sql can't be empty.")

        #check whether sql is ascii string
        try:
            self.sql = codecs.encode(self.sql,'ascii')
        except :
            raise ValidationError("Sql contains non ascii character.")


        try:
            #import ipdb;ipdb.set_trace()
            self.last_modify_time = timezone.now()
            #import ipdb; ipdb.set_trace()
            if self.normal_table:
                #check the circle dependency relationship
                all_normalises = self.normalises

            #drop the previous created testing function
            self.drop(cursor,schema)

            if self.normal_table:
                #recreate the normal table
                self.output_table.drop(cursor,normal_schema)
                self.output_table.create(cursor,normal_schema)

                #speicfy a output normal table
                self.create(cursor,schema,input_schema,normal_schema)

                #invoke the normalise function to check whether it is correct or not.
                self.invoke(cursor,schema,input_schema,normal_schema)
        except ValidationError as e:
            logger.error(traceback.format_exc())
            raise e
        except Exception as e:
            logger.error(traceback.format_exc())
            raise ValidationError(e)



    @switch_searchpath(searchpath=BorgConfiguration.BORG_SCHEMA)
    def _post_execute(self,cursor):
        self.save(update_fields=['job_run_time'])

    @in_schema(BorgConfiguration.TRANSFORM_SCHEMA + "," + BorgConfiguration.BORG_SCHEMA,input_schema=BorgConfiguration.INPUT_SCHEMA,normal_schema=BorgConfiguration.NORMAL_SCHEMA)
    def execute(self,cursor,schema,input_schema,normal_schema):
        """
        recreate the normailzied table and repopulate the table data
        """
        begin_time = timezone.now()
        self.drop(cursor,schema)
        self.output_table.drop(cursor,normal_schema)
        self.output_table.create(cursor,normal_schema)
        self.create(cursor,schema,input_schema,normal_schema)
        self.invoke(cursor,schema,input_schema,normal_schema)
        self.job_run_time = begin_time
        self._post_execute(cursor)

    def delete(self,using=None):
        logger.info('Delete {0}:{1}'.format(type(self),self.name))
        if try_set_push_owner("normalise"):
            try:
                with transaction.atomic():
                    super(Normalise,self).delete(using)
                try_push_to_repository('normalise')
            finally:
                try_clear_push_owner("normalise")
        else:
            super(Normalise,self).delete(using)

    def save(self, force_insert=False, force_update=False, using=None, update_fields=None):
        with transaction.atomic():
            super(Normalise,self).save(force_insert,force_update,using,update_fields)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['name']

class NormaliseEventListener(object):
    @staticmethod
    @receiver(pre_delete, sender=Normalise)
    def _pre_delete(sender, instance, **args):
        # drop tables in both schema
        cursor=connection.cursor()
        instance.drop(cursor, BorgConfiguration.TRANSFORM_SCHEMA)
        instance.drop(cursor, BorgConfiguration.TEST_TRANSFORM_SCHEMA)

    @staticmethod
    @receiver(pre_save, sender=Normalise)
    def _pre_save(sender, instance, **args):
        if not instance.save_signal_guard():
            return
        #import ipdb;ipdb.set_trace()
        #save relationship first
        instance._del_relations = []
        cursor=connection.cursor()
        #break the relationship between normalise and normalise_normaltable
        pos = 0
        for relation in instance.relations:
            if relation.is_empty:
                if relation.pk:
                    instance._del_relations.append(relation)
                instance.set_relation(pos, None)
            pos += 1

        #save the relationship row
        pos = 0
        for relation in instance.relations:
            if relation:
                relation.save()
                instance.set_relation(pos,relation)
            pos += 1

    @staticmethod
    @receiver(post_save, sender=Normalise)
    def _post_save(sender, instance, **args):
        #import ipdb;ipdb.set_trace()
        if not instance.save_signal_enabled():
            return

        #save normal table's foreign key
        save = False
        try:
            save = instance.normaltable != instance.normal_table
        except ObjectDoesNotExist:
            save = True

        #delete the empty relations
        if hasattr(instance,"_del_relations"):
            for relation in instance._del_relations:
                relation.delete()
            delattr(instance,"_del_relations")

        if save:
            try:
                old_normal_table = instance.normaltable
            except ObjectDoesNotExist:
                old_normal_table = None
            if old_normal_table:
                old_normal_table.normalise = None
                old_normal_table.save()

            if instance.normal_table:
                instance.normal_table.normalise = instance
                instance.normal_table.save()

        for relation in instance.relations:
            if relation and not relation.normalise:
                relation.normalise = instance
                relation.save()

class NormalTable(BorgModel,SignalEnable):
    """
    Represents a table in the harvest DB generated by a Normalise operation on
    an Input table, with associated constraints.
    """
    name = models.CharField(unique=True, max_length=255, validators=[validate_slug])
    normalise = models.OneToOneField(Normalise,null=True,editable=False)
    create_sql = SQLField(default="CREATE TABLE \"{{self.name}}\" (name varchar(32) unique);")
    last_modify_time = models.DateTimeField(auto_now=False,auto_now_add=True,editable=False,default=timezone.now,null=False)

    def is_up_to_date(self,job=None,enforce=False):
        """
        Returns True if up to date;otherwise return False
        """
        #import ipdb;ipdb.set_trace()
        if self.normalise:
            return self.normalise.is_up_to_date(job,enforce)
        else:
            return False

    @property
    def job_run_time(self):
        """
        return the last job's run time
        """
        if self.normalise:
            return self.normalise.job_run_time
        else:
            return None

    def drop(self, cursor,schema):
        """
        Drop the table from specified schema
        """
        cursor.execute("DROP TABLE IF EXISTS \"{0}\".\"{1}\" CASCADE;".format(schema,self.name))

    @switch_searchpath()
    def create(self, cursor,schema):
        """
        Create the table in specified schema
        """
        sql = Template(self.create_sql)
        sql = sql.render(Context({"self": self,"schema":schema}))
        cursor.execute(sql)

    @in_schema(BorgConfiguration.TEST_NORMAL_SCHEMA)
    def clean(self, cursor,schema):
        """
        check whether the NormalTable is correct, by recreating it in test schema
        """
        self.create_sql = None if not self.create_sql else self.create_sql.strip()
        if not self.create_sql:
            raise ValidationError("Create sql can't be empty.")

        #check whether create sql is ascii string
        try:
            self.create_sql = codecs.encode(self.create_sql,'ascii')
        except :
            raise ValidationError("Create sql contains non ascii character.")

        orig = None
        if self.pk:
            orig = NormalTable.objects.get(pk=self.pk)

        if orig and orig.create_sql == self.create_sql:
            #create_sql not changed, no need to do the validation.
            return

        self.last_modify_time = timezone.now()

        self.drop(cursor,schema)
        try:
            self.create(cursor,schema)
            self.drop(cursor,schema)
        except ValidationError as e:
            raise e
        except Exception as e:
            raise ValidationError(e)

    def delete(self,using=None):
        logger.info('Delete {0}:{1}'.format(type(self),self.name))
        if try_set_push_owner("normal_table"):
            try:
                with transaction.atomic():
                    super(NormalTable,self).delete(using)
                try_push_to_repository('normal_table')
            finally:
                try_clear_push_owner("normal_table")
        else:
            super(NormalTable,self).delete(using)

    def save(self, force_insert=False, force_update=False, using=None, update_fields=None):
        with transaction.atomic():
            super(NormalTable,self).save(force_insert,force_update,using,update_fields)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['name']

class NormalTableEventListener(object):
    @staticmethod
    @receiver(pre_delete, sender=NormalTable)
    def _pre_delete(sender, instance, **args):
        # import ipdb;ipdb.set_trace()
        # drop tables in both schema
        cursor=connection.cursor()
        instance.drop(cursor, BorgConfiguration.NORMAL_SCHEMA)
        instance.drop(cursor, BorgConfiguration.TEST_NORMAL_SCHEMA)

class Normalise_NormalTable(BorgModel):
    """
    Analogous a many to many relationship between Normalise and NormalTable
    """
    normalise = models.ForeignKey(Normalise,blank=True,null=True)
    normal_table_1 = models.ForeignKey(NormalTable,blank=True,null=True,related_name="normalise_normaltable_1")
    normal_table_2 = models.ForeignKey(NormalTable,blank=True,null=True,related_name="normalise_normaltable_2")
    normal_table_3 = models.ForeignKey(NormalTable,blank=True,null=True,related_name="normalise_normaltable_3")
    normal_table_4 = models.ForeignKey(NormalTable,blank=True,null=True,related_name="normalise_normaltable_4")

    @property
    def normal_tables(self):
        return [self.normal_table_1,self.normal_table_2,self.normal_table_3,self.normal_table_4]

    def set_normal_table(self,pos,normal_table):
        """
        set the normal_table at position pos, position is based 0
        """
        if pos == 0:
            self.normal_table_1 = normal_table
        elif pos == 1:
            self.normal_table_2 = normal_table
        elif pos == 2:
            self.normal_table_3 = normal_table
        elif pos == 3:
            self.normal_table_4 = normal_table

    @property
    def is_empty(self):
        return not any(self.normal_tables)

    def __str__(self):
        if self.normal_table_1 or self.normal_table_2 or self.normal_table_3 or self.normal_table_4:

            return "{0} depedents on [{1} {2} {3} {4}]".format(self.normalise.name if self.normalise else "",
                                                            self.normal_table_1.name if self.normal_table_1 else "",
                                                            ", " + self.normal_table_2.name if self.normal_table_2 else "",
                                                            ", " + self.normal_table_3.name if self.normal_table_3 else "",
                                                            ", " + self.normal_table_4.name if self.normal_table_4 else "",
                                                            )
        else:
            return self.normalise.name if self.normalise else ""

class PublishChannel(BorgModel,SignalEnable):
    """
    The publish channel
    """
    name = models.SlugField(max_length=255, unique=True, help_text="Name of publish destination", validators=[validate_slug])
    sync_postgres_data = models.BooleanField(default=True)
    sync_geoserver_data = models.BooleanField(default=True)
    last_modify_time = models.DateTimeField(auto_now=False,auto_now_add=True,editable=False,default=timezone.now,null=False)

    def delete(self,using=None):
        logger.info('Delete {0}:{1}'.format(type(self),self.name))
        if try_set_push_owner("publish_channel"):
            try:
                with transaction.atomic():
                    super(PublishChannel,self).delete(using)
                try_push_to_repository('publish_channel')
            finally:
                try_clear_push_owner("publish_channel")
        else:
            super(PublishChannel,self).delete(using)

    def clean(self):
        orig = None
        if self.pk:
            orig = PublishChannel.objects.get(pk=self.pk)

        if (not orig or
            orig.sync_postgres_data != self.sync_postgres_data or
            orig.sync_geoserver_data != self.sync_geoserver_data):
            self.last_modify_time = timezone.now()


    def save(self, force_insert=False, force_update=False, using=None, update_fields=None):
        with transaction.atomic():
            super(PublishChannel,self).save(force_insert,force_update,using,update_fields)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['name']

@python_2_unicode_compatible
class Workspace(BorgModel,SignalEnable):
    """
    Analogous to a workspace in GeoServer.
    """
    name = models.SlugField(max_length=255, help_text="Name of workspace", validators=[validate_slug])
    publish_channel = models.ForeignKey(PublishChannel)

    AUTH_CHOICES = (
        (0, 'Public access'),
        (1, 'SSO access'),
        (2, 'SSO restricted role access')
    )
    auth_level = models.PositiveSmallIntegerField(choices=AUTH_CHOICES, default=1)

    default_schema = BorgConfiguration.PUBLISH_SCHEMA
    default_view_schema = BorgConfiguration.PUBLISH_VIEW_SCHEMA

    @property
    def workspace_as_schema(self):
        return BorgConfiguration.WORKSPACE_AS_SCHEMA

    @property
    def schema(self):
        if self.workspace_as_schema:
            return '{0}_{1}'.format(self.publish_channel.name,self.name)
        else:
            return '{0}_{1}'.format(self.publish_channel.name,self.default_schema)

    @property
    def publish_schema(self):
        """
        The schema used by borg slave to let user access the table
        """
        if self.workspace_as_schema:
            return self.name
        else:
            return self.default_schema

    @property
    def publish_data_schema(self):
        """
        The schema used by borg slave to save the table data.
        """
        return "{0}_data".format(self.publish_schema)

    @property
    def publish_outdated_schema(self):
        """
        The schema used by borg slave to temporary save the outdated table data
        """
        return "{0}_outdated".format(self.publish_schema)

    @property
    def view_schema(self):
        if self.workspace_as_schema:
            return '{0}_{1}_view'.format(self.publish_channel.name,self.name)
        else:
            return '{0}_{1}'.format(self.publish_channel.name,self.default_view_schema)

    @property
    def test_schema(self):
        return BorgConfiguration.test_schema(self.schema)

    @property
    def test_view_schema(self):
        return BorgConfiguration.test_schema(self.view_schema)

    @in_schema(BorgConfiguration.BORG_SCHEMA)
    def execute(self,validation_mode,cursor,schema):
        if validation_mode:
            sql = ";".join(["CREATE SCHEMA IF NOT EXISTS \"{}\"".format(s) for s in [self.test_schema,self.test_view_schema]])
        else:
            sql = ";".join(["CREATE SCHEMA IF NOT EXISTS \"{}\"".format(s) for s in [self.schema,self.view_schema,self.publish_data_schema]])

        cursor.execute(sql)

    def delete(self,using=None):
        logger.info('Delete {0}:{1}'.format(type(self),self.name))
        if try_set_push_owner("workspace"):
            try:
                with transaction.atomic():
                    super(Workspace,self).delete(using)
                try_push_to_repository('workspace')
            finally:
                try_clear_push_owner("workspace")
        else:
            super(Workspace,self).delete(using)

    def save(self, force_insert=False, force_update=False, using=None, update_fields=None):
        with transaction.atomic():
            super(Workspace,self).save(force_insert,force_update,using,update_fields)

    def __str__(self):
        return '{0}.{1}'.format(self.publish_channel.name,self.name)

    class Meta:
        ordering = ['publish_channel','name']
        unique_together=(('publish_channel','name'),)

class WorkspaceEventListener(object):
    @staticmethod
    @receiver(post_delete, sender=Workspace)
    def _post_delete(sender, instance, **args):
        refresh_select_choices.send(instance,choice_family="workspace")

    @staticmethod
    @receiver(pre_save, sender=Workspace)
    def _pre_save(sender, instance,**kwargs):
        if not instance.pk:
            instance.new_object = True

    @staticmethod
    @receiver(post_save, sender=Workspace)
    def _post_save(sender, instance, **args):
        if (hasattr(instance,"new_object") and getattr(instance,"new_object")):
            delattr(instance,"new_object")
            refresh_select_choices.send(instance,choice_family="workspace")

STATUS_CHOICES = (
    (0, "idle"),
    (1, "harvesting"),
    (2, "harvested"),
    (3, "failed")
)

def get_full_data_file_name(instance,filename):
    if instance.workspace.workspace_as_schema:
        return 'full_data/{0}/{1}/{2}/{3}'.format(instance.workspace.publish_channel.name,instance.workspace.name,instance.job_batch_id,filename)
    else:
        return 'full_data/{0}/{1}/{2}'.format(instance.workspace.publish_channel.name,instance.job_batch_id,filename)

class Publish(Transform,SignalEnable):
    """
    Represents an operation to publish parts of an Input table in the harvest
    DB as a view.
    """
    TRANSFORM = [
        "CREATE FUNCTION \"{{trans_schema}}\".\"{{self.func_name}}\"() RETURNS SETOF \"{{input_table_schema}}\".\"{{input_table_name}}\" as ",
        "\nBEGIN\n    RETURN QUERY SELECT * FROM \"{{input_table_schema}}\".\"{{input_table_name}}\";\nEND;\n",
        " LANGUAGE plpgsql;"
    ]

    name = models.SlugField(max_length=255, unique=True, help_text="Name of Publish", validators=[validate_slug])
    workspace = models.ForeignKey(Workspace)
    interval = models.CharField(max_length=64, choices=JobInterval.publish_options(), default=Weekly.instance().name)
    status = models.CharField(max_length=32, choices=PublishStatus.all_options(),default=EnabledStatus.instance().name)
    kmi_title = models.CharField(max_length=512,null=True,editable=True,blank=True)
    kmi_abstract = models.TextField(null=True,editable=True,blank=True)
    input_table = models.ForeignKey(Input, blank=True,null=True) # Referencing the schema which to introspect for the output of this transform
    sql = SQLField(default="$$".join(TRANSFORM).strip())
    spatial_type = models.IntegerField(default=1,editable=False)
    create_extra_index_sql = SQLField(null=True, editable=True,blank=True)
    priority = models.PositiveIntegerField(default=1000)
    sld = XMLField(help_text="Styled Layer Descriptor", unique=False,blank=True,null=True)
    pgdump_file = models.FileField(upload_to=get_full_data_file_name,storage=downloadFileSystemStorage,null=True,editable=False)
    style_file = models.FileField(upload_to=get_full_data_file_name,storage=downloadFileSystemStorage,null=True,editable=False)
    create_table_sql = SQLField(null=True, editable=False)
    applications = models.TextField(blank=True,null=True,editable=False)
    geoserver_setting = models.TextField(blank=True,null=True,editable=False)
    pending_actions = models.IntegerField(blank=True,null=True,editable=False)

    relation_1 = models.OneToOneField('Publish_NormalTable',blank=True,null=True,related_name="publish_1",editable=False)
    relation_2 = models.OneToOneField('Publish_NormalTable',blank=True,null=True,related_name="publish_2",editable=False)
    relation_3 = models.OneToOneField('Publish_NormalTable',blank=True,null=True,related_name="publish_3",editable=False)

    running = models.PositiveIntegerField(default=0,editable=False)
    completed = models.PositiveIntegerField(default=0,editable=False)
    failed = models.PositiveIntegerField(default=0,editable=False)
    waiting = models.PositiveIntegerField(default=0,editable=False)

    job_create_time = models.DateTimeField(null=True, editable=False)
    job_start_time = models.DateTimeField(null=True, editable=False)
    job_end_time = models.DateTimeField(null=True, editable=False)

    default_layer_setting = {}

    _style_re = re.compile("<se:Name>(?P<layer>.*?)</se:Name>")
    _property_re = re.compile("<ogc:PropertyName>(?P<property>.*?)</ogc:PropertyName>")

    @property
    def publish_status(self):
        return PublishStatus.get_status(self.status)

    def init_relations(self):
        """
        initialize relations
        if relations is None, create a empty one
        """
        if self.relation_1 is None:
            self.relation_1 = Publish_NormalTable()

        if self.relation_2 is None:
            self.relation_2 = Publish_NormalTable()

        if self.relation_3 is None:
            self.relation_3 = Publish_NormalTable()

    def set_relation(self,pos,relation):
        """
        set the relation at position, position is based 0
        """
        if pos == 0:
            self.relation_1 = relation
        elif pos == 1:
            self.relation_2 = relation
        elif pos == 2:
            self.relation_3 = relation

    @property
    def feature_style(self):
        """
        This implementation based on a assumption: publish is derived from only one geospatial table, and also if publish has a input table, publish will try to use the same style as the input table.
        """
        if not self.workspace.publish_channel.sync_geoserver_data:
            #no need to update geoserver
            return None

        if SpatialTable.check_normal(self.spatial_type):
            #is a normal table, no style file
            return None

        sld = None
        style_file = None
        if self.sld and self.sld.strip():
            #has customized sld
            sld = self.sld
        elif self.input_table and self.input_table.spatial_type == self.spatial_type  and self.input_table.style_file:
            #publish's input_table has style file, use it
            style_file = self.input_table.style_file

        if not sld and style_file:
            #find the style file, copy it
            with open(style_file,"rb") as f:
                sld = f.read()

        if sld:
            _style_re = re.compile("<se:Name>(?P<layer>.*?)</se:Name>")
            #do some transformation.
            sld = self._style_re.sub("<se:Name>{}</se:Name>".format(self.table_name),sld,2)
            sld = self._property_re.sub((lambda m: "<ogc:PropertyName>{}</ogc:PropertyName>".format(m.group(1).lower())), sld)

        return sld

    @property
    def relations(self):
        return [self.relation_1,self.relation_2,self.relation_3]

    @property
    def publish_status(self):
        return PublishStatus.get_status(self.status)

    @property
    def func_name(self):
        return "p_{0}".format(self.table_name)

    @property
    def table_name(self):
        if self.workspace.workspace_as_schema:
            return self.name
        else:
            return "{}_{}".format(self.workspace, self.name)

    @property
    def normalises(self):
        """
        the sorted related normalises
        """
        if not hasattr(self,"_normalises_cache"):
            normalises = []
            for relation in self.relations:
                if not relation:
                    continue
                for normal_table in relation.normal_tables:
                    if not normal_table:
                        continue
                    try:
                        if not normal_table.normalise:
                            raise ValidationError("NormalTable({0}) does not connect to a normalise function.".format(normal_table.name))
                    except ObjectDoesNotExist:
                        raise ValidationError("NormalTable({0}) does not connect to a normalise function.".format(normal_table.name))

                    for n in normal_table.normalise.normalises:
                        if n not in normalises:
                            normalises.append(n)

            self._normalises_cache = normalises
        return self._normalises_cache

    @property
    def inputs(self):
        """
        a set object contains all related inputs.
        """
        #import ipdb;ipdb.set_trace()
        if not hasattr(self,"_inputs_cache"):
            inputs = []
            try:
                if self.input_table:
                    inputs.append(self.input_table)
            except ObjectDoesNotExist:
                pass

            for n in self.normalises:
                if not n.input_table:
                    raise ValidationError("Normalise({0}) does not connect to a input table.".format(self.name))
                if n.input_table not in inputs:
                    inputs.append(n.input_table)

            self._inputs_cache = inputs

        return self._inputs_cache

    def drop(self,cursor,transform_schema,publish_schema):
        """
        drop related tables and transform functions
        """
        cursor.execute("DROP TABLE IF EXISTS \"{0}\".\"{1}\" CASCADE;".format(publish_schema,self.table_name))
        super(Publish,self).drop(cursor,transform_schema)

    def invoke(self, cursor,trans_schema,normal_schema,publish_view_schema,publish_schema):
        """
        invoke the function to populate the table data in speicifed schema
        """
        #import ipdb; ipdb.set_trace()
        #drop auto generated spatial index
        #SpatialTable.get_instance(cursor,publish_schema,self.table_name,True).drop_indexes(cursor)
        #drop all indexes except primary key
        #DbUtil.drop_all_indexes(publish_schema,self.table_name,False)

        sql = "CREATE OR REPLACE VIEW \"{3}\".\"{0}\" AS SELECT *, md5(CAST(row.* AS text)) as md5_rowhash FROM \"{2}\".\"{1}\"() as row;".format(self.table_name,self.func_name,trans_schema,publish_view_schema)
        cursor.execute(sql)
        sql = (
            "DROP TABLE IF EXISTS \"{4}\".\"{0}\" CASCADE;\n"
            #"CREATE TABLE IF NOT EXISTS \"{4}\".\"{0}\" (LIKE \"{3}\".\"{0}\",\n"
            "CREATE TABLE \"{4}\".\"{0}\" (LIKE \"{3}\".\"{0}\",\n"
            "CONSTRAINT pk_{0} PRIMARY KEY (md5_rowhash));\n"
            #"CREATE TABLE IF NOT EXISTS \"{0}_diff\" (\n"
            #"difftime TIMESTAMP PRIMARY KEY\n,"
            #"inserts VARCHAR(32)[], deletes VARCHAR(32)[]);\n"
            #"INSERT INTO \"{0}_diff\" select now() as difftime, del.array_agg as deletes, ins.array_agg as inserts from\n"
            #"(select array_agg(d.md5_rowhash) from (select md5_rowhash from \"{0}\" except (select md5_rowhash from publish_view.\"{0}\")) as d) as del,\n"
            #"(select array_agg(i.md5_rowhash) from (select md5_rowhash from publish_view.\"{0}\" except (select md5_rowhash from \"{0}\")) as i) as ins;\n"
            #"TRUNCATE \"{4}\".\"{0}\";" # For now don't actually use diff just truncate/full reinsert
            "INSERT INTO \"{4}\".\"{0}\" SELECT * FROM \"{3}\".\"{0}\";"
            ).format(self.table_name, timezone.now(),trans_schema,publish_view_schema,publish_schema)
        cursor.execute(sql)

        #create extra index
        if self.create_extra_index_sql and self.create_extra_index_sql.strip():
            sql = Template(self.create_extra_index_sql).render(Context({"self": self,"publish_schema":publish_schema}))
            cursor.execute(sql)

        #create index
        SpatialTable.get_instance(cursor,publish_schema,self.table_name,True).create_indexes(cursor)


    def _create(self, cursor,schema,input_schema=None,normal_schema=None):
        """
        This function is used to take care two different scenario:
        1. when the publish dependent on an input_table.
        2. when the publish does not dependent on an input table
        """
        if self.input_table:
            self.create(cursor,schema,input_schema,normal_schema,input_schema,self.input_table.name)
        else:
            first_normal_table = None
            for relation in self.relations:
                if relation:
                    for normal_table in relation.normal_tables:
                        if normal_table:
                            first_normal_table = normal_table
                            break;
                    if first_normal_table:
                        break;
            if first_normal_table:
                self.create(cursor,schema,input_schema,normal_schema,normal_schema,first_normal_table.name)
            else:
                raise ValidationError("Must specify input or dependencies or both.")

    @in_schema(BorgConfiguration.TEST_TRANSFORM_SCHEMA + "," + BorgConfiguration.BORG_SCHEMA,input_schema=BorgConfiguration.TEST_INPUT_SCHEMA, normal_schema=BorgConfiguration.TEST_NORMAL_SCHEMA)
    def clean(self,cursor,schema,input_schema,normal_schema):
        """
        Check whether the publish function is correct, by creating in test schema
        """
        self.sql = None if not self.sql else self.sql.strip()
        if not self.sql :
            raise ValidationError("Sql can't be empty.")

        #check whether sql is ascii string
        try:
            self.sql = codecs.encode(self.sql,'ascii')
        except :
            raise ValidationError("Sql contains non ascii character.")

        self.create_extra_index_sql = None if not self.create_extra_index_sql else self.create_extra_index_sql.strip()
        if self.create_extra_index_sql:
            try:
                self.create_extra_index_sql = codecs.encode(self.create_extra_index_sql,'ascii')
            except :
                raise ValidationError("Sql contains non ascii character.")
        else:
            self.create_extra_index_sql = None

        if not self.input_table and not any(self.relations):
            raise ValidationError("Must specify input or dependencies or both.")

        try:
            #drop transform functions, but not drop related tables
            super(Publish,self).drop(cursor,schema)
            self.last_modify_time = timezone.now()
            self._create(cursor,schema,input_schema,normal_schema)

            self.workspace.execute(True)

            #invoke the normalise function to check whether it is correct or not.
            self.invoke(cursor,schema,normal_schema,self.workspace.test_view_schema,self.workspace.test_schema)

            self.create_table_sql = DbUtil.get_create_table_sql(self.workspace.test_schema,self.table_name)

            #check the table is spatial or non spatial
            self.spatial_type = SpatialTable.get_instance(cursor,self.workspace.test_schema,self.table_name,True).spatial_type

            orig = None
            if self.pk:
                orig = Publish.objects.get(pk=self.pk)

            if orig and orig.status != self.status:
                #publish status changed.
                if (not self.publish_status.publish_enabled) and (orig.publish_status.publish_enabled):
                    #from publish enabled to publish disabled.
                    try:
                        self.remove_publish_from_repository()
                    except:
                        error = sys.exc_info()
                        raise ValidationError(traceback.format_exception_only(error[0],error[1]))

                    self.job_id = None
                    self.job_batch_id = None
                    self.job_status = None
        except ValidationError as e:
            raise e
        except Exception as e:
            raise ValidationError(e)

    def remove_publish_from_repository(self):
        """
         remove layer's json reference (if exists) from the state repository,
         so that slave nodes will remove the layer/table from their index
         return True if layres is removed for repository; return false, if layers does not existed in repository.
        """
        #get all possible files
        files =[self.output_filename_abs(action) for action in ['publish','meta','empty_gwc'] ]
        #get all existing files.
        files =[ f for f in files if os.path.exists(f)]
        if files:
            #file exists, layers is published, remove it.
            try_set_push_owner("remove_publish")
            hg = None
            try:
                hg = hglib.open(BorgConfiguration.BORG_STATE_REPOSITORY)
                hg.remove(files=files)
                hg.commit(include=files,addremove=True, user="borgcollector", message="Removed {}.{}".format(self.workspace.name, self.name))
                increase_committed_changes()

                try_push_to_repository("remove_publish",hg)
            finally:
                if hg: hg.close()
                try_clear_push_owner("remove_publish")
            return True
        else:
            return False

    @switch_searchpath(searchpath=BorgConfiguration.BORG_SCHEMA)
    def _post_execute(self,cursor):
        self.save(update_fields=['job_run_time'])

    @in_schema(BorgConfiguration.TRANSFORM_SCHEMA + "," + BorgConfiguration.BORG_SCHEMA,input_schema=BorgConfiguration.INPUT_SCHEMA, normal_schema=BorgConfiguration.NORMAL_SCHEMA)
    def execute(self,cursor,schema,input_schema,normal_schema):
        """
        recreate the function;
        recreate the latest data view
        publish the data
        """
        #drop transform functions, but not drop related tables
        begin_time = timezone.now()
        super(Publish,self).drop(cursor,schema)
        self._create(cursor,schema,input_schema,normal_schema)
        self.workspace.execute(False)
        self.invoke(cursor,schema,normal_schema,self.workspace.view_schema,self.workspace.schema)
        self.job_run_time = begin_time
        self._post_execute(cursor)

    def publish_meta_data(self):
        from application.models import Application_Layers
        publish_action = PublishAction(self.pending_actions)
        if self.status != EnabledStatus.instance().name:
            raise ValidationError("The publish({0}) is disabled".format(self.name))

        if not self.workspace.publish_channel.sync_geoserver_data:
            raise ValidationError("The publish channel({1}) of publish({0}) does not support geoserver.".format(self.name,self.workspace.publish_channel.name))

        if publish_action.publish_all:
            raise ValidationError("Publish({0}) requires a full publish including data and metadata".format(self.name))

        #prepare style file
        style_file = None
        sld = self.feature_style
        if sld:
            style_file_folder = None
            if self.workspace.workspace_as_schema:
                style_file_folder = os.path.join(BorgConfiguration.STYLE_FILE_DUMP_DIR,self.workspace.publish_channel.name, self.workspace.name)
            else:
                style_file_folder = os.path.join(BorgConfiguration.STYLE_FILE_DUMP_DIR,self.workspace.publish_channel.name)

            if not os.path.exists(style_file_folder):
                #dump dir does not exist, create it
                os.makedirs(style_file_folder)

            style_file = os.path.join(style_file_folder,self.table_name + ".sld")
            with open(style_file,"wb") as f:
                f.write(sld)


        try_set_push_owner("publish")
        hg = None
        try:
            hg = hglib.open(BorgConfiguration.BORG_STATE_REPOSITORY)
            json_file = self.output_filename_abs('meta')

            # Write JSON output file
            json_out = {}
            json_out["name"] = self.table_name
            json_out["workspace"] = self.workspace.name
            json_out["schema"] = self.workspace.publish_schema
            json_out["channel"] = self.workspace.publish_channel.name
            json_out["spatial_data"] = SpatialTable.check_spatial(self.spatial_type)
            json_out["sync_postgres_data"] = False
            json_out["sync_geoserver_data"] = True
            json_out["applications"] = ["{0}:{1}".format(o.application,o.order) for o in Application_Layers.objects.filter(publish=self)]
            json_out["title"] = self.title
            json_out["action"] = 'meta'
            json_out["abstract"] = self.abstract
            json_out["publish_time"] = timezone.now().strftime("%Y-%m-%d %H:%M:%S.%f")
            json_out["auth_level"] = self.workspace.auth_level

            if self.geoserver_setting:
                json_out["geoserver_setting"] = json.loads(self.geoserver_setting)
            if style_file:
                json_out["style_path"] = "{}{}".format(BorgConfiguration.MASTER_PATH_PREFIX,style_file)

            #create the dir if required
            if not os.path.exists(os.path.dirname(json_file)):
                os.makedirs(os.path.dirname(json_file))

            with open(json_file, "wb") as output:
                json.dump(json_out, output, indent=4)

            hg.commit(include=[json_file],addremove=True, user=BorgConfiguration.BORG_STATE_USER, message="Update feature's meta data {}.{}".format(self.workspace.name, self.name))

            increase_committed_changes()

            try_push_to_repository('publish',hg)

            actions = publish_action.clear_feature_action().clear_gwc_action().actions
            if self.pending_actions != actions:
                self.pending_actions = actions
                self.save(update_fields=['pending_actions'])
        finally:
            if hg: hg.close()
            try_clear_push_owner("publish")

    def empty_gwc(self):
        """
        Empty gwc to the repository
        """
        if self.publish_status not in [EnabledStatus.instance()]:
            #layer is not published, no need to empty gwc
            raise ValidationError("The publish({0}) is disabled".format(self.name))

        geo_settings = json.loads(self.geoserver_setting) if self.geoserver_setting else {}
        if not geo_settings.get("create_cache_layer",False):
            #layer does not enable gwc, no need to empty gwc
            raise ValidationError("The publish({0}) doesn't enable gwc.".format(self.name))


        json_file = self.output_filename_abs('empty_gwc');
        try_set_push_owner("publish")
        hg = None
        try:
            json_out = {}
            json_out["name"] = self.table_name
            json_out["workspace"] = self.workspace.name
            json_out["action"] = "empty_gwc"
            json_out["empty_time"] = timezone.now().strftime("%Y-%m-%d %H:%M:%S.%f")
            json_out["auth_level"] = self.workspace.auth_level

            #create the dir if required
            if not os.path.exists(os.path.dirname(json_file)):
                os.makedirs(os.path.dirname(json_file))

            with open(json_file, "wb") as output:
                json.dump(json_out, output, indent=4)
        
            hg = hglib.open(BorgConfiguration.BORG_STATE_REPOSITORY)
            hg.commit(include=[json_file],addremove=True, user="borgcollector", message="Empty GWC of publish {}.{}".format(self.workspace.name, self.name))
            increase_committed_changes()
                
            try_push_to_repository("publish",hg)
        finally:
            if hg: hg.close()
            try_clear_push_owner("publish")

    @property
    def title(self):
        return self.kmi_title if self.kmi_title else (self.input_table.title if self.input_table else "")

    @property
    def abstract(self):
        return self.kmi_abstract if self.kmi_abstract else (self.input_table.kmi_abstract if self.input_table else "")

    def output_filename(self,action='publish'):
        if action == 'publish':
            return os.path.join(self.workspace.publish_channel.name,"layers", "{}.{}.json".format(self.workspace.name, self.name))
        else:
            return os.path.join(self.workspace.publish_channel.name,"layers", "{}.{}.{}.json".format(self.workspace.name, self.name,action))

    def output_filename_abs(self,action='publish'):
        return os.path.join(BorgConfiguration.BORG_STATE_REPOSITORY, self.output_filename(action))

    def is_up_to_date(self,job=None,enforce=False):
        """
        Returns PublishAction object.
        """
        #import ipdb;ipdb.set_trace();
        if self.status != EnabledStatus.instance().name:
            return None

        publish_action = PublishAction(self.pending_actions)

        if not self.job_run_time:
            return publish_action.publish_all

        if publish_action.publish_all or publish_action.publish_data:
            return publish_action

        if self.input_table:
            up_to_date = self.input_table.is_up_to_date(job,enforce)
            if up_to_date == False:
                #input_table is not up to date
                return publish_action.column_changed("input_table")
            elif up_to_date is None:
                publish_action.possible_data_changed = True

            if self.job_run_time < self.input_table.job_run_time:
                #input table is up to date but input table's last job run after normalise's last job run.
                return publish_action.column_changed("input_table")

        for relation in self.relations:
            if relation:
                for normal_table in relation.normal_tables:
                    if normal_table:
                        up_to_date = normal_table.is_up_to_date(job,enforce)
                        if up_to_date == False:
                            #dependent normal table is not up to date
                            return publish_action.column_changed("normal_tables")
                        elif up_to_date is None:
                            publish_action.possible_data_changed = True
                        if self.job_run_time < normal_table.job_run_time:
                            #dependent normal table is up to date but its last job run after normalise's last job run.
                            return publish_action.column_changed("normal_tables")

        return publish_action

    def delete(self,using=None):
        logger.info('Delete {0}:{1}'.format(type(self),self.name))
        if try_set_push_owner("publish"):
            try:
                with transaction.atomic():
                    super(Publish,self).delete(using)
                try_push_to_repository('publish')
            finally:
                try_clear_push_owner("publish")
        else:
            super(Publish,self).delete(using)

    def save(self, force_insert=False, force_update=False, using=None, update_fields=None):
        with transaction.atomic():
            super(Publish,self).save(force_insert,force_update,using,update_fields)

    def __str__(self):
        if self.workspace.workspace_as_schema:
            return "{}.{}".format(self.workspace, self.name)
        else:
            return "{}_{}".format(self.workspace, self.name)

    class Meta(Transform.Meta):
        unique_together = [['workspace','name']]
        ordering = ["workspace","name"]

class PublishEventListener(object):
    @staticmethod
    @receiver(pre_delete, sender=Publish)
    def _pre_delete(sender, instance, **args):
        #import ipdb;ipdb.set_trace()
        # drop tables in both schema
        if instance.waiting + instance.running > 0:
            raise Exception("Can not delete publish which has some waiting or running jobs.")
        cursor=connection.cursor()
        instance.drop(cursor, BorgConfiguration.TRANSFORM_SCHEMA,instance.workspace.schema)
        instance.drop(cursor, BorgConfiguration.TEST_TRANSFORM_SCHEMA,instance.workspace.test_schema)

        instance.remove_publish_from_repository()

    @staticmethod
    @receiver(post_delete, sender=Publish)
    def _post_delete(sender, instance, **args):
        refresh_select_choices.send(instance,choice_family="publish")

    @staticmethod
    @receiver(pre_save, sender=Publish)
    def _pre_save(sender, instance, **args):
        if not instance.pk:
            instance.new_object = True

        if not instance.save_signal_guard():
            return

        instance.pending_actions = PublishAction().edit(instance).actions

        #save relationship first
        instance._del_relations = []
        #break the relationship between publish and publish_normaltable
        pos = 0
        for relation in instance.relations:
            if relation.is_empty:
                if relation.pk:
                    instance._del_relations.append(relation)
                instance.set_relation(pos, None)
            pos += 1

        #save the relationship row
        pos = 0
        for relation in instance.relations:
            if relation:
                relation.save()
                instance.set_relation(pos,relation)
            pos += 1

    @staticmethod
    @receiver(post_save, sender=Publish)
    def _post_save(sender, instance, **args):
        if (hasattr(instance,"new_object") and getattr(instance,"new_object")):
            delattr(instance,"new_object")
            refresh_select_choices.send(instance,choice_family="publish")

        #import ipdb;ipdb.set_trace()
        if not instance.save_signal_enabled():
            return

        #delete the empty relations
        if hasattr(instance,"_del_relations"):
            for relation in instance._del_relations:
                relation.delete()
            delattr(instance,"_del_relations")

        for relation in instance.relations:
            if relation and not relation.publish:
                relation.publish = instance
                relation.save()

class Publish_NormalTable(BorgModel):
    """
    Analogous a many to many relationship between Publish and NormalTable
    """
    publish = models.ForeignKey(Publish,blank=True,null=True)
    normal_table_1 = models.ForeignKey(NormalTable,blank=True,null=True,related_name="publish_normaltable_1")
    normal_table_2 = models.ForeignKey(NormalTable,blank=True,null=True,related_name="publish_normaltable_2")
    normal_table_3 = models.ForeignKey(NormalTable,blank=True,null=True,related_name="publish_normaltable_3")
    normal_table_4 = models.ForeignKey(NormalTable,blank=True,null=True,related_name="publish_normaltable_4")

    @property
    def normal_tables(self):
        return [self.normal_table_1,self.normal_table_2,self.normal_table_3,self.normal_table_4]

    def set_normal_table(self,pos,normal_table):
        """
        set the normal_table at position pos, position is based 0
        """
        if pos == 0:
            self.normal_table_1 = normal_table
        elif pos == 1:
            self.normal_table_2 = normal_table
        elif pos == 2:
            self.normal_table_3 = normal_table
        elif pos == 3:
            self.normal_table_4 = normal_table

    @property
    def is_empty(self):
        return not any(self.normal_tables)

    def __nonzero__(self):
        return any(self.normal_tables)

    def __str__(self):
        if self.normal_table_1 or self.normal_table_2 or self.normal_table_3 or self.normal_table_4:
            return "{0} depedents on {1} {2} {3} {4}".format(self.publish.name if self.publish else "",
                                                            self.normal_table_1.name if self.normal_table_1 else "",
                                                            ", " + self.normal_table_2.name if self.normal_table_2 else "",
                                                            ", " + self.normal_table_3.name if self.normal_table_3 else "",
                                                            ", " + self.normal_table_4.name if self.normal_table_4 else "",
                                                            )
        else:
            return self.publish.name if self.publish else ""

class Replica(models.Model):
    """
    Represents a remote PostgreSQL server which will be seeded with data
    from the Publish objects.
    """
    active = models.BooleanField(default=True)
    namespace = models.BooleanField(default=True, help_text="Use schemas to namespace replicated tables, if not will use a prefix")
    name = models.CharField(max_length=255, validators=[validate_slug])
    includes = models.ManyToManyField(Publish, blank=True, help_text="Published tables to include, all if blank")
    link = models.TextField(default="CREATE SERVER {{self.name}} FOREIGN DATA WRAPPER postgres_fdw OPTIONS (dbserver '//<hostname>/<sid>');")

