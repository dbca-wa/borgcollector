import re
import logging

from django.db import models,transaction
from django.dispatch import receiver
from django.utils import timezone
from django.db.models.signals import pre_save, pre_delete,post_save,post_delete
from django.core.validators import RegexValidator
from django.core.exceptions import ValidationError,ObjectDoesNotExist

from tablemanager.models import Publish
from tablemanager.publish_action import PublishAction
from wmsmanager.models import WmsLayer
from borg_utils.signal_enable import SignalEnable
from borg_utils.resource_status import ResourceStatus

slug_re = re.compile(r'^[a-z0-9_]+$')
validate_slug = RegexValidator(slug_re, "Slug can only contain lowercase letters, numbers and underscores", "invalid")

logger = logging.getLogger(__name__)

class Application(models.Model,SignalEnable):
    """
    Represent a application which can access wms,wfs,wcs service from geoserver
    """
    name = models.CharField(max_length=255, validators=[validate_slug],db_index=True,blank=False)
    description = models.TextField(blank=True)

    def delete(self,using=None):
        logger.info('Delete {0}:{1}'.format(type(self),self.name))
        with transaction.atomic():
            super(Application,self).delete(using)

    def save(self, force_insert=False, force_update=False, using=None, update_fields=None):
        with transaction.atomic():
            super(Application,self).save(force_insert,force_update,using,update_fields)

    def __str__(self):
        return self.name

class Application_Layers(models.Model,SignalEnable):
    """
    The relationship between application and layer
    """
    application = models.ForeignKey(Application,blank=False,null=False)
    publish = models.ForeignKey(Publish,db_index=True,null=True,blank=True)
    wmslayer = models.ForeignKey(WmsLayer,db_index=True,null=True,blank=True)
    order = models.PositiveIntegerField(blank=False,null=False)

    def delete(self,using=None):
        with transaction.atomic():
            super(Application_Layers,self).delete(using)

    def clean(self):
        if (
            (self.publish and self.wmslayer)
            or (not self.publish and not self.wmslayer)
        ):
            raise ValidationError("Must input either publish or wmslayer, but not both.")
        previous_object = None
        if self.pk:
            try:
                previous_object = Application_Layers.objects.get(pk = self.pk)
            except ObjectDoesNotExist:
                previous_object = None

        if previous_object:
            #object existing
            if (
                previous_object.application == self.application 
                and previous_object.publish == self.publish
                and previous_object.wmslayer == self.wmslayer
                and previous_object.order == self.order
            ):
                raise ValidationError("No changes.")

    def save(self, force_insert=False, force_update=False, using=None, update_fields=None):
        with transaction.atomic():
            super(Application_Layers,self).save(force_insert,force_update,using,update_fields)

    def __str__(self):
        return "application={0} , publish={1}, wmslayer={2}".format(self.application,self.publish,self.wmslayer)

    class Meta:
        unique_together = (('application','publish'),('application','wmslayer'))
        verbose_name = "Application's Layer"


class Application_LayersEventListener(object):
    @staticmethod
    def _update_applications(instance,editing_instance=None):
        if instance.publish:
            if editing_instance and editing_instance.publish == instance.publish:
                #publish not changed.
                pass
            else:
                q = Application_Layers.objects.filter(publish=instance.publish)
                if editing_instance and editing_instance.pk:
                    q = q.exclude(pk = editing_instance.pk)
                q = q.order_by("application__name")
                applications = ",".join(["{0}:{1}".format(o.application,o.order) for o in q])
                if instance.publish.applications != applications:
                    instance.publish.applications = applications
                    instance.publish.last_modify_time = timezone.now()
                    instance.publish.pending_actions = PublishAction(instance.publish.pending_actions).column_changed("applications").actions
                    instance.publish.save(update_fields=["applications","last_modify_time","pending_actions"])
        
        if instance.wmslayer:
            if editing_instance and editing_instance.wmslayer == instance.wmslayer:
                #wmslayer not changed.
                pass
            else:
                q = Application_Layers.objects.filter(wmslayer=instance.wmslayer)
                if editing_instance and editing_instance.pk:
                    q = q.exclude(pk = editing_instance.pk)
                q = q.order_by("application__name")
                applications = ",".join(["{0}:{1}".format(o.application,o.order) for o in q])
                if instance.wmslayer.applications != applications:
                    instance.wmslayer.applications = applications
                    instance.wmslayer.last_modify_time = timezone.now()
                    instance.wmslayer.status = instance.wmslayer.get_next_status(instance.wmslayer.status,ResourceStatus.UPDATED)
                    instance.wmslayer.save(update_fields=["status","applications","last_modify_time"])

    @staticmethod
    @receiver(post_delete, sender=Application_Layers)
    def _post_delete(sender, instance, **args):
        Application_LayersEventListener._update_applications(instance)
        
    @staticmethod
    @receiver(pre_save, sender=Application_Layers)
    def _pre_save(sender, instance, **args):
        if instance.pk:
            existed_instance = Application_Layers.objects.get(pk = instance.pk)
            Application_LayersEventListener._update_applications(existed_instance,instance)

    @staticmethod
    @receiver(post_save, sender=Application_Layers)
    def _post_save(sender, instance, **args):
        Application_LayersEventListener._update_applications(instance)
        

