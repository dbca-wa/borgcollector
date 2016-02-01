import os
import json
import logging
import itertools
import hglib
import re

from django.db import transaction
from django.db import models
from django.utils import timezone
from django.utils.six import with_metaclass
from django.utils import timezone
from django.dispatch import receiver
from django.db.models.signals import pre_save, pre_delete,post_save,post_delete
from django.core.exceptions import ValidationError,ObjectDoesNotExist
from django.core.validators import RegexValidator

from tablemanager.models import Workspace,Publish
from wmsmanager.models import WmsLayer
from borg_utils.borg_config import BorgConfiguration
from borg_utils.resource_status import ResourceStatus,ResourceStatusManagement
from borg_utils.signal_enable import SignalEnable
from borg_utils.signals import refresh_select_choices
from borg_utils.hg_batch_push import try_set_push_owner, try_clear_push_owner, increase_committed_changes, try_push_to_repository

logger = logging.getLogger(__name__)

slug_re = re.compile(r'^[a-z0-9_]+$')
validate_slug = RegexValidator(slug_re, "Slug can only contain lowercase letters, numbers and underscores", "invalid")

GROUP_STATUS_CHOICES = (
    (ResourceStatus.NEW,ResourceStatus.NEW),
    (ResourceStatus.UPDATED,ResourceStatus.UPDATED),
    (ResourceStatus.PUBLISHED,ResourceStatus.PUBLISHED),
    (ResourceStatus.UNPUBLISHED,ResourceStatus.UNPUBLISHED),
)

SRS_CHOICES = (
    ("EPSG:4283","EPSG:4283"),
    ("EPSG:4326","EPSG:4326"),
)
class LayerGroupEmpty(Exception):
    pass

