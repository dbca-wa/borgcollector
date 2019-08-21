import os
import re
import json
import requests
import logging
import hglib
import urllib
import traceback
import mimetypes
from xml.etree import ElementTree
from xml.dom import minidom
from datetime import datetime


from django.db import transaction
from django.db import models
from django.utils import timezone
from django.utils.six import with_metaclass
from django.conf import settings
from django.utils import timezone
from django.dispatch import receiver
from django.db.models.signals import pre_save, pre_delete,post_save,post_delete
from django.core.exceptions import ValidationError,ObjectDoesNotExist
from django.core.validators import RegexValidator

from tablemanager.models import Workspace
from borg_utils.borg_config import BorgConfiguration
from borg_utils.utils import file_md5
from borg_utils.transaction import TransactionMixin
from borg_utils.signals import refresh_select_choices,inherit_support_receiver
from borg_utils.resource_status import ResourceStatus,ResourceStatusMixin,ResourceAction
from borg_utils.hg_batch_push import try_set_push_owner, try_clear_push_owner, increase_committed_changes, try_push_to_repository

logger = logging.getLogger(__name__)

slug_re = re.compile(r'^[a-zA-Z0-9_\-]+$')
validate_slug = RegexValidator(slug_re, "Slug can only start with letters or underscore, and contain letters, numbers and underscore", "invalid")

getcapabilities_ns = {"xlink":"http://www.w3.org/1999/xlink"}

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

class WmsSyncStatus(object):
    NO_NEED = 'N/A'
    SUCCEED = 'Succeed'
    FAILED = 'Failed'
    NOT_CHANGED = 'Not Changed'
    NOT_EXECUTED = 'Not Executed'

