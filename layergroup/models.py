import os
import json
import logging
import itertools
import hglib
import re
import requests
from datetime import datetime

from django.db import transaction
from django.db import models
from django.utils import timezone
from django.utils.six import with_metaclass
from django.utils import timezone
from django.dispatch import receiver
from django.db.models.signals import pre_save, pre_delete,post_save,post_delete
from django.core.exceptions import ValidationError,ObjectDoesNotExist
from django.core.validators import RegexValidator
from django.conf import settings

from tablemanager.models import Workspace,Publish
from wmsmanager.models import WmsLayer
from borg_utils.borg_config import BorgConfiguration
from borg_utils.resource_status import ResourceStatus,ResourceStatusMixin,ResourceAction
from borg_utils.transaction import TransactionMixin
from borg_utils.signals import refresh_select_choices
from borg_utils.hg_batch_push import try_set_push_owner, try_clear_push_owner, increase_committed_changes, try_push_to_repository
from borg_utils.utils import file_md5

logger = logging.getLogger(__name__)

slug_re = re.compile(r'^[a-z0-9_]+$')
validate_slug = RegexValidator(slug_re, "Slug can only contain lowercase letters, numbers and underscores", "invalid")

SRS_CHOICES = (
    ("EPSG:4326","EPSG:4326"),
    ("EPSG:3857","EPSG:3857"),
)
class LayerGroupEmpty(Exception):
    pass

