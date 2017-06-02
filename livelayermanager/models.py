from __future__ import unicode_literals
import re
import json
import logging
import shutil
import os
import hglib
from datetime import datetime
import requests

from django.conf import settings
from django.db import models
from django.contrib.postgres.fields import HStoreField
from django.utils import timezone
from django.core.validators import RegexValidator
from django.dispatch import receiver
from django.db.models.signals import pre_save, pre_delete,post_save,post_delete
from django.db import transaction
from django.core.exceptions import ValidationError

from tablemanager.models import Workspace
from borg_utils.borg_config import BorgConfiguration
from borg_utils.resource_status import ResourceStatus,ResourceStatusMixin,ResourceAction
from borg_utils.transaction import TransactionMixin
from borg_utils.db_util import DbUtil
from borg_utils.spatial_table import SpatialTable
from borg_utils.signals import inherit_support_receiver
from borg_utils.models import BorgModel,SQLField
from borg_utils.utils import file_md5
from borg_utils.hg_batch_push import try_set_push_owner, try_clear_push_owner, increase_committed_changes, try_push_to_repository

logger = logging.getLogger(__name__)

slug_re = re.compile(r'^[a-z_][a-z0-9_]+$')
validate_slug = RegexValidator(slug_re, "Slug can only start with lowercase letters or underscore, and contain lowercase letters, numbers and underscore", "invalid")

default_layer_geoserver_setting = { 
                   "create_cache_layer": True,
                   "client_cache_expire": 0, 
                   "meta_tiling_factor": [1, 1], 
                   "server_cache_expire": 0, 
                   "gridsets": {
                       "EPSG:3857": {
                            "enabled": True
                        }, 
                        "internal.fms.wa.gov.au/apps/sss": {
                            "enabled": True}
                        }, 
}
default_layer_geoserver_setting_json = json.dumps(default_layer_geoserver_setting)