class WmsServer(models.Model,ResourceStatusMixin,TransactionMixin):
    name = models.SlugField(max_length=64,null=False,editable=True,unique=True, help_text="The name of wms server", validators=[validate_slug])
    workspace = models.ForeignKey(Workspace, null=False,blank=False)
    capability_url = models.CharField(max_length=256,null=False,editable=True)
    user = models.CharField(max_length=32,null=True,blank=True)
    password = models.CharField(max_length=32,null=True,blank=True)
    geoserver_setting = models.TextField(blank=True,null=True,editable=False)
    layers = models.PositiveIntegerField(null=False,editable=False,default=0)

    status = models.CharField(max_length=32,null=False,editable=False,choices=ResourceStatus.layer_status_options)
    last_refresh_time = models.DateTimeField(null=True,editable=False)
    last_publish_time = models.DateTimeField(null=True,editable=False)
    last_unpublish_time = models.DateTimeField(null=True,editable=False)
    last_modify_time = models.DateTimeField(null=False,editable=False,default=timezone.now)

    _newline_re = re.compile('\n+')
    def clean(self):
        self.capability_url = self.capability_url.strip()
        self.user = (self.user.strip() if self.user else None) or None
        try:
            o = WmsServer.objects.get(pk=self.pk)
        except ObjectDoesNotExist:
            o = None
            self.status = ResourceStatus.New.name

        if (o 
            and o.name == self.name 
            and o.capability_url == self.capability_url 
            and o.user == self.user 
            and o.password == self.password 
            and o.geoserver_setting == self.geoserver_setting
            and o.status == self.status
        ):
            #not changeed
       
            raise ValidationError("Not changed.")

        if not o or o.capability_url != self.capability_url:
            if not o:
                #new wmsserver,save it first for refresh layers
                self.save()
            self.refresh_layers(False)

        if o:
            #already exist
            self.status = self.next_status(ResourceAction.UPDATE)

        self.last_modify_time = timezone.now()

    @property
    def get_capability_url(self):
        if not hasattr(self,"_capability_url"):
            url = self.capability_url.split("?", 1)
            url, parameters = (url[0], url[1].split("&")) if len(url) == 2 else (url[0], [])
            parameters = dict([(p.split("=", 1) if len(p.split("=",1)) == 2 else (p,"")) for p in parameters if p]) 
            default_parameters = {"SERVICE":"WMS","REQUEST":"GetCapabilities","VERSION":"1.1.1"}
            for k,v in default_parameters.iteritems():
                if not re.compile("{}=".format(k),re.IGNORECASE).search(self.capability_url):
                    parameters[k] = v
            setattr(self,"_wms_version",parameters["VERSION"])
            setattr(self,"_capability_url" , "{}?{}".format(url,urllib.urlencode(parameters)))
        return self._capability_url

    @property
    def wms_version(self):
        url = self.get_capability_url
        return self._wms_version


    def refresh_layers(self,save=True):
        result = None
        #modify the table data
        now = timezone.now()
        if self.user and self.user.strip():
            res = requests.get(self.get_capability_url, auth=(self.user,self.password), verify=False)
        else:
            res = requests.get(self.get_capability_url, verify=False)
        res.raise_for_status()
        if self.wms_version == "1.1.1":
            namespace = ""
        elif self.wms_version == "1.3.0":
            namespace = "{http://www.opengis.net/wms}"
        else:
            raise Exception("Only support wms version 1.1.1 and 1.3.0")
        xml_data = res.text.encode('utf-8')
        root = ElementTree.fromstring(xml_data)
        first_level_layer = root.find("{0}Capability/{0}Layer".format(namespace))
        with transaction.atomic():
            layer_size = self._process_layer_xml(namespace,first_level_layer,now)
                    
            if layer_size == 0:
                #no layers found in the server
                #delete all layers
                WmsLayer.objects.filter(server=self).delete()
            else:
                #set status to DELETE for layers not returned from server
                WmsLayer.objects.filter(server=self).exclude(last_refresh_time = now).delete()

            self.layers = layer_size
            self.last_refresh_time = now
            if save:
                self.save()
        refresh_select_choices.send(self,choice_family="wmslayer")

    @staticmethod
    def getCrsPriority(crs):
        try:
            return ["EPSG:4326","EPSG:4283","EPSG:3857"].index(crs)
        except:
            return 999999

    def _process_layer_xml(self,namespace,layer,process_time,path=None):
        """
        process layer xml.
        return the number of processed layers.
        """
        layer_name_element = layer.find("{0}Name".format(namespace))
        layer_title_element = layer.find("{0}Title".format(namespace))
        layer_size = 0
        if layer_name_element is not None:
            #import ipdb;ipdb.set_trace()
            layer_name = layer_name_element.text
            kmi_name = layer_name.replace(":","_").replace(" ","_")
            layer_abstract_element = layer.find("{0}Abstract".format(namespace))
            boundingbox_iter = layer.iterfind("{0}BoundingBox".format(namespace))
            style_element = layer.find("{0}Style".format(namespace))
            legend_element = style_element.find("{0}LegendURL".format(namespace)) if style_element is not None else None
            legendurl_element = legend_element.find("{0}OnlineResource".format(namespace)) if legend_element is not None else None
            crs = None
            crsPosition = None
            tmpcrs = None
            tmpcrsPosition = None
            bbox = None
            for boundingbox_element in boundingbox_iter:
                tmpcrs = boundingbox_element.get("SRS" if self.wms_version == "1.1.1" else "CRS",None)
                tmpcrsPosition = self.getCrsPriority(tmpcrs)
                if tmpcrsPosition == 0:
                    crs = tmpcrs
                    bbox = "[{},{},{},{}]".format(boundingbox_element.get("minx",None),boundingbox_element.get("miny",None),boundingbox_element.get("maxx",None),boundingbox_element.get("maxy",None))
                    break
                elif not crs or crsPosition > tmpcrsPosition:
                    crs = tmpcrs
                    bbox = "[{},{},{},{}]".format(boundingbox_element.get("minx",None),boundingbox_element.get("miny",None),boundingbox_element.get("maxx",None),boundingbox_element.get("maxy",None))
                    crsPosition = tmpcrsPosition

            if not crs:
                srs_iter = layer.iterfind("{0}{1}".format(namespace,"SRS" if self.wms_version == "1.1.1" else "CRS"))
                for srs_element in srs_iter:
                    tmpcrs = srs_element.text
                    tmpcrsPosition = self.getCrsPriority(tmpcrs)
                    if tmpcrsPosition == 0:
                        crs = tmpcrs
                        break
                    elif not crs or crsPosition > tmpcrsPosition:
                        crs = tmpcrs
                        crsPosition = tmpcrsPosition

            try:
                existed_layer = WmsLayer.objects.get(server = self,name=layer_name)
            except ObjectDoesNotExist:
                existed_layer = None
            if existed_layer:
                #layer already existed
                changed = False
                if existed_layer.title != (layer_title_element.text if layer_title_element is not None else None):
                    existed_layer.title = layer_title_element.text if layer_title_element is not None else None
                    changed = True
                if existed_layer.abstract != (layer_abstract_element.text if layer_abstract_element is not None else None):
                    existed_layer.abstract = layer_abstract_element.text if layer_abstract_element is not None else None
                    changed = True
                
                if existed_layer.crs != crs:
                    existed_layer.crs = crs
                    changed = True

                if existed_layer.bbox != bbox:
                    existed_layer.bbox = bbox
                    changed = True

                if changed:                
                    existed_layer.status = existed_layer.next_status(ResourceAction.UPDATE)

                existed_layer.path = path
                existed_layer.last_refresh_time = process_time
                existed_layer.legend = legendurl_element.get("{{{}}}href".format(getcapabilities_ns['xlink']),None) if legendurl_element is not None else None
                if existed_layer.last_modify_time is None:
                    existed_layer.geoserver_setting = default_layer_geoserver_setting_json
                existed_layer.save()
            else:
                #layer not exist
                existed_layer = WmsLayer(server = self,
                                        name=layer_name,
                                        kmi_name=kmi_name,
                                        title=layer_title_element.text,
                                        path=path,
                                        abstract=layer_abstract_element.text if layer_abstract_element is not None else None,
                                        status=ResourceStatus.New.name,
                                        geoserver_setting = default_layer_geoserver_setting_json,
                                        last_publish_time=None,
                                        last_unpublish_time=None,
                                        last_modify_time=None,
                                        legend=legendurl_element.get("{{{}}}href".format(getcapabilities_ns['xlink']),None) if legendurl_element is not None else None,
                                        crs=crs,
                                        bbox=bbox,
                                        last_refresh_time=process_time)
                existed_layer.save()

            layer_size = 1

        if path is None:
            #top element,ignore the first title
            path = ""
        elif path:
            path = path + "->" + layer_title_element.text
        else:
           path = layer_title_element.text

        layers = layer.findall("{0}Layer".format(namespace))
        for layer in layers:
            layer_size += self._process_layer_xml(namespace,layer,process_time,path)

        return layer_size
 
    def save(self, force_insert=False, force_update=False, using=None, update_fields=None):
        try:
            if self.try_begin_transaction("wmsserver_save"):
                with transaction.atomic():
                    super(WmsServer,self).save(force_insert,force_update,using,update_fields)
            else:
                super(WmsServer,self).save(force_insert,force_update,using,update_fields)
        finally:
            self.try_clear_transaction("wmsserver_save")

    def delete(self,using=None):
        logger.info('Delete {0}:{1}'.format(type(self),self.name))
        try:
            if self.try_begin_transaction("wmsserver_delete"):
                with transaction.atomic():
                    super(WmsServer,self).delete(using)
            else:
                super(WmsServer,self).delete(using)
        finally:
            self.try_clear_transaction("wmsserver_delete")

    def json_filename(self,action='publish'):
        if action in ['publish','unpublish']:
            return os.path.join(self.workspace.publish_channel.name,"wms_stores", "{}.{}.json".format(self.workspace.name, self.name))
        else:
            return os.path.join(self.workspace.publish_channel.name,"wms_stores", "{}.{}.{}.json".format(self.workspace.name, self.name,action))

    def json_filename_abs(self,action='publish'):
        return os.path.join(BorgConfiguration.BORG_STATE_REPOSITORY, self.json_filename(action))

    def unpublish(self):
        publish_file = self.json_filename_abs('publish')
        publish_json = None
        if os.path.exists(publish_file):
            with open(publish_file,"r") as f:
                publish_json = json.loads(f.read())
        else:
            publish_json = {}

        json_file = self.json_filename_abs('unpublish');
        json_out = None
        try_set_push_owner("wmsserver")
        hg = None
        try:
            if publish_json.get("action","publish") != "remove":
                json_out = {}
                json_out["name"] = self.name
                json_out["workspace"] = self.workspace.name
                json_out["channel"] = self.workspace.publish_channel.name

                json_out['action'] = 'remove'
                json_out["sync_geoserver_data"] = self.workspace.publish_channel.sync_geoserver_data

                #retrieve meta data from the last published task
                meta_json = publish_json
                if "meta" in publish_json and "file" in publish_json["meta"]:
                    meta_file = publish_json["meta"]["file"][len(BorgConfiguration.MASTER_PATH_PREFIX):]
                    if os.path.exists(meta_file):
                        with open(meta_file,"r") as f:
                            meta_json = json.loads(f.read())
                    else:
                        meta_json = {}
    
                for key in ["name","workspace","channel","sync_geoserver_data"]:
                    if key in meta_json:
                        json_out[key] = meta_json[key]
            else:
                json_out = publish_json
                
            json_out["remove_time"] = timezone.localtime(timezone.now()).strftime("%Y-%m-%d %H:%M:%S.%f")
        
            #create the dir if required
            if not os.path.exists(os.path.dirname(json_file)):
                os.makedirs(os.path.dirname(json_file))

            with open(json_file, "wb") as output:
                json.dump(json_out, output, indent=4)
        
            hg = hglib.open(BorgConfiguration.BORG_STATE_REPOSITORY)
            hg.commit(include=[json_file],addremove=True, user="borgcollector", message="Unpublish wms store {}.{}".format(self.workspace.name, self.name))
            increase_committed_changes()
                
            try_push_to_repository("wmsserver",hg)
        finally:
            if hg: hg.close()
            try_clear_push_owner("wmsserver")

    def publish(self):
        """
         publish store's json reference (if exists) to the repository,
        """
        try_set_push_owner("wmsserver")
        hg = None
        try:
            meta_data = {}
            meta_data["name"] = self.name
            meta_data["capability_url"] = self.get_capability_url
            meta_data["channel"] = self.workspace.publish_channel.name
            meta_data["username"] = self.user or ""
            meta_data["password"] = self.password or ""
            meta_data["workspace"] = self.workspace.name

            meta_data["sync_geoserver_data"] = self.workspace.publish_channel.sync_geoserver_data
        
            if self.geoserver_setting:
                meta_data["geoserver_setting"] = json.loads(self.geoserver_setting)

            #write meta data file
            file_name = "{}.{}.meta.json".format(self.workspace.name,self.name)
            meta_file = os.path.join(BorgConfiguration.WMS_STORE_DIR,file_name)
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
            hg.commit(include=[json_filename],addremove=True, user="borgcollector", message="Update wms store {}.{}".format(self.workspace.name, self.name))
            increase_committed_changes()
                
            try_push_to_repository("wmsserver",hg)
        finally:
            if hg: hg.close()
            try_clear_push_owner("wmsserver")

    def __str__(self):
        return self.name               

    class Meta:
        ordering = ("name",)