class LayerGroup(models.Model,ResourceStatusMixin,TransactionMixin):
    name = models.SlugField(max_length=128,null=False,unique=True, help_text="The name of layer group", validators=[validate_slug])
    title = models.CharField(max_length=320,null=True,blank=True)
    workspace = models.ForeignKey(Workspace, null=False)
    srs = models.CharField(max_length=320,null=False,choices=SRS_CHOICES)
    abstract = models.TextField(null=True,blank=True)
    geoserver_setting = models.TextField(blank=True,null=True,editable=False)
    status = models.CharField(max_length=32, null=False, editable=False,choices=ResourceStatus.layer_status_options)
    last_publish_time = models.DateTimeField(null=True,editable=False)
    last_unpublish_time = models.DateTimeField(null=True,editable=False)
    last_modify_time = models.DateTimeField(null=False,editable=False,default=timezone.now)

    def clean(self):
        #import ipdb;ipdb.set_trace()
        self.name = self.name.strip() if self.name and self.name.strip() else None
        self.title = self.title.strip() if self.title and self.title.strip() else None
        self.abstract = self.abstract.strip() if self.abstract and self.abstract.strip() else None

        if not self.name:
            raise ValidationError("name is required.")

        try:
            o = LayerGroup.objects.get(pk=self.pk)
        except ObjectDoesNotExist:
            o = None

        if (o 
            and o.name == self.name 
            and o.title == self.title
            and o.srs == self.srs
            and o.workspace == self.workspace
            and o.abstract == self.abstract
            and o.geoserver_setting == self.geoserver_setting
        ):
            #not changeed
            raise ValidationError("Not changed.")
 
        if o:
            self.status = self.next_status(ResourceAction.UPDATE)
        else:
            self.status = ResourceStatus.New
            
        self.last_modify_time = timezone.now()

    def save(self, force_insert=False, force_update=False, using=None, update_fields=None):
        try:
            if self.try_begin_transaction("layergroup_save"):
                with transaction.atomic():
                    super(LayerGroup,self).save(force_insert,force_update,using,update_fields)
            else:
                super(LayerGroup,self).save(force_insert,force_update,using,update_fields)
        finally:
            self.try_clear_transaction("layergroup_save")

    def delete(self,using=None):
        logger.info('Delete {0}:{1}'.format(type(self),self.name))
        try:
            if self.try_begin_transaction("layergroup_delete"):
                with transaction.atomic():
                    super(LayerGroup,self).delete(using)
            else:
                super(LayerGroup,self).delete(using)
        finally:
            self.try_clear_transaction("layergroup_delete")

    def check_circular_dependency(self,editing_group_layer=None,parents=None):
        """
        check whether it has some cycle dependencies.
        """
        if parents:
            parents.append(self)
        else:
            parents = [self]

        queryset = LayerGroupLayers.objects.filter(group = self)
        if editing_group_layer :
            if editing_group_layer.pk:
                queryset = queryset.exclude(pk = editing_group_layer.pk)
            queryset = itertools.chain(queryset,[editing_group_layer])

        for group_layer in queryset:
            if group_layer.sub_group:
                if group_layer.sub_group in parents:
                    #cycle dependency found
                    raise ValidationError("Found a circular dependency:{0}".format("=>".join([g.name for g in parents + [group_layer.sub_group]])))
                else:
                    group_layer.sub_group.check_circular_dependency(None,parents)

    def get_inclusions(self,editing_group_layer=None, check_multi_inclusion = True, included_publishs=None, included_layers=None, included_groups=None):
        """
        Get all included layers and sub groups.
        If in editing mode, editing_group_layer should be the edting layer gorup
        If in non editing mode, editing_group_layer should be None.
        Return a three elements tuple: 
            first element is a dictionary between included publishs and its immediately including group; 
            second element is a dictionary between included layers and its immediately including group; 
            third element is a dictionary between included groups and its immediately including group;
        """
        if not included_publishs:
            included_publishs = {}

        if not included_layers:
            included_layers = {}

        if not included_groups:
            included_groups = {}

        queryset = LayerGroupLayers.objects.filter(group = self)
        if editing_group_layer :
            if editing_group_layer.pk:
                queryset = queryset.exclude(pk = editing_group_layer.pk)
            queryset = itertools.chain(queryset,[editing_group_layer])

        for group_layer in queryset:
            if group_layer.publish:
                if check_multi_inclusion and group_layer.publish in included_publishs:
                    if included_publishs[group_layer.publish].group == group_layer.group:
                        raise ValidationError("Found multiple inclusion:Publish {0} is already included by {1}".format(group_layer.publish.name,included_publishs[group_layer.publish].group.name))
                    else:
                        raise ValidationError("Found multiple inclusion:Publish {0} is included by {1} and {2}".format(group_layer.publish.name,included_publishs[group_layer.publish].group.name,group_layer.group.name))
                else:
                    included_publishs[group_layer.publish] = group_layer

            elif group_layer.layer:
                if check_multi_inclusion and group_layer.layer in included_layers:
                    if included_layers[group_layer.layer].group == group_layer.group:
                        raise ValidationError("Found multiple inclusion:Layer {0} is already included by {1}".format(group_layer.layer.name,included_layers[group_layer.layer].group.name))
                    else:
                        raise ValidationError("Found multiple inclusion:Layer {0} is included by {1} and {2}".format(group_layer.layer.name,included_layers[group_layer.layer].group.name,group_layer.group.name))
                else:
                    included_layers[group_layer.layer] = group_layer

            elif group_layer.sub_group:
                if check_multi_inclusion and group_layer.sub_group in included_groups:
                    if included_groups[group_layer.sub_group].group == group_layer.group:
                        raise ValidationError("Found multiple inclusion:sub group {0} is already included by {1}".format(group_layer.sub_group.name,included_groups[group_layer.sub_group].group.name))
                    else:
                        raise ValidationError("Found multiple inclusion:sub group {0} is included by {1} and {2}".format(group_layer.sub_group.name,included_groups[group_layer.sub_group].group.name,group_layer.group.name))
                else:
                    included_groups[group_layer.sub_group] = group_layer
                    sub_inclusion = group_layer.sub_group.get_inclusions(None,check_multi_inclusion,included_publishs,included_layers,included_groups)
                    included_publishs.update(sub_inclusion[0])
                    included_layers.update(sub_inclusion[1])
                    included_groups.update(sub_inclusion[2])

        return (included_publishs,included_layers,included_groups)
        
    def json_filename(self,action='publish'):
        if action in ['publish','unpublish']:
            return os.path.join(self.workspace.publish_channel.name,"layergroups", "{}.{}.json".format(self.workspace.name, self.name))
        else:
            return os.path.join(self.workspace.publish_channel.name,"layergroups", "{}.{}.{}.json".format(self.workspace.name, self.name,action))

    def json_filename_abs(self,action='publish'):
        return os.path.join(BorgConfiguration.BORG_STATE_REPOSITORY, self.json_filename(action))

    @property
    def builtin_metadata(self):
        meta_data = {}
        meta_data["workspace"] = self.workspace.name
        meta_data["name"] = self.name
        meta_data["service_type"] = "WMS"
        meta_data["service_type_version"] = self.workspace.publish_channel.wms_version
        meta_data["title"] = self.title
        meta_data["abstract"] = self.abstract
        meta_data["modified"] = self.last_modify_time.astimezone(timezone.get_default_timezone()).strftime("%Y-%m-%d %H:%M:%S.%f") if self.last_modify_time else None
        meta_data["crs"] = self.srs or None

        #ows resource
        meta_data["ows_resource"] = {}
        if self.workspace.publish_channel.wms_endpoint:
            meta_data["ows_resource"]["wms"] = True
            meta_data["ows_resource"]["wms_version"] = self.workspace.publish_channel.wms_version
            meta_data["ows_resource"]["wms_endpoint"] = self.workspace.publish_channel.wms_endpoint

        geo_settings = json.loads(self.geoserver_setting) if self.geoserver_setting else {}
        if geo_settings.get("create_cache_layer",False) and self.workspace.publish_channel.gwc_endpoint:
            meta_data["ows_resource"]["gwc"] = True
            meta_data["ows_resource"]["gwc_endpoint"] = self.workspace.publish_channel.gwc_endpoint
        return meta_data

    def update_catalogue_service(self, extra_datas=None):
        meta_data = self.builtin_metadata
        if extra_datas:
            meta_data.update(extra_datas)
        res = requests.post("{}/catalogue/api/records/".format(settings.CSW_URL),json=meta_data,auth=(settings.CSW_USER,settings.CSW_PASSWORD))
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
        meta_data["workspace"] = self.workspace.name
        meta_data["name"] = self.name
        meta_data["native_name"] = self.name
        meta_data["auth_level"] = self.workspace.auth_level
        meta_data["preview_path"] = "{}{}".format(BorgConfiguration.MASTER_PATH_PREFIX, BorgConfiguration.PREVIEW_DIR)
        meta_data["spatial_data"] = True

        meta_data["channel"] = self.workspace.publish_channel.name
        meta_data["sync_geoserver_data"] = self.workspace.publish_channel.sync_geoserver_data

        if self.geoserver_setting:
            meta_data["geoserver_setting"] = json.loads(self.geoserver_setting)
                
        return meta_data



    def unpublish(self):
        """
        unpublish layer group
        """
        #remove it from catalogue service
        res = requests.delete("{}/catalogue/api/records/{}:{}/".format(settings.CSW_URL,self.workspace.name,self.name),auth=(settings.CSW_USER,settings.CSW_PASSWORD))
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

        try_set_push_owner("layergroup")
        hg = None
        try:
            if publish_json.get("action","publish") != "remove":
                json_out = {}
                json_out["name"] = self.name
                json_out["workspace"] = self.workspace.name

                json_out["spatial_data"] = True
                json_out["channel"] = self.workspace.publish_channel.name
                json_out["sync_geoserver_data"] = self.workspace.publish_channel.sync_geoserver_data

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
    
                for key in ["name","workspace","channel","spatial_data","sync_geoserver_data"]:
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
            hg.commit(include=json_files, user="borgcollector",addremove=True, message="Unpublish layer group {}.{}".format(self.workspace.name, self.name))
            increase_committed_changes()
                
            try_push_to_repository("layergroup",hg)
        finally:
            if hg: hg.close()
            try_clear_push_owner("layergroup")


    def publish(self):
        """
        Only publish the member layers which is already published.

        """
        json_filename = self.json_filename_abs('publish');

        try_set_push_owner("layergroup")
        hg = None
        try:
            json_out = self.update_catalogue_service(extra_datas={"publication_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")})
            layers = []
            for group_layer in LayerGroupLayers.objects.filter(group=self).order_by("order"):
                if group_layer.layer and group_layer.layer.is_published:
                    layers.append({"type":"wms_layer","name":group_layer.layer.kmi_name,"store":group_layer.layer.server.name,"workspace":group_layer.layer.server.workspace.name})
                elif group_layer.publish and group_layer.publish.is_published:
                    layers.append({"type":"publish","name":group_layer.publish.name,"workspace":group_layer.publish.workspace.name})
                elif group_layer.sub_group and group_layer.sub_group.is_published:
                    layers.append({"type":"group","name":group_layer.sub_group.name,"workspace":group_layer.sub_group.workspace.name})
            if not layers:
                #layergroup is empty,remove it.
                raise LayerGroupEmpty("Layer group can't be empty.")
            json_out["layers"] = layers
            json_out["srs"] = self.srs or None
            json_out["publish_time"] = timezone.localtime(timezone.now()).strftime("%Y-%m-%d %H:%M:%S.%f")
            inclusions = self.get_inclusions()
            dependent_groups = []
            for group in inclusions[2].keys():
                if group.is_published:
                    dependent_groups.append({"name":group.name,"workspace":group.workspace.name})
            json_out["dependent_groups"] = dependent_groups
        
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
            hg.commit(include=json_files, user="borgcollector",addremove=True, message="Update layer group {}.{}".format(self.workspace.name, self.name))
            increase_committed_changes()
                
            try_push_to_repository("layergroup",hg)
        finally:
            if hg: hg.close()
            try_clear_push_owner("layergroup")

    def empty_gwc(self):
        """
        update layer group's json for empty gwc to the repository
        """
        if self.publish_status.unpublished:
            #layer is not published, no need to empty gwc
            raise ValidationError("The layergroup({0}) is not published before.".format(self.name))

        json_filename = self.json_filename_abs('empty_gwc');
        try_set_push_owner("layergroup")
        hg = None
        try:
            json_out = {}
            json_out["name"] = self.name
            json_out["workspace"] = self.workspace.name
            json_out["action"] = "empty_gwc"
            json_out["publish_time"] = timezone.localtime(timezone.now()).strftime("%Y-%m-%d %H:%M:%S.%f")

            if self.geoserver_setting:
                json_out["geoserver_setting"] = json.loads(self.geoserver_setting)
        
            #create the dir if required
            if not os.path.exists(os.path.dirname(json_filename)):
                os.makedirs(os.path.dirname(json_filename))

            with open(json_filename, "wb") as output:
                json.dump(json_out, output, indent=4)
        
            hg = hglib.open(BorgConfiguration.BORG_STATE_REPOSITORY)
            hg.commit(include=[json_filename],addremove=True, user="borgcollector", message="Empty GWC of layer group {}.{}".format(self.workspace.name, self.name))
            increase_committed_changes()
                
            try_push_to_repository("layergroup",hg)
        finally:
            if hg: hg.close()
            try_clear_push_owner("layergroup")

    def __str__(self):
        return self.name

    class Meta:
        ordering = ["workspace","name"]