class LayerGroup(models.Model,ResourceStatusManagement,SignalEnable):
    name = models.SlugField(max_length=128,null=False,unique=True, help_text="The name of layer group", validators=[validate_slug])
    title = models.CharField(max_length=320,null=True,blank=True)
    workspace = models.ForeignKey(Workspace, null=False)
    srs = models.CharField(max_length=320,null=False,choices=SRS_CHOICES)
    abstract = models.TextField(null=True,blank=True)
    geoserver_setting = models.TextField(blank=True,null=True,editable=False)
    status = models.CharField(max_length=16, null=False, editable=False,choices=GROUP_STATUS_CHOICES)
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
            and o.workspace == self.workspace
            and o.abstract == self.abstract
            and o.geoserver_setting == self.geoserver_setting
        ):
            #not changeed
            raise ValidationError("Not changed.")
 
        if o:
            self.status = self.get_next_status(o.status,ResourceStatus.UPDATED)
        else:
            self.status = ResourceStatus.NEW
            
        self.last_modify_time = timezone.now()

    def save(self, force_insert=False, force_update=False, using=None, update_fields=None):
        try:
            if self.try_set_signal_sender("save"):
                with transaction.atomic():
                    super(LayerGroup,self).save(force_insert,force_update,using,update_fields)
            else:
                super(LayerGroup,self).save(force_insert,force_update,using,update_fields)
        finally:
            self.try_clear_signal_sender("save")

    def delete(self,using=None):
        logger.info('Delete {0}:{1}'.format(type(self),self.name))
        try:
            if self.try_set_signal_sender("delete"):
                with transaction.atomic():
                    super(LayerGroup,self).delete(using)
            else:
                super(LayerGroup,self).delete(using)
        finally:
            self.try_clear_signal_sender("delete")

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
        if action == 'publish':
            return os.path.join(self.workspace.publish_channel.name,"layergroups", "{}.{}.json".format(self.workspace.name, self.name))
        else:
            return os.path.join(self.workspace.publish_channel.name,"layergroups", "{}.{}.{}.json".format(self.workspace.name, self.name,action))

    def json_filename_abs(self,action='publish'):
        return os.path.join(BorgConfiguration.BORG_STATE_REPOSITORY, self.json_filename(action))

    def unpublish(self):
        """
         remove store's json reference (if exists) from the repository,
         return True if store is removed for repository; return false, if layers does not existed in repository.
        """
        json_filename = self.json_filename_abs('publish');
        if os.path.exists(json_filename):
            #file exists, layers is published, remove it.
            try_set_push_owner("layergroup")
            hg = None
            try:
                hg = hglib.open(BorgConfiguration.BORG_STATE_REPOSITORY)
                hg.remove(files=[json_filename])
                hg.commit(include=[json_filename],addremove=True, user="borgcollector", message="Remove layer group {}.{}".format(self.workspace.name, self.name))
                increase_committed_changes()
                
                try_push_to_repository("layergroup",hg)
            finally:
                if hg: hg.close()
                try_clear_push_owner("layergroup")
            return True
        else:
            return False

    def publish(self):
        """
        publish store's json reference (if exists) to the repository;
        """
        json_filename = self.json_filename_abs('publish');

        try_set_push_owner("layergroup")
        hg = None
        try:
            layers = []
            for group_layer in LayerGroupLayers.objects.filter(group=self).order_by("order"):
                if group_layer.layer and group_layer.layer.is_published:
                    layers.append({"type":"wms_layer","name":group_layer.layer.layer_name,"store":group_layer.layer.server.name,"workspace":group_layer.layer.server.workspace.name})
                elif group_layer.publish :
                    layers.append({"type":"publish","name":group_layer.publish.name,"workspace":group_layer.publish.workspace.name})
                elif group_layer.sub_group and group_layer.sub_group.is_published:
                    layers.append({"type":"group","name":group_layer.sub_group.name,"workspace":group_layer.sub_group.workspace.name})
            if not layers:
                #layergroup is empty,remove it.
                raise LayerGroupEmpty("Layer group can't be empty.")
            json_out = {}
            json_out["layers"] = layers;
            json_out["name"] = self.name
            json_out["title"] = self.title or ""
            json_out["abstract"] = self.abstract or ""
            json_out["workspace"] = self.workspace.name
            json_out["srs"] = self.srs
            json_out["publish_time"] = timezone.now().strftime("%Y-%m-%d %H:%M:%S.%f")
            inclusions = self.get_inclusions()
            dependent_groups = []
            for group in inclusions[2].keys():
                if group.is_published:
                    dependent_groups.append({"name":group.name,"workspace":group.workspace.name})
            json_out["dependent_groups"] = dependent_groups
        
            if self.geoserver_setting:
                json_out["geoserver_setting"] = json.loads(self.geoserver_setting)
        
            #create the dir if required
            if not os.path.exists(os.path.dirname(json_filename)):
                os.makedirs(os.path.dirname(json_filename))

            with open(json_filename, "wb") as output:
                json.dump(json_out, output, indent=4)
        
            hg = hglib.open(BorgConfiguration.BORG_STATE_REPOSITORY)
            hg.commit(include=[json_filename], user="borgcollector",addremove=True, message="Update layer group {}.{}".format(self.workspace.name, self.name))
            increase_committed_changes()
                
            try_push_to_repository("layergroup",hg)
        finally:
            if hg: hg.close()
            try_clear_push_owner("layergroup")

    def empty_gwc(self):
        """
        update layer group's json for empty gwc to the repository
        """
        if self.status not in [ResourceStatus.PUBLISHED,ResourceStatus.UPDATED]:
            #layer is not published, no need to empty gwc
            return
        json_filename = self.json_filename_abs('empty_gwc');
        try_set_push_owner("layergroup")
        hg = None
        try:
            json_out = {}
            json_out["name"] = self.name
            json_out["workspace"] = self.workspace.name
            json_out["action"] = "empty_gwc"
            json_out["empty_time"] = timezone.now().strftime("%Y-%m-%d %H:%M:%S.%f")

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