class WmsLayer(models.Model,ResourceStatusMixin,TransactionMixin):
    name = models.CharField(max_length=128,null=False,editable=True, help_text="The name of wms layer")
    server = models.ForeignKey(WmsServer, null=False,editable=False)
    crs = models.CharField(max_length=64,null=True,editable=False)
    bbox = models.CharField(max_length=128,null=True,editable=False)
    kmi_bbox = models.CharField(max_length=128,null=True,blank=True,editable=True)
    title = models.CharField(max_length=512,null=True,editable=False)
    abstract = models.TextField(null=True,editable=False)
    kmi_name = models.SlugField(max_length=128,null=False,editable=True,blank=False, validators=[validate_slug])
    path = models.CharField(max_length=512,null=True,editable=False)
    legend = models.CharField(max_length=512,null=True,editable=False)
    applications = models.TextField(blank=True,null=True,editable=False)
    geoserver_setting = models.TextField(blank=True,null=True,editable=False)
    status = models.CharField(max_length=32, null=False, editable=False,choices=ResourceStatus.layer_status_options)
    last_publish_time = models.DateTimeField(null=True,editable=False)
    last_unpublish_time = models.DateTimeField(null=True,editable=False)
    last_refresh_time = models.DateTimeField(null=False,editable=False)
    last_modify_time = models.DateTimeField(null=True,editable=False)


    def clean(self):
        #import ipdb;ipdb.set_trace()
        self.kmi_name = (self.kmi_name.strip() if self.kmi_name else None) or None
        try:
            o = WmsLayer.objects.get(pk=self.pk)
        except ObjectDoesNotExist:
            o = None

        if (o 
            and o.name == self.name 
            and o.kmi_name == self.kmi_name 
            and o.server == self.server
            and o.title == self.title
            and o.path == self.path
            and o.geoserver_setting == self.geoserver_setting
        ):
            #not changeed
       
            raise ValidationError("Not changed.")

        if o:
            self.status = self.next_status(ResourceAction.UPDATE)
        else:
            self.status = ResourceStatus.New.name

        if self.pk:
            self.last_modify_time = timezone.now()

    @property
    def builtin_metadata(self):
        meta_data = {}
        meta_data["workspace"] = self.server.workspace.name
        meta_data["name"] = self.kmi_name
        meta_data["service_type"] = "WMS"
        meta_data["service_type_version"] = self.server.workspace.publish_channel.wms_version
        meta_data["title"] = self.title
        meta_data["abstract"] = self.abstract
        meta_data["modified"] = self.last_modify_time.astimezone(timezone.get_default_timezone()).strftime("%Y-%m-%d %H:%M:%S.%f") if self.last_modify_time else None

        #bbox
        meta_data["bounding_box"] = self.kmi_bbox or self.bbox or None
        meta_data["crs"] = self.crs or None

        #ows resource
        meta_data["ows_resource"] = {}
        if self.server.workspace.publish_channel.wms_endpoint:
            meta_data["ows_resource"]["wms"] = True
            meta_data["ows_resource"]["wms_version"] = self.server.workspace.publish_channel.wms_version
            meta_data["ows_resource"]["wms_endpoint"] = self.server.workspace.publish_channel.wms_endpoint

        geo_settings = json.loads(self.geoserver_setting) if self.geoserver_setting else {}
        if geo_settings.get("create_cache_layer",False) and self.server.workspace.publish_channel.gwc_endpoint:
            meta_data["ows_resource"]["gwc"] = True
            meta_data["ows_resource"]["gwc_endpoint"] = self.server.workspace.publish_channel.gwc_endpoint

        if self.legend:
            try:
                res = requests.get(self.legend,auth=(self.server.user,self.server.password))
                res.raise_for_status()
                meta_data["source_legend"] = {"content":res.content.encode("base64"),"ext":mimetypes.guess_extension(res.headers.get("content-type",None))}
            except:
                logger.error(traceback.format_exc())
                

        return meta_data

    def update_catalogue_service(self,extra_datas=None):
        meta_data = self.builtin_metadata
        if extra_datas:
            meta_data.update(extra_datas)
        bbox = meta_data.get("bounding_box",None)
        crs = meta_data.get("crs",None)
        #update catalog service
        res = requests.post("{}/catalogue/api/records/".format(settings.CSW_URL),json=meta_data,auth=(settings.CSW_USER,settings.CSW_PASSWORD),verify=settings.CSW_CERT_VERIFY)
        if 400 <= res.status_code < 600 and res.content:
            res.reason = "{}({})".format(res.reason,res.content)
        res.raise_for_status()
        try:
            meta_data = res.json()
        except:
            if res.content.find("microsoft") >= 0:
                res.status_code = 401
                res.reason = "Please login"
            else:
                res.status_code = 400
                res.reason = "Unknown reason"
            res.raise_for_status()

        #add extra data to meta data
        meta_data["workspace"] = self.server.workspace.name
        meta_data["name"] = self.kmi_name
        meta_data["native_name"] = self.name
        meta_data["override_bbox"] = True if self.kmi_bbox else False
        meta_data["store"] = self.server.name
        meta_data["auth_level"] = self.server.workspace.auth_level
        meta_data["preview_path"] = "{}{}".format(BorgConfiguration.MASTER_PATH_PREFIX, BorgConfiguration.PREVIEW_DIR)
        meta_data["spatial_data"] = True

        meta_data["channel"] = self.server.workspace.publish_channel.name
        meta_data["sync_geoserver_data"] = self.server.workspace.publish_channel.sync_geoserver_data

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
            if self.try_begin_transaction("wmslayer_save"):
                with transaction.atomic():
                    super(WmsLayer,self).save(force_insert,force_update,using,update_fields)
            else:
                super(WmsLayer,self).save(force_insert,force_update,using,update_fields)
        finally:
            self.try_clear_transaction("wmslayer_save")

    def delete(self,using=None):
        logger.info('Delete {0}:{1}'.format(type(self),self.name))
        try:
            if self.try_begin_transaction("wmslayer_delete"):
                with transaction.atomic():
                    super(WmsLayer,self).delete(using)
            else:
                super(WmsLayer,self).delete(using)
        finally:
            self.try_clear_transaction("wmslayer_delete")

    def json_filename(self,action='publish'):
        if action in ['publish','unpublish']:
            return os.path.join(self.server.workspace.publish_channel.name,"wms_layers", "{}.{}.json".format(self.server.workspace.name, self.name))
        else:
            return os.path.join(self.server.workspace.publish_channel.name,"wms_layers", "{}.{}.{}.json".format(self.server.workspace.name, self.name,action))

    def json_filename_abs(self,action='publish'):
        return os.path.join(BorgConfiguration.BORG_STATE_REPOSITORY, self.json_filename(action))

    def unpublish(self):
        #remove it from catalogue service
        res = requests.delete("{}/catalogue/api/records/{}:{}/".format(settings.CSW_URL,self.server.workspace.name,self.kmi_name),auth=(settings.CSW_USER,settings.CSW_PASSWORD),verify=settings.CSW_CERT_VERIFY)
        if res.status_code != 404:
            res.raise_for_status()

        publish_file = self.json_filename_abs('publish')
        publish_json = None
        if os.path.exists(publish_file):
            with open(publish_file,"r") as f:
                publish_json = json.loads(f.read())
        else:
            publish_json = {}

        json_file = self.json_filename_abs('unpublish');
        json_out = None
        try_set_push_owner("wmslayer")
        hg = None
        try:
            if publish_json.get("action","publish") != "remove":
                json_out = {}
                json_out["name"] = self.kmi_name
                json_out["workspace"] = self.server.workspace.name
                json_out["store"] = self.server.name
                json_out["spatial_data"] = True
    
                json_out["channel"] = self.server.workspace.publish_channel.name
                json_out["sync_geoserver_data"] = self.server.workspace.publish_channel.sync_geoserver_data
    
                json_out['action'] = "remove"

                #retrieve meta data from the last publish task
                meta_json = publish_json
                if "meta" in publish_json and "file" in publish_json["meta"]:
                    meta_file = publish_json["meta"]["file"][len(BorgConfiguration.MASTER_PATH_PREFIX):]
                    if os.path.exists(meta_file):
                        with open(meta_file,"r") as f:
                            meta_json = json.loads(f.read())
                    else:
                        meta_json = {}
    
                for key in ["name","workspace","store","channel","spatial_data","sync_geoserver_data"]:
                    if key in meta_json:
                        json_out[key] = meta_json[key]
                
            else:
                json_out = publish_json

            json_out["remove_time"] = timezone.localtime(timezone.now()).strftime("%Y-%m-%d %H:%M:%S.%f")
        
            #create the dir if required
            if not os.path.exists(os.path.dirname(json_file)):
                os.makedirs(os.path.dirname(json_file))

            with open(json_file, "wb") as output:
                json.dump(json_out, output, indent=4)
        
            hg = hglib.open(BorgConfiguration.BORG_STATE_REPOSITORY)

            #remove other related json files
            json_files = [ self.json_filename_abs(action) for action in [ 'empty_gwc' ] ]
            #get all existing files.
            json_files = [ f for f in json_files if os.path.exists(f) ]
            if json_files:
                hg.remove(files=json_files)

            json_files.append(json_file)
            hg.commit(include=json_files,addremove=True, user="borgcollector", message="unpublish wms layer {}.{}".format(self.server.workspace.name, self.name))
            increase_committed_changes()
                
            try_push_to_repository("wmslayer",hg)
        finally:
            if hg: hg.close()
            try_clear_push_owner("wmslayer")

    def publish(self):
        """
         publish layer's json reference (if exists) to the repository,
        """
        json_filename = self.json_filename_abs('publish');
        try_set_push_owner("wmslayer")
        hg = None
        try:
            meta_data = self.update_catalogue_service(extra_datas={"publication_date":datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")})

            #write meta data file
            file_name = "{}.{}.meta.json".format(self.server.workspace.name,self.kmi_name)
            meta_file = os.path.join(BorgConfiguration.WMS_LAYER_DIR,file_name)
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
            hg.commit(include=json_files,addremove=True, user="borgcollector", message="update wms layer {}.{}".format(self.server.workspace.name, self.name))
            increase_committed_changes()
                
            try_push_to_repository("wmslayer",hg)
        finally:
            if hg: hg.close()
            try_clear_push_owner("wmslayer")

    def empty_gwc(self):
        """
        update layer's json for empty gwc to the repository
        """
        if self.publish_status.unpublished:
            #layer is not published, no need to empty gwc
            raise ValidationError("The wms layer({0}) is not published before.".format(self.name))

        json_filename = self.json_filename_abs('empty_gwc');
        try_set_push_owner("wmslayer")
        hg = None
        try:
            json_out = {}
            json_out["name"] = self.kmi_name
            json_out["workspace"] = self.server.workspace.name
            json_out["store"] = self.server.name
            json_out["action"] = "empty_gwc"
            json_out["publish_time"] = timezone.localtime(timezone.now()).strftime("%Y-%m-%d %H:%M:%S.%f")

            #create the dir if required
            if not os.path.exists(os.path.dirname(json_filename)):
                os.makedirs(os.path.dirname(json_filename))

            with open(json_filename, "wb") as output:
                json.dump(json_out, output, indent=4)
        
            hg = hglib.open(BorgConfiguration.BORG_STATE_REPOSITORY)
            hg.commit(include=[json_filename],addremove=True, user="borgcollector", message="Empty GWC of wms layer {}.{}".format(self.server.workspace.name, self.name))
            increase_committed_changes()
                
            try_push_to_repository("wmslayer",hg)
        finally:
            if hg: hg.close()
            try_clear_push_owner("wmslayer")

    def __str__(self):
        return self.name


    class Meta:
        unique_together = (("server","name"),("server","kmi_name"))
        ordering = ("server","name")
        pass

class PublishedWmsLayer(WmsLayer):
    class Meta:
        proxy = True
        verbose_name="Wms layer (Published)"
        verbose_name_plural="Wms layers (Published)"

class InterestedWmsLayer(WmsLayer):
    class Meta:
        proxy = True
        verbose_name="Wms layer (Interested)"
        verbose_name_plural="Wms layers (Interested)"


class WmsServerEventListener(object):
    @staticmethod
    @receiver(pre_delete, sender=WmsServer)
    def _pre_delete(sender, instance, **args):
        #unpublish the server first
        target_status = instance.next_status(ResourceAction.UNPUBLISH)
        if target_status != instance.status or instance.unpublish_required:
            instance.status = target_status
            instance.save(update_fields=['status','last_unpublish_time'])

    @staticmethod
    @receiver(pre_save, sender=WmsServer)
    def _pre_save(sender, instance, **args):
        if instance.unpublish_required:
            #unpublish all layers belonging to the server
            for layer in instance.wmslayer_set.all():
                target_status = layer.next_status(ResourceAction.CASCADE_UNPUBLISH)
                if layer.status != target_status or layer.unpublish_required:
                    #need to unpublish
                    layer.status = target_status
                    layer.save(update_fields=["status","last_unpublish_time"])

            instance.unpublish()
            instance.last_unpublish_time = timezone.now()
        elif instance.publish_required:
            instance.publish()
            #publish succeed, change the status to published.
            instance.last_publish_time = timezone.now()
            #cascade publish layers
            """
            cascade publish will trigger all published layers from this wms server to be published again, and in most cases, this is unnecessary.
            for layer in instance.wmslayer_set.all():
                target_status = layer.next_status(ResourceAction.CASCADE_PUBLISH)
                if layer.status != target_status or layer.publish_required:
                    #need to publish
                    layer.status = target_status
                    layer.save(update_fields=["status","last_publish_time"])
            """

class WmsLayerEventListener(object):
    @staticmethod
    @receiver(pre_delete, sender=WmsLayer)
    def _pre_delete(sender, instance, **args):
        #unpublish the layer first
        target_status = instance.next_status(ResourceAction.UNPUBLISH)
        if target_status != instance.status or instance.unpublish_required:
            instance.status = target_status
            instance.save(update_fields=['status','last_unpublish_time'])

    @staticmethod
    @receiver(post_delete, sender=WmsLayer)
    def _post_delete(sender, instance, **args):
        if instance.status != ResourceStatus.New.name:
            refresh_select_choices.send(instance,choice_family="interested_wmslayer")

    @staticmethod
    @inherit_support_receiver(pre_save, sender=WmsLayer)
    def _pre_save(sender, instance, **args):
        instance.related_publish = False
        instance.refresh_select_options = False
        if "update_fields" in args and args['update_fields'] and "status" in args["update_fields"]:
            if instance.unpublish_required:
                instance.unpublish()
                instance.last_unpublish_time = timezone.now()
                instance.related_publish = True
            elif instance.publish_required:
                #publish the server to which this layer belongs to
                server = instance.server
                target_status = server.next_status(ResourceAction.DEPENDENT_PUBLISH)
                if server.status != target_status or server.publish_required:
                    #associated wms server is not published,publish it
                    server.status = target_status
                    server.save(update_fields=["status","last_publish_time"])
                
                instance.publish()
                instance.last_publish_time = timezone.now()
                #publish the resource affected by the current resource
                instance.related_publish = True
                dbobj = WmsLayer.objects.get(pk = instance.pk)
                if not dbobj or dbobj.status == ResourceStatus.New.name:
                    instance.refresh_select_options = True

    @staticmethod
    @inherit_support_receiver(post_save, sender=WmsLayer)
    def _post_save(sender, instance, **args):
        if (hasattr(instance,"related_publish") and getattr(instance,"related_publish")):
            delattr(instance,"related_publish")
            from layergroup.models import LayerGroupLayers
            for layer in LayerGroupLayers.objects.filter(layer = instance):
                target_status = layer.group.next_status(ResourceAction.CASCADE_PUBLISH)
                if target_status != layer.group.status or layer.group.publish_required:
                    layer.group.status = target_status
                    layer.group.save(update_fields=["status","last_publish_time","last_unpublish_time"])

        if (hasattr(instance,"refresh_select_options") and getattr(instance,"refresh_select_options")):
            delattr(instance,"refresh_select_options")
            refresh_select_choices.send(instance,choice_family="interested_wmslayer")
                