class LayerGroupLayers(models.Model,TransactionMixin):
    group = models.ForeignKey(LayerGroup,null=False,blank=False,related_name="group_layer")
    layer = models.ForeignKey(WmsLayer,null=True,blank=False)
    publish = models.ForeignKey(Publish,null=True,blank=True,editable=False)
    sub_group = models.ForeignKey(LayerGroup,null=True,blank=True,related_name="subgroup_layer",editable=False)
    order = models.PositiveIntegerField(null=False,blank=False)

    def clean(self):
        if not self.group_id:
            raise ValidationError("group is required")
        self.publish = None
        self.sub_group = None
        if (
            (self.layer is None and self.sub_group is None and self.publish is None)
            or (self.layer and self.sub_group and self.publish)
        
        ):
            #currently publish and sub_group are disabled
            raise ValidationError("Layer required")

        try:
            o = LayerGroupLayers.objects.get(pk=self.pk)
        except ObjectDoesNotExist:
            o = None

        if (o 
            and o.group == self.group
            and o.layer == self.layer
            and o.publish == self.publish
            and o.sub_group == self.sub_group
            and o.order == self.order
        ):
            #not changeed
            raise ValidationError("Not changed.")
        
        if (
            (self.layer and self.group.workspace != self.layer.server.workspace)
            or (self.publish and self.group.workspace != self.publish.workspace)
            or (self.sub_group and self.group.workspace != self.sub_group.workspace)
        ):
            raise ValidationError("Both layer group and its layers must belong to the same workspace.")

        #check circular dependency
        self.group.check_circular_dependency(self)
        #check multiple inclusion
        self.group.get_inclusions(self)

    def save(self, force_insert=False, force_update=False, using=None, update_fields=None):
        try:
            if self.try_begin_transaction("layer_save"):
                with transaction.atomic():
                    super(LayerGroupLayers,self).save(force_insert,force_update,using,update_fields)
            else:
                super(LayerGroupLayers,self).save(force_insert,force_update,using,update_fields)
        finally:
            self.try_clear_transaction("layer_save")

    def delete(self,using=None):
        logger.info('Delete {0}:{1}'.format(type(self),self.name))
        try:
            if self.try_begin_transaction("layer_delete"):
                with transaction.atomic():
                    super(LayerGroupLayers,self).delete(using)
            else:
                super(LayerGroupLayers,self).delete(using)
        finally:
            self.try_clear_transaction("layer_delete")

    def __str__(self):
        return "group={0} , layer={1}".format(self.group,self.layer)

    class Meta:
        unique_together = (("group","layer","sub_group"),("group","order"))
        ordering = ["group","order"]
        verbose_name="Layer group layers"
        verbose_name_plural="Layer group layers"