class LayerGroupLayers(models.Model,SignalEnable):
    group = models.ForeignKey(LayerGroup,null=False,blank=False,related_name="+")
    layer = models.ForeignKey(WmsLayer,null=True,blank=False)
    publish = models.ForeignKey(Publish,null=True,blank=True,editable=False)
    sub_group = models.ForeignKey(LayerGroup,null=True,blank=True,related_name="+",editable=False)
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
            if self.try_set_signal_sender("save"):
                with transaction.atomic():
                    super(LayerGroupLayers,self).save(force_insert,force_update,using,update_fields)
            else:
                super(LayerGroupLayers,self).save(force_insert,force_update,using,update_fields)
        finally:
            self.try_clear_signal_sender("save")

    def delete(self,using=None):
        logger.info('Delete {0}:{1}'.format(type(self),self.name))
        try:
            if self.try_set_signal_sender("delete"):
                with transaction.atomic():
                    super(LayerGroupLayers,self).delete(using)
            else:
                super(LayerGroupLayers,self).delete(using)
        finally:
            self.try_clear_signal_sender("delete")

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
        target_status = instance.get_next_status(instance.status,ResourceStatus.UNPUBLISH)
        if target_status != instance.status:
            instance.status = target_status
            instance.save(update_fields=['status','last_unpublish_time'])

    @staticmethod
    @receiver(post_delete, sender=LayerGroup)
    def _post_delete(sender, instance, **args):
        refresh_select_choices.send(instance,choice_family="layergroup")

    @staticmethod
    @receiver(pre_save, sender=LayerGroup)
    def _pre_save(sender, instance, **args):
        if not instance.pk:
            instance.new_object = True
        if "update_fields" in args and args['update_fields'] and "status" in args["update_fields"]:
            if instance.status == ResourceStatus.UNPUBLISH: 
                instance.unpublish()
                #unpublish succeed, change the status to unpublished.
                instance.status = ResourceStatus.UNPUBLISHED
                instance.last_unpublish_time = timezone.now()
                instance.side_publish = True
            elif instance.status == ResourceStatus.PUBLISH:
                #publish the dependent layers
                for layer in LayerGroupLayers.objects.filter(group=instance):
                    if layer.layer:
                        target_status = layer.layer.get_next_status(layer.layer.status,ResourceStatus.CASCADE_PUBLISH)
                        if layer.layer.status != target_status:
                            #dependent layer is not published, 
                            layer.layer.status = target_status
                            layer.layer.save(update_fields=["status","last_publish_time","last_unpublish_time"])
                    elif layer.sub_group:
                        target_status = layer.sub_group.get_next_status(layer.sub_group.status,ResourceStatus.CASCADE_PUBLISH)
                        if layer.sub_group.status != target_status:
                            #dependent group is not published, 
                            layer.sub_group.status = target_status
                            layer.sub_group.save(update_fields=["status","last_publish_time","last_unpublish_time"])
                try:
                    instance.publish()
                except LayerGroupEmpty:
                    #unpublish it
                    existed_instance = LayerGroup.objects.get(pk = instance.pk)
                    target_status = instance.get_next_status(existed_instance.status,ResourceStatus.UNPUBLISH)
                    if target_status != existed_instance.status:
                        instance.status = target_status
                        LayerGroupEventListener._pre_save(sender,instance,**args)
                    else:
                        instance.status = existed_instance.status
                    return
                #publish succeed, change the status to published.
                instance.status = ResourceStatus.PUBLISHED
                instance.last_publish_time = timezone.now()
                #publish the resource affected by the current resource
                dbobj = LayerGroup.objects.get(pk = instance.pk)
                if dbobj and dbobj.is_unpublished:
                    instance.side_publish = True
                

    @staticmethod
    @receiver(post_save, sender=LayerGroup)
    def _post_save(sender, instance, **args):
        if (hasattr(instance,"new_object") and getattr(instance,"new_object")):
            delattr(instance,"new_object")
            refresh_select_choices.send(instance,choice_family="layergroup")

        if "update_fields" in args and args['update_fields'] and "status" in args["update_fields"]:
            if instance.status in [ResourceStatus.PUBLISHED,ResourceStatus.UNPUBLISHED]:
                if (hasattr(instance,"side_publish") and getattr(instance,"side_publish")):
                    delattr(instance,"side_publish")
                    for layer in LayerGroupLayers.objects.filter(sub_group = instance):
                        target_status = layer.group.get_next_status(layer.group.status,ResourceStatus.SIDE_PUBLISH)
                        if target_status != layer.group.status:
                            layer.group.status = target_status
                            layer.group.save(update_fields=["status","last_publish_time","last_unpublish_time"])
            

class LayerGroupLayersEventListener(object):
    @staticmethod
    @receiver(post_delete, sender=LayerGroupLayers)
    def _post_delete(sender, instance, **args):
        if instance.is_signal_sender("delete"):
            #trigged by itself
            instance.group.status = instance.group.get_next_status(instance.group.status,ResourceStatus.UPDATED)
            instance.group.last_modify_time = timezone.now()
            instance.group.save(update_fields=["status","last_modify_time"])

    @staticmethod
    @receiver(post_save, sender=LayerGroupLayers)
    def _post_save(sender, instance, **args):
        if instance.is_signal_sender("save"):
            instance.group.status = instance.group.get_next_status(instance.group.status,ResourceStatus.UPDATED)
            instance.group.last_modify_time = timezone.now()
            instance.group.save(update_fields=["status","last_modify_time"])
        