# Create your models here.
class Datasource(BorgModel,ResourceStatusMixin,TransactionMixin):
    name = models.SlugField(max_length=64,null=False,blank=False,editable=True,unique=True, help_text="The name of live layer datasource", validators=[validate_slug])
    workspace = models.ForeignKey(Workspace, null=False,blank=False)
    host = models.CharField(max_length=128,null=False,blank=False)
    port = models.PositiveIntegerField(blank=False,default=5432)
    db_name = models.CharField(max_length=64,null=False,blank=False,editable=True, help_text="The name of live layer database")
    user = models.CharField(max_length=32,null=True,blank=True)
    password = models.CharField(max_length=32,null=True,blank=True)
    schema = models.CharField(max_length=32,blank=False,default="public")
    filter = models.CharField(max_length=32,blank=True,null=True)
    geoserver_setting = models.TextField(blank=True,null=True,editable=False)
    status = models.CharField(max_length=32,null=False,editable=False,choices=ResourceStatus.layer_status_options)

    layers = models.PositiveIntegerField(null=False,editable=False,default=0)

    last_refresh_time = models.DateTimeField(null=True,editable=False)
    last_publish_time = models.DateTimeField(null=True,editable=False)
    last_unpublish_time = models.DateTimeField(null=True,editable=False)
    last_modify_time = models.DateTimeField(null=False,editable=False,default=timezone.now)

    _filters = None

    def clean(self):
        if not self.pk:
            self.status = ResourceStatus.New.name
        else:
            #already exist
            self.status = self.next_status(ResourceAction.UPDATE)

        if self.filter:
            try:
                [re.compile(f.strip()) for f in self.filter.split(";") if f.strip()]
            except:
                raise ValidationError("Invalid filter.")
                
        self.last_modify_time = timezone.now()

    def save(self, force_insert=False, force_update=False, using=None, update_fields=None):
        try:
            if self.try_begin_transaction("datasource_save"):
                with transaction.atomic():
                    super(Datasource,self).save(force_insert,force_update,using,update_fields)
            else:
                super(Datasource,self).save(force_insert,force_update,using,update_fields)
        finally:
            self.try_clear_transaction("datasource_save")

        if (not getattr(self,"refreshed",False)
            and hasattr(self,"changed_fields") 
            and (self.changed_fields == "__all__"  or any([f in self.changed_fields for f in ["host","port","db_name","schema","user","password"]]))
            ):
            setattr(self,"refreshed",True)
            self.refresh()

    def delete(self,using=None):
        logger.info('Delete {0}:{1}'.format(type(self),self.name))
        try:
            if self.try_begin_transaction("datasource_delete"):
                with transaction.atomic():
                    super(Datasource,self).delete(using)
            else:
                super(Datasource,self).delete(using)
        finally:
            self.try_clear_transaction("datasource_delete")

    @property
    def dbUtil(self):
        dbUtil = getattr(self,"_dbUtil") if hasattr(self,"_dbUtil") else None
        if not dbUtil:
            dbUtil = DbUtil(self.db_name,self.host,self.port,self.user,self.password)
            setattr(self,"_dbUtil",dbUtil)
        return dbUtil

    def filter_table(self,table):
        if not self.filter:
            return True

        if not self._filters:
            self._filters = [re.compile(f.strip()) for f in self.filter.split(";") if f.strip()]

        return any([f.search(table) for f in self._filters])


    def refresh(self):
        self.try_begin_transaction("datasource_refresh")
        try:
            #modify the table data
            now = timezone.now()
            tables = self.dbUtil.get_all_tables(self.schema)
            views = self.dbUtil.get_all_views(self.schema)
            now = timezone.now()

        
            #refresh tables and views
            for typename, tables in [["Table", tables],["Views", views]]:
                for table_name in tables:
                    if not self.filter_table(table_name):
                        continue
                    layer, created = Layer.objects.get_or_create(datasource=self, 
                        table=table_name, 
                        defaults={
                            "type": typename, 
                            "last_refresh_time": now,
                            "geoserver_setting":default_layer_geoserver_setting_json,
                            "status":ResourceStatus.New.name
                        }
                    )
                    layer.refresh(now)
            
            Layer.objects.filter(datasource=self).exclude(last_refresh_time=now).delete()

            for viewlayer in self.sqlviewlayer_set.all():
                viewlayer.refersh(now)

            self.layers = Layer.objects.filter(datasource=self).count()
            self.last_refresh_time = now
            self.save(update_fields=["layers","last_refresh_time"])
        finally:
            self.try_clear_transaction("datasource_refresh")


    def json_filename(self,action='publish'):
        if action in ['publish','unpublish']:
            return os.path.join(self.workspace.publish_channel.name,"live_stores", "{}.{}.json".format(self.workspace.name, self.name))
        else:
            return os.path.join(self.workspace.publish_channel.name,"live_stores", "{}.{}.{}.json".format(self.workspace.name, self.name,action))

    def json_filename_abs(self,action='publish'):
        return os.path.join(BorgConfiguration.BORG_STATE_REPOSITORY, self.json_filename(action))

    def unpublish(self):
        try_set_push_owner("liveserver")
        hg = None
        try:
            meta_data = {}
            meta_data["name"] = self.name
            meta_data["schema"] = self.schema
            meta_data["workspace"] = self.workspace.name
        
            #write meta data file
            file_name = "{}.meta.json".format(self.name)
            meta_file = os.path.join(BorgConfiguration.UNPUBLISH_DIR,self.workspace.publish_channel.name,self.workspace.name,"stores",file_name)
            #create the dir if required
            if not os.path.exists(os.path.dirname(meta_file)):
                os.makedirs(os.path.dirname(meta_file))

            with open(meta_file,"wb") as output:
                json.dump(meta_data, output, indent=4)

            json_out = {}
            json_out['meta'] = {"file":"{}{}".format(BorgConfiguration.MASTER_PATH_PREFIX, meta_file),"md5":file_md5(meta_file)}
            json_out['action'] = 'remove'
            json_out["remove_time"] = timezone.localtime(timezone.now()).strftime("%Y-%m-%d %H:%M:%S.%f")
        
            json_filename = self.json_filename_abs('unpublish');
            #create the dir if required
            if not os.path.exists(os.path.dirname(json_filename)):
                os.makedirs(os.path.dirname(json_filename))

            with open(json_filename, "wb") as output:
                json.dump(json_out, output, indent=4)
        
            hg = hglib.open(BorgConfiguration.BORG_STATE_REPOSITORY)
            hg.commit(include=[json_filename],addremove=True, user="borgcollector", message="Unpublish live store {}.{}".format(self.workspace.name, self.name))
            increase_committed_changes()
                
            try_push_to_repository("liveserver",hg)
        finally:
            if hg: hg.close()
            try_clear_push_owner("liveserver")

    def publish(self):
        """
         publish store's json reference (if exists) to the repository,
        """
        try_set_push_owner("liveserver")
        hg = None
        try:
            meta_data = {}
            meta_data["name"] = self.name
            meta_data["host"] = self.host
            meta_data["port"] = self.port
            meta_data["database"] = self.db_name
            meta_data["user"] = self.user
            meta_data["passwd"] = self.password
            meta_data["schema"] = self.schema
            meta_data["workspace"] = self.workspace.name
        
            if self.geoserver_setting:
                meta_data["geoserver_setting"] = json.loads(self.geoserver_setting)

            #write meta data file
            file_name = "{}.{}.meta.json".format(self.workspace.name,self.name)
            meta_file = os.path.join(BorgConfiguration.LIVE_STORE_DIR,file_name)
            #create the dir if required
            if not os.path.exists(os.path.dirname(meta_file)):
                os.makedirs(os.path.dirname(meta_file))

            with open(meta_file,"wb") as output:
                json.dump(meta_data, output, indent=4)

            json_out = {}
            json_out['meta'] = {"file":"{}{}".format(BorgConfiguration.MASTER_PATH_PREFIX, meta_file),"md5":file_md5(meta_file)}
            json_out['action'] = 'publish'
            json_out["publish_time"] = timezone.localtime(timezone.now()).strftime("%Y-%m-%d %H:%M:%S.%f")
        
            json_filename = self.json_filename_abs('publish');
            #create the dir if required
            if not os.path.exists(os.path.dirname(json_filename)):
                os.makedirs(os.path.dirname(json_filename))

            with open(json_filename, "wb") as output:
                json.dump(json_out, output, indent=4)
        
            hg = hglib.open(BorgConfiguration.BORG_STATE_REPOSITORY)
            hg.commit(include=[json_filename],addremove=True, user="borgcollector", message="Update live store {}.{}".format(self.workspace.name, self.name))
            increase_committed_changes()
                
            try_push_to_repository("liveserver",hg)
        finally:
            if hg: hg.close()
            try_clear_push_owner("liveserver")

    def __str__(self):
        return self.name

    class Meta:
        ordering = ("name",)