class LayerGroupEventListener(object):
    @staticmethod
    @receiver(pre_delete, sender=LayerGroup)
    def _pre_delete(sender, instance, **args):
        #unpublish the group first
        target_status = instance.next_status(ResourceAction.UNPUBLISH)
        if target_status != instance.status or instance.unpublish_required:
            instance.status = target_status
            instance.save(update_fields=['status','last_unpublish_time'])

    @staticmethod
    @receiver(post_delete, sender=LayerGroup)
    def _post_delete(sender, instance, **args):
        refresh_select_choices.send(instance,choice_family="layergroup")

    @staticmethod
    @receiver(pre_save, sender=LayerGroup)
    def _pre_save(sender, instance, **args):
        instance.related_publish = False
        if not instance.pk:
            instance.new_object = True
        if "update_fields" in args and args['update_fields'] and "status" in args["update_fields"]:
            if instance.unpublish_required: 
                instance.unpublish()
                instance.last_unpublish_time = timezone.now()
                instance.related_publish = True
            elif instance.publish_required:
                #publish the dependent layers
                if instance.publish_status == ResourceStatus.Published:
                    for layer in instance.group_layer.all():
                        if layer.layer:
                            target_status = layer.layer.next_status(ResourceAction.DEPENDENT_PUBLISH)
                            if layer.layer.status != target_status or layer.layer.publish_required:
                                #dependent layer is not published, 
                                layer.layer.status = target_status
                                layer.layer.save(update_fields=["status","last_publish_time","last_unpublish_time"])
                        elif layer.sub_group:
                            #publish triggered by user and try to publish the dependent sub groups
                            target_status = layer.sub_group.next_status(ResourceAction.DEPENDENT_PUBLISH)
                            if layer.sub_group.status != target_status or layer.sub_group.publish_required:
                                #dependent group is not published, 
                                layer.sub_group.status = target_status
                                layer.sub_group.save(update_fields=["status","last_publish_time","last_unpublish_time"])
                try:
                    instance.publish()
                except LayerGroupEmpty:
                    #unpublish it
                    existed_instance = LayerGroup.objects.get(pk = instance.pk)
                    target_status = existed_instance.next_status(ResourceAction.CASCADE_UNPUBLISH)
                    if target_status != existed_instance.status or existed_instance.unpublish_required:
                        instance.status = target_status
                        instance.unpublish()
                        instance.last_unpublish_time = timezone.now()
                        instance.related_publish = True
                    else:
                        instance.status = existed_instance.status
                    return
                instance.last_publish_time = timezone.now()
                #publish the resource affected by the current resource
                dbobj = LayerGroup.objects.get(pk = instance.pk)
                if dbobj and dbobj.is_unpublished:
                    instance.related_publish = True
                

    @staticmethod
    @receiver(post_save, sender=LayerGroup)
    def _post_save(sender, instance, **args):
        if (hasattr(instance,"new_object") and getattr(instance,"new_object")):
            delattr(instance,"new_object")
            refresh_select_choices.send(instance,choice_family="layergroup")

        if (hasattr(instance,"related_publish") and getattr(instance,"related_publish")):
            delattr(instance,"related_publish")
            for layer in instance.subgroup_layer.all():
                target_status = layer.group.next_status(ResourceAction.CASCADE_PUBLISH)
                if target_status != layer.group.status or layer.group.publish_required:
                    layer.group.status = target_status
                    layer.group.save(update_fields=["status","last_publish_time","last_unpublish_time"])
            

class LayerGroupLayersEventListener(object):
    @staticmethod
    @receiver(post_delete, sender=LayerGroupLayers)
    def _post_delete(sender, instance, **args):
        if instance.is_current_transaction("layer_delete"):
            #trigged by itself
            instance.group.status = instance.group.next_status(ResourceAction.UPDATE)
            instance.group.last_modify_time = timezone.now()
            instance.group.save(update_fields=["status","last_modify_time"])

    @staticmethod
    @receiver(post_save, sender=LayerGroupLayers)
    def _post_save(sender, instance, **args):
        if instance.is_current_transaction("layer_save"):
            instance.group.status = instance.group.next_status(ResourceAction.UPDATE)
            instance.group.last_modify_time = timezone.now()
            instance.group.save(update_fields=["status","last_modify_time"])
        