class Layer(BorgModel,ResourceStatusMixin,TransactionMixin):
    table = models.SlugField(max_length=64,null=False,editable=True)
    datasource = models.ForeignKey(Datasource,editable=False,on_delete=models.CASCADE)
    type = models.CharField(max_length=8,null=False,editable=False)
    spatial_type = models.IntegerField(default=1,editable=False)
    sql = models.TextField(null=True, editable=False)
    crs = models.CharField(max_length=64,editable=False,null=True,blank=True)
    bbox = models.CharField(max_length=128,null=True,editable=False)
    kmi_bbox = models.CharField(max_length=128,null=True,blank=True,editable=True)
    name = models.CharField(max_length=256,null=True,editable=True,blank=True,unique=True)
    geoserver_setting = models.TextField(blank=True,null=True,editable=False)
    status = models.CharField(max_length=32, null=False, editable=False,choices=ResourceStatus.layer_status_options)

    last_publish_time = models.DateTimeField(null=True,editable=False)
    last_unpublish_time = models.DateTimeField(null=True,editable=False)
    last_refresh_time = models.DateTimeField(null=False,editable=False)
    last_modify_time = models.DateTimeField(null=True,editable=False)


    @staticmethod
    def is_system_table(table):
        system_table_prefixes = ("django_","auth_","reversion_","pg_")
        return any([table[0:len(prefix)] == prefix for prefix in system_table_prefixes])

    def clean(self):
        self.last_modify_time = timezone.now()
        self.status = self.next_status(ResourceAction.UPDATE)

    @property
    def kmi_name(self):
        return self.name or self.table.lower()

    def refresh(self,time=None):
        self.try_begin_transaction("livelayer_refresh")
        try:
            time = time or timezone.now()
            if Layer.is_system_table(self.table):
                return False

            st = SpatialTable.get_instance(self.datasource.schema,self.table,refresh=True,bbox=True,crs=True,dbUtil=self.datasource.dbUtil)
            self.last_refresh_time = time
            bbox = json.dumps(st.bbox)
            sql = st.get_create_table_sql()
            if not self.sql or self.sql != sql or st.crs != self.crs or st.spatial_type != self.spatial_type or bbox != self.bbox:
                self.crs = st.crs
                self.bbox = bbox
                self.spatial_type = st.spatial_type
                self.last_modify_time = time
                self.status = self.next_status(ResourceAction.UPDATE)
                self.sql = sql
            self.save()

            return True
        finally:
            self.try_clear_transaction("livelayer_refresh")

    @property
    def builtin_metadata(self):
        meta_data = {}
        meta_data["workspace"] = self.datasource.workspace.name
        meta_data["name"] = self.kmi_name
        meta_data["service_type"] = "WMS"
        if SpatialTable.check_normal(self.spatial_type) or not self.datasource.workspace.publish_channel.sync_geoserver_data:
            meta_data["service_type"] = ""
        elif SpatialTable.check_raster(self.spatial_type):
            meta_data["service_type"] = "WMS"
            meta_data["service_type_version"] = self.datasource.workspace.publish_channel.wms_version
        else:
            meta_data["service_type"] = "WFS"
            meta_data["service_type_version"] = self.datasource.workspace.publish_channel.wfs_version

        meta_data["modified"] = (self.last_modify_time or self.last_refresh_time).astimezone(timezone.get_default_timezone()).strftime("%Y-%m-%d %H:%M:%S.%f")

        #bbox
        meta_data["bounding_box"] = self.kmi_bbox or self.bbox or None
        meta_data["crs"] = self.crs or None

        #ows resource
        meta_data["ows_resource"] = {}
        if meta_data["service_type"] == "WFS" and self.datasource.workspace.publish_channel.wfs_endpoint:
            meta_data["ows_resource"]["wfs"] = True
            meta_data["ows_resource"]["wfs_version"] = self.datasource.workspace.publish_channel.wfs_version
            meta_data["ows_resource"]["wfs_endpoint"] = self.datasource.workspace.publish_channel.wfs_endpoint

        if meta_data["service_type"] in ("WFS","WMS") and self.datasource.workspace.publish_channel.wfs_endpoint:
            meta_data["ows_resource"]["wms"] = True
            meta_data["ows_resource"]["wms_version"] = self.datasource.workspace.publish_channel.wms_version
            meta_data["ows_resource"]["wms_endpoint"] = self.datasource.workspace.publish_channel.wms_endpoint

            geo_settings = json.loads(self.geoserver_setting) if self.geoserver_setting else {}
            if geo_settings.get("create_cache_layer",False) and self.datasource.workspace.publish_channel.gwc_endpoint:
                meta_data["ows_resource"]["gwc"] = True
                meta_data["ows_resource"]["gwc_endpoint"] = self.datasource.workspace.publish_channel.gwc_endpoint

        return meta_data

    def update_catalogue_service(self,md5=False,extra_datas=None):
        meta_data = self.builtin_metadata
        if extra_datas:
            meta_data.update(extra_datas)
        bbox = meta_data.get("bounding_box",None)
        crs = meta_data.get("crs",None)
        #update catalog service
        res = requests.post("{}/catalogue/api/records/?style_content=true".format(settings.CSW_URL),json=meta_data,auth=(settings.CSW_USER,settings.CSW_PASSWORD))
        if 400 <= res.status_code < 600 and res.content:
            res.reason = "{}({})".format(res.reason,res.content)
        res.raise_for_status()
        meta_data = res.json()

        #process styles
        styles = meta_data.get("styles",[])
        #filter out qml and lyr styles
        sld_styles = [s for s in meta_data.get("styles",[]) if s["format"].lower() == "sld"]
        meta_data["styles"] = {}
        style_dump_dir = BorgConfiguration.LIVE_LAYER_DIR
        if not os.path.exists(style_dump_dir):
            os.makedirs(style_dump_dir)

        for style in sld_styles:
            if style["default"]:
                #default sld file
                meta_data["default_style"] = style["name"]
            #write the style into file system
            style_file = os.path.join(style_dump_dir,"{}.{}.{}.sld".format(self.datasource.workspace.name,self.kmi_name,style["name"]))
            with open(style_file,"wb") as f:
                f.write(style["raw_content"].decode("base64"))
            if md5:
                meta_data["styles"][style["name"]] = {"file":"{}{}".format(BorgConfiguration.MASTER_PATH_PREFIX, style_file),"default":style["default"],"md5":file_md5(style_file)}
            else:
                meta_data["styles"][style["name"]] = {"file":"{}{}".format(BorgConfiguration.MASTER_PATH_PREFIX, style_file),"default":style["default"]}

        #add extra data to meta data
        meta_data["workspace"] = self.datasource.workspace.name
        meta_data["override_bbox"] = True if self.kmi_bbox else False
        meta_data["schema"] = self.datasource.schema
        meta_data["name"] = self.kmi_name
        meta_data["table"] = self.table
        meta_data["datastore"] = self.datasource.name
        meta_data["auth_level"] = self.datasource.workspace.auth_level
        meta_data["preview_path"] = "{}{}".format(BorgConfiguration.MASTER_PATH_PREFIX, BorgConfiguration.PREVIEW_DIR)
        meta_data["spatial_data"] = SpatialTable.check_spatial(self.spatial_type)
        meta_data["spatial_type"] = SpatialTable.get_spatial_type_desc(self.spatial_type)

        meta_data["channel"] = self.datasource.workspace.publish_channel.name
        meta_data["sync_geoserver_data"] = self.datasource.workspace.publish_channel.sync_geoserver_data

        if self.geoserver_setting:
            meta_data["geoserver_setting"] = json.loads(self.geoserver_setting)
                
        #bbox
        if "bounding_box" in meta_data:
            del meta_data["bounding_box"]
        meta_data["bbox"] = bbox
        meta_data["crs"] = crs

        return meta_data

    def save(self, force_insert=False, force_update=False, using=None, update_fields=None):
        try:
            if self.try_begin_transaction("livelayer_save"):
                with transaction.atomic():
                    super(Layer,self).save(force_insert,force_update,using,update_fields)
            else:
                super(Layer,self).save(force_insert,force_update,using,update_fields)
        finally:
            self.try_clear_transaction("livelayer_save")

    def delete(self,using=None):
        try:
            if self.try_begin_transaction("livelayer_delete"):
                with transaction.atomic():
                    super(Layer,self).delete(using)
            else:
                super(Layer,self).delete(using)
        finally:
            self.try_clear_transaction("livelayer_delete")

    def json_filename(self,action='publish'):
        if action in ['publish','unpublish']:
            return os.path.join(self.datasource.workspace.publish_channel.name,"live_layers", "{}.{}.json".format(self.datasource.workspace.name, self.kmi_name))
        else:
            return os.path.join(self.datasource.workspace.publish_channel.name,"live_layers", "{}.{}.{}.json".format(self.datasource.workspace.name, self.kmi_name,action))

    def json_filename_abs(self,action='publish'):
        return os.path.join(BorgConfiguration.BORG_STATE_REPOSITORY, self.json_filename(action))

    def unpublish(self):
        #use published meta file as the meta file for unpublish
        json_file = self.json_filename_abs('publish')
        if not os.path.exists(json_file):
            raise Exception("Can't find the publish json file({}) in repository.".format(self.json_filename('publish')))

        json_out = None
        with open(json_file,"r") as f:
            json_out = json.loads(f.read())

        if "meta" not in json_out or "file" not in json_out["meta"]:
            raise Exception("Can't find meta file in the publish json file({})".format(self.json_filename('publish')))

        published_meta_file = json_out["meta"]["file"][len(BorgConfiguration.MASTER_PATH_PREFIX):]
        if not os.path.exists(published_meta_file):
            raise Exception("Published meta file({}) is missing.".format(published_meta_file))

        file_name = "{}.meta.json".format(self.kmi_name)
        meta_file = os.path.join(BorgConfiguration.UNPUBLISH_DIR,self.datasource.workspace.publish_channel.name,self.datasource.workspace.name,"layers",file_name)

        if not os.path.exists(os.path.dirname(meta_file)):
            os.makedirs(os.path.dirname(meta_file))

        shutil.copyfile(published_meta_file,meta_file)

        #remove it from catalogue service
        #remove it from catalogue service
        res = requests.delete("{}/catalogue/api/records/{}:{}/".format(settings.CSW_URL,self.datasource.workspace.name,self.kmi_name),auth=(settings.CSW_USER,settings.CSW_PASSWORD))
        if res.status_code != 404:
            res.raise_for_status()

        json_filename = self.json_filename_abs('unpublish');
        try_set_push_owner("livelayer")
        hg = None
        try:
            json_out['meta'] = {"file":"{}{}".format(BorgConfiguration.MASTER_PATH_PREFIX, meta_file),"md5":file_md5(meta_file)}
            json_out['action'] = "remove"
            json_out["remove_time"] = timezone.localtime(timezone.now()).strftime("%Y-%m-%d %H:%M:%S.%f")
        
            with open(json_filename, "wb") as output:
                json.dump(json_out, output, indent=4)
        
            hg = hglib.open(BorgConfiguration.BORG_STATE_REPOSITORY)

            #remove other related json files
            json_files = [ self.json_filename_abs(action) for action in [ 'empty_gwc' ] ]
            #get all existing files.
            json_files = [ f for f in json_files if os.path.exists(f) ]
            if json_files:
                hg.remove(files=json_files)

            json_files.append(json_filename)
            hg.commit(include=json_files,addremove=True, user="borgcollector", message="unpublish live layer {}.{}".format(self.datasource.workspace.name, self.kmi_name))
            increase_committed_changes()
                
            try_push_to_repository("livelayer",hg)
        finally:
            if hg: hg.close()
            try_clear_push_owner("livelayer")

    def publish(self):
        """
         publish layer's json reference (if exists) to the repository,
        """
        json_filename = self.json_filename_abs('publish');
        try_set_push_owner("livelayer")
        hg = None
        try:
            meta_data = self.update_catalogue_service(md5=True,extra_datas={"publication_date":datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")})

            #write meta data file
            file_name = "{}.{}.meta.json".format(self.datasource.workspace.name,self.kmi_name)
            meta_file = os.path.join(BorgConfiguration.LIVE_LAYER_DIR,file_name)
            #create the dir if required
            if not os.path.exists(os.path.dirname(meta_file)):
                os.makedirs(os.path.dirname(meta_file))

            with open(meta_file,"wb") as output:
                json.dump(meta_data, output, indent=4)

            json_out = {}
            json_out['meta'] = {"file":"{}{}".format(BorgConfiguration.MASTER_PATH_PREFIX, meta_file),"md5":file_md5(meta_file)}
            json_out['action'] = "publish"
            json_out["publish_time"] = timezone.localtime(timezone.now()).strftime("%Y-%m-%d %H:%M:%S.%f")
        
            #create the dir if required
            if not os.path.exists(os.path.dirname(json_filename)):
                os.makedirs(os.path.dirname(json_filename))

            with open(json_filename, "wb") as output:
                json.dump(json_out, output, indent=4)
        
            hg = hglib.open(BorgConfiguration.BORG_STATE_REPOSITORY)

            #remove other related json files
            json_files = [ self.json_filename_abs(action) for action in [ 'empty_gwc' ] ]
            #get all existing files.
            json_files = [ f for f in json_files if os.path.exists(f) ]
            if json_files:
                hg.remove(files=json_files)

            json_files.append(json_filename)
            hg.commit(include=json_files,addremove=True, user="borgcollector", message="update live layer {}.{}".format(self.datasource.workspace.name, self.kmi_name))
            increase_committed_changes()
                
            try_push_to_repository("livelayer",hg)
        finally:
            if hg: hg.close()
            try_clear_push_owner("livelayer")

    def empty_gwc(self):
        """
        update layer's json for empty gwc to the repository
        """
        if self.publish_status.unpublished:
            #layer is not published, no need to empty gwc
            raise ValidationError("The wms layer({0}) is not published before.".format(self.kmi_name))

        json_filename = self.json_filename_abs('empty_gwc');
        try_set_push_owner("livelayer")
        hg = None
        try:
            json_out = {}
            json_out["name"] = self.kmi_name
            json_out["workspace"] = self.datasource.workspace.name
            json_out["store"] = self.datasource.name
            json_out["action"] = "empty_gwc"
            json_out["publish_time"] = timezone.localtime(timezone.now()).strftime("%Y-%m-%d %H:%M:%S.%f")

            #create the dir if required
            if not os.path.exists(os.path.dirname(json_filename)):
                os.makedirs(os.path.dirname(json_filename))

            with open(json_filename, "wb") as output:
                json.dump(json_out, output, indent=4)
        
            hg = hglib.open(BorgConfiguration.BORG_STATE_REPOSITORY)
            hg.commit(include=[json_filename],addremove=True, user="borgcollector", message="Empty GWC of live layer {}.{}".format(self.datasource.workspace.name, self.kmi_name))
            increase_committed_changes()
                
            try_push_to_repository("livelayer",hg)
        finally:
            if hg: hg.close()
            try_clear_push_owner("livelayer")

    def __str__(self):
        return self.kmi_name

    class Meta:
        unique_together = (("datasource","table"),)
        ordering = ("datasource","table")

class PublishedLayerManager(models.Manager):
    def get_queryset(self):
            return super(LayerManager, self).get_queryset().filter(status__in=ResourceStatus.published_status)

class PublishedLayer(Layer):
    objects = PublishedLayerManager
    class Meta:
        proxy = True
        verbose_name="Published layer"
        verbose_name_plural="Published layers"

class SqlViewLayer(BorgModel,ResourceStatusMixin,TransactionMixin):
    name = models.SlugField(max_length=60,null=False,blank=False,editable=True,unique=True, help_text="The name of live layer", validators=[validate_slug])
    datasource = models.ForeignKey(Datasource,editable=True,null=False,blank=False,on_delete=models.CASCADE)
    viewsql = SQLField(null=False,blank=False)
    spatial_type = models.IntegerField(default=1,editable=False)
    sql = models.TextField(null=True, editable=False)
    crs = models.CharField(max_length=64,editable=False,null=True,blank=True)
    bbox = models.CharField(max_length=128,null=True,editable=False)
    kmi_bbox = models.CharField(max_length=128,null=True,blank=True,editable=True)
    geoserver_setting = models.TextField(blank=True,null=True,editable=False)
    status = models.CharField(max_length=32, null=False, editable=False,choices=ResourceStatus.layer_status_options,default=ResourceStatus.New.name)

    last_publish_time = models.DateTimeField(null=True,editable=False)
    last_unpublish_time = models.DateTimeField(null=True,editable=False)
    last_refresh_time = models.DateTimeField(null=False,editable=False)
    last_modify_time = models.DateTimeField(null=True,editable=False)
    create_time = models.DateTimeField(auto_now=False,auto_now_add=True,editable=False,null=False)

    def clean(self):
        if not self.data_changed: return
        self.last_modify_time = timezone.now()
        self.status = self.next_status(ResourceAction.UPDATE)
        if not self.last_refresh_time:
            self.last_refresh_time = self.datasource.last_refresh_time
        st = SpatialTable.get_instance(self.datasource.schema,self.name,refresh=True,bbox=True,crs=True,dbUtil=self.datasource.dbUtil,sql=self.viewsql)
        self.crs = st.crs
        self.bbox = json.dumps(st.bbox)
        self.spatial_type = st.spatial_type
        self.sql = st.get_create_table_sql()

    def refresh(self,time=None):
        self.try_begin_transaction("livesqlviewlayer_refresh")
        try:
            time = time or timezone.now()

        
            st = SpatialTable.get_instance(self.datasource.schema,self.name,refresh=True,bbox=True,crs=True,dbUtil=self.datasource.dbUtil,sql=self.viewsql)
            self.last_refresh_time = time
            bbox = json.dumps(st.bbox)
            sql = st.get_create_table_sql()
            if not self.sql or self.sql != sql or bbox != self.bbox or st.crs != self.crs or st.spatial_type != self.spatial_type:
                self.crs = st.crs
                self.bbox = bbox
                self.spatial_type = st.spatial_type
                self.last_modify_time = time
                self.status = self.next_status(ResourceAction.UPDATE)
                self.sql = sql
            self.save()

            return True
        finally:
            self.try_clear_transaction("livesqlviewlayer_refresh")

    @property
    def kmi_name(self):
        return self.name

    @property
    def builtin_metadata(self):
        meta_data = {}
        meta_data["workspace"] = self.datasource.workspace.name
        meta_data["name"] = self.kmi_name
        meta_data["service_type"] = "WMS"
        if SpatialTable.check_normal(self.spatial_type) or not self.datasource.workspace.publish_channel.sync_geoserver_data:
            meta_data["service_type"] = ""
        elif SpatialTable.check_raster(self.spatial_type):
            meta_data["service_type"] = "WMS"
            meta_data["service_type_version"] = self.datasource.workspace.publish_channel.wms_version
        else:
            meta_data["service_type"] = "WFS"
            meta_data["service_type_version"] = self.datasource.workspace.publish_channel.wfs_version

        meta_data["modified"] = (self.last_modify_time or self.last_refresh_time).astimezone(timezone.get_default_timezone()).strftime("%Y-%m-%d %H:%M:%S.%f")

        #bbox
        meta_data["bounding_box"] = self.kmi_bbox or self.bbox or None
        meta_data["crs"] = self.crs or None

        #ows resource
        meta_data["ows_resource"] = {}
        if meta_data["service_type"] == "WFS" and self.datasource.workspace.publish_channel.wfs_endpoint:
            meta_data["ows_resource"]["wfs"] = True
            meta_data["ows_resource"]["wfs_version"] = self.datasource.workspace.publish_channel.wfs_version
            meta_data["ows_resource"]["wfs_endpoint"] = self.datasource.workspace.publish_channel.wfs_endpoint

        if meta_data["service_type"] in ("WFS","WMS") and self.datasource.workspace.publish_channel.wfs_endpoint:
            meta_data["ows_resource"]["wms"] = True
            meta_data["ows_resource"]["wms_version"] = self.datasource.workspace.publish_channel.wms_version
            meta_data["ows_resource"]["wms_endpoint"] = self.datasource.workspace.publish_channel.wms_endpoint

            geo_settings = json.loads(self.geoserver_setting) if self.geoserver_setting else {}
            if geo_settings.get("create_cache_layer",False) and self.datasource.workspace.publish_channel.gwc_endpoint:
                meta_data["ows_resource"]["gwc"] = True
                meta_data["ows_resource"]["gwc_endpoint"] = self.datasource.workspace.publish_channel.gwc_endpoint

        return meta_data

    def update_catalogue_service(self,md5=False,extra_datas=None):
        meta_data = self.builtin_metadata
        if extra_datas:
            meta_data.update(extra_datas)
        bbox = meta_data.get("bounding_box",None)
        crs = meta_data.get("crs",None)
        #update catalog service
        res = requests.post("{}/catalogue/api/records/?style_content=true".format(settings.CSW_URL),json=meta_data,auth=(settings.CSW_USER,settings.CSW_PASSWORD))
        if 400 <= res.status_code < 600 and res.content:
            res.reason = "{}({})".format(res.reason,res.content)
        res.raise_for_status()
        meta_data = res.json()

        #process styles
        styles = meta_data.get("styles",[])
        #filter out qml and lyr styles
        sld_styles = [s for s in meta_data.get("styles",[]) if s["format"].lower() == "sld"]
        meta_data["styles"] = {}
        style_dump_dir = BorgConfiguration.LIVE_LAYER_DIR
        if not os.path.exists(style_dump_dir):
            os.makedirs(style_dump_dir)

        for style in sld_styles:
            if style["default"]:
                #default sld file
                meta_data["default_style"] = style["name"]
            #write the style into file system
            style_file = os.path.join(style_dump_dir,"{}.{}.{}.sld".format(self.datasource.workspace.name,self.kmi_name,style["name"]))
            with open(style_file,"wb") as f:
                f.write(style["raw_content"].decode("base64"))
            if md5:
                meta_data["styles"][style["name"]] = {"file":"{}{}".format(BorgConfiguration.MASTER_PATH_PREFIX, style_file),"default":style["default"],"md5":file_md5(style_file)}
            else:
                meta_data["styles"][style["name"]] = {"file":"{}{}".format(BorgConfiguration.MASTER_PATH_PREFIX, style_file),"default":style["default"]}

        #add extra data to meta data
        meta_data["workspace"] = self.datasource.workspace.name
        meta_data["override_bbox"] = True if self.kmi_bbox else False
        meta_data["name"] = self.kmi_name
        meta_data["datastore"] = self.datasource.name
        meta_data["auth_level"] = self.datasource.workspace.auth_level
        meta_data["preview_path"] = "{}{}".format(BorgConfiguration.MASTER_PATH_PREFIX, BorgConfiguration.PREVIEW_DIR)
        meta_data["spatial_data"] = SpatialTable.check_spatial(self.spatial_type)
        meta_data["spatial_type"] = SpatialTable.get_spatial_type_desc(self.spatial_type)

        meta_data["channel"] = self.datasource.workspace.publish_channel.name
        meta_data["sync_geoserver_data"] = self.datasource.workspace.publish_channel.sync_geoserver_data

        if self.geoserver_setting:
            meta_data["geoserver_setting"] = json.loads(self.geoserver_setting)

        meta_data["viewsql"] = self.viewsql
                
        #bbox
        if "bounding_box" in meta_data:
            del meta_data["bounding_box"]
        meta_data["bbox"] = bbox
        meta_data["crs"] = crs

        return meta_data

    def save(self, force_insert=False, force_update=False, using=None, update_fields=None):
        try:
            if self.try_begin_transaction("livesqlviewlayer_save"):
                with transaction.atomic():
                    super(SqlViewLayer,self).save(force_insert,force_update,using,update_fields)
            else:
                super(SqlViewLayer,self).save(force_insert,force_update,using,update_fields)
        finally:
            self.try_clear_transaction("livesqlviewlayer_save")

    def delete(self,using=None):
        try:
            if self.try_begin_transaction("livesqlviewlayer_delete"):
                with transaction.atomic():
                    super(SqlViewLayer,self).delete(using)
            else:
                super(SqlViewLayer,self).delete(using)
        finally:
            self.try_clear_transaction("livesqlviewlayer_delete")

    def json_filename(self,action='publish'):
        if action in ['publish','unpublish']:
            return os.path.join(self.datasource.workspace.publish_channel.name,"live_layers", "{}.{}.json".format(self.datasource.workspace.name, self.kmi_name))
        else:
            return os.path.join(self.datasource.workspace.publish_channel.name,"live_layers", "{}.{}.{}.json".format(self.datasource.workspace.name, self.kmi_name,action))

    def json_filename_abs(self,action='publish'):
        return os.path.join(BorgConfiguration.BORG_STATE_REPOSITORY, self.json_filename(action))

    def unpublish(self):
        #use published meta file as the meta file for unpublish
        json_file = self.json_filename_abs('publish')
        if not os.path.exists(json_file):
            raise Exception("Can't find the publish json file({}) in repository.".format(self.json_filename('publish')))

        json_out = None
        with open(json_file,"r") as f:
            json_out = json.loads(f.read())

        if "meta" not in json_out or "file" not in json_out["meta"]:
            raise Exception("Can't find meta file in the publish json file({})".format(self.json_filename('publish')))

        published_meta_file = json_out["meta"]["file"][len(BorgConfiguration.MASTER_PATH_PREFIX):]
        if not os.path.exists(published_meta_file):
            raise Exception("Published meta file({}) is missing.".format(published_meta_file))

        file_name = "{}.meta.json".format(self.kmi_name)
        meta_file = os.path.join(BorgConfiguration.UNPUBLISH_DIR,self.datasource.workspace.publish_channel.name,self.datasource.workspace.name,"layers",file_name)

        if not os.path.exists(os.path.dirname(meta_file)):
            os.makedirs(os.path.dirname(meta_file))

        shutil.copyfile(published_meta_file,meta_file)

        #remove it from catalogue service
        #remove it from catalogue service
        res = requests.delete("{}/catalogue/api/records/{}:{}/".format(settings.CSW_URL,self.datasource.workspace.name,self.kmi_name),auth=(settings.CSW_USER,settings.CSW_PASSWORD))
        if res.status_code != 404:
            res.raise_for_status()

        json_filename = self.json_filename_abs('unpublish');
        try_set_push_owner("livelayer")
        hg = None
        try:
            json_out['meta'] = {"file":"{}{}".format(BorgConfiguration.MASTER_PATH_PREFIX, meta_file),"md5":file_md5(meta_file)}
            json_out['action'] = "remove"
            json_out["remove_time"] = timezone.localtime(timezone.now()).strftime("%Y-%m-%d %H:%M:%S.%f")
        
            with open(json_filename, "wb") as output:
                json.dump(json_out, output, indent=4)
        
            hg = hglib.open(BorgConfiguration.BORG_STATE_REPOSITORY)

            #remove other related json files
            json_files = [ self.json_filename_abs(action) for action in [ 'empty_gwc' ] ]
            #get all existing files.
            json_files = [ f for f in json_files if os.path.exists(f) ]
            if json_files:
                hg.remove(files=json_files)

            json_files.append(json_filename)
            hg.commit(include=json_files,addremove=True, user="borgcollector", message="unpublish live layer {}.{}".format(self.datasource.workspace.name, self.kmi_name))
            increase_committed_changes()
                
            try_push_to_repository("livelayer",hg)
        finally:
            if hg: hg.close()
            try_clear_push_owner("livelayer")

    def publish(self):
        """
         publish layer's json reference (if exists) to the repository,
        """
        import ipdb;ipdb.set_trace()
        json_filename = self.json_filename_abs('publish');
        try_set_push_owner("livesqlviewlayer")
        hg = None
        try:
            meta_data = self.update_catalogue_service(md5=True,extra_datas={"publication_date":datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")})

            #write meta data file
            file_name = "{}.{}.meta.json".format(self.datasource.workspace.name,self.kmi_name)
            meta_file = os.path.join(BorgConfiguration.LIVE_LAYER_DIR,file_name)
            #create the dir if required
            if not os.path.exists(os.path.dirname(meta_file)):
                os.makedirs(os.path.dirname(meta_file))

            with open(meta_file,"wb") as output:
                json.dump(meta_data, output, indent=4)

            json_out = {}
            json_out['meta'] = {"file":"{}{}".format(BorgConfiguration.MASTER_PATH_PREFIX, meta_file),"md5":file_md5(meta_file)}
            json_out['action'] = "publish"
            json_out["publish_time"] = timezone.localtime(timezone.now()).strftime("%Y-%m-%d %H:%M:%S.%f")
        
            #create the dir if required
            if not os.path.exists(os.path.dirname(json_filename)):
                os.makedirs(os.path.dirname(json_filename))

            with open(json_filename, "wb") as output:
                json.dump(json_out, output, indent=4)
        
            hg = hglib.open(BorgConfiguration.BORG_STATE_REPOSITORY)

            #remove other related json files
            json_files = [ self.json_filename_abs(action) for action in [ 'empty_gwc' ] ]
            #get all existing files.
            json_files = [ f for f in json_files if os.path.exists(f) ]
            if json_files:
                hg.remove(files=json_files)

            json_files.append(json_filename)
            hg.commit(include=json_files,addremove=True, user="borgcollector", message="update live layer {}.{}".format(self.datasource.workspace.name, self.kmi_name))
            increase_committed_changes()
                
            try_push_to_repository("livesqlviewlayer",hg)
        finally:
            if hg: hg.close()
            try_clear_push_owner("livesqlviewlayer")

    def empty_gwc(self):
        """
        update layer's json for empty gwc to the repository
        """
        if self.publish_status.unpublished:
            #layer is not published, no need to empty gwc
            raise ValidationError("The wms layer({0}) is not published before.".format(self.kmi_name))

        json_filename = self.json_filename_abs('empty_gwc');
        try_set_push_owner("livelayer")
        hg = None
        try:
            json_out = {}
            json_out["name"] = self.kmi_name
            json_out["workspace"] = self.datasource.workspace.name
            json_out["store"] = self.datasource.name
            json_out["action"] = "empty_gwc"
            json_out["publish_time"] = timezone.localtime(timezone.now()).strftime("%Y-%m-%d %H:%M:%S.%f")

            #create the dir if required
            if not os.path.exists(os.path.dirname(json_filename)):
                os.makedirs(os.path.dirname(json_filename))

            with open(json_filename, "wb") as output:
                json.dump(json_out, output, indent=4)
        
            hg = hglib.open(BorgConfiguration.BORG_STATE_REPOSITORY)
            hg.commit(include=[json_filename],addremove=True, user="borgcollector", message="Empty GWC of live layer {}.{}".format(self.datasource.workspace.name, self.kmi_name))
            increase_committed_changes()
                
            try_push_to_repository("livelayer",hg)
        finally:
            if hg: hg.close()
            try_clear_push_owner("livelayer")

    def __str__(self):
        return self.kmi_name

    class Meta:
        ordering = ("datasource","name")

class DatasourceEventListener(object):
    @staticmethod
    @receiver(pre_delete, sender=Datasource)
    def _pre_delete(sender, instance, **args):
        #unpublish the datasource first
        target_status = instance.next_status(ResourceAction.UNPUBLISH)
        if target_status != instance.status or instance.unpublish_required:
            instance.status = target_status
            instance.save(update_fields=['status','last_unpublish_time'])

    @staticmethod
    @receiver(pre_save, sender=Datasource)
    def _pre_save(sender, instance, **args):
        if instance.unpublish_required:
            #unpublish all layers belonging to the server
            for layer in instance.layer_set.all():
                target_status = layer.next_status(ResourceAction.CASCADE_UNPUBLISH)
                if layer.status != target_status or layer.unpublish_required:
                    #need to unpublish
                    layer.status = target_status
                    layer.save(update_fields=["status","last_unpublish_time"])

            for viewlayer in instance.sqlviewlayer_set.all():
                target_status = viewlayer.next_status(ResourceAction.CASCADE_UNPUBLISH)
                if viewlayer.status != target_status or viewlayer.unpublish_required:
                    #need to unpublish
                    viewlayer.status = target_status
                    viewlayer.save(update_fields=["status","last_unpublish_time"])

            instance.unpublish()
            instance.last_unpublish_time = timezone.now()
        elif instance.publish_required:
            instance.publish()
            #publish succeed, change the status to published.
            instance.last_publish_time = timezone.now()
            #cascade publish layers
            for layer in instance.layer_set.all():
                target_status = layer.next_status(ResourceAction.CASCADE_PUBLISH)
                if layer.status != target_status or layer.publish_required:
                    #need to publish
                    layer.status = target_status
                    layer.save(update_fields=["status","last_publish_time"])

            for viewlayer in instance.sqlviewlayer_set.all():
                target_status = viewlayer.next_status(ResourceAction.CASCADE_PUBLISH)
                if viewlayer.status != target_status or viewlayer.publish_required:
                    #need to unpublish
                    viewlayer.status = target_status
                    viewlayer.save(update_fields=["status","last_publish_time"])

class LayerEventListener(object):
    @staticmethod
    @receiver(pre_delete, sender=Layer)
    def _pre_delete(sender, instance, **args):
        #unpublish the layer first
        target_status = instance.next_status(ResourceAction.UNPUBLISH)
        if target_status != instance.status or instance.unpublish_required:
            instance.status = target_status
            instance.save(update_fields=['status','last_unpublish_time'])

    @staticmethod
    @receiver(post_delete, sender=Layer)
    def _post_delete(sender, instance, **args):
        pass

    @staticmethod
    @inherit_support_receiver(pre_save, sender=Layer)
    def _pre_save(sender, instance, **args):
        if "update_fields" in args and args['update_fields'] and "status" in args["update_fields"]:
            if instance.unpublish_required:
                instance.unpublish()
                instance.last_unpublish_time = timezone.now()
            elif instance.publish_required:
                #publish the datasource to which this layer belongs to
                datasource = instance.datasource
                target_status = datasource.next_status(ResourceAction.DEPENDENT_PUBLISH)
                if datasource.status != target_status or datasource.publish_required:
                    #associated datasource is not published,publish it
                    datasource.status = target_status
                    datasource.save(update_fields=["status","last_publish_time"])
                
                instance.publish()
                instance.last_publish_time = timezone.now()

class SqlViewLayerEventListener(object):
    @staticmethod
    @receiver(pre_delete, sender=SqlViewLayer)
    def _pre_delete(sender, instance, **args):
        #unpublish the layer first
        target_status = instance.next_status(ResourceAction.UNPUBLISH)
        if target_status != instance.status or instance.unpublish_required:
            instance.status = target_status
            instance.save(update_fields=['status','last_unpublish_time'])

    @staticmethod
    @receiver(post_delete, sender=SqlViewLayer)
    def _post_delete(sender, instance, **args):
        pass

    @staticmethod
    @inherit_support_receiver(pre_save, sender=SqlViewLayer)
    def _pre_save(sender, instance, **args):
        import ipdb;ipdb.set_trace()
        if "update_fields" in args and args['update_fields'] and "status" in args["update_fields"]:
            if instance.unpublish_required:
                instance.unpublish()
                instance.last_unpublish_time = timezone.now()
            elif instance.publish_required:
                #publish the datasource to which this layer belongs to
                datasource = instance.datasource
                target_status = datasource.next_status(ResourceAction.DEPENDENT_PUBLISH)
                if datasource.status != target_status or datasource.publish_required:
                    #associated datasource is not published,publish it
                    datasource.status = target_status
                    datasource.save(update_fields=["status","last_publish_time"])
                
                instance.publish()
                instance.last_publish_time = timezone.now()

