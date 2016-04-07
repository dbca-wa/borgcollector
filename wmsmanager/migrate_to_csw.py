import os
from datetime import datetime
import pytz
import requests
import json

from django.utils import timezone
from django.conf import settings

from wmsmanager.models import WmsLayer
from borg_utils.resource_status import ResourceStatus,ResourceStatusManagement

def migrate_all(debug=False):
    """
    Migrate all meta data to csw
    """
    for layer in WmsLayer.objects.filter(status__in=[ResourceStatus.Published.name,ResourceStatus.CascadePublished.name,ResourceStatus.Updated.name]):
        migrate(layer,debug)
def migrate(layer,debug=False):
    """
    Migrate one meta data to csw
    """
    if not hasattr(layer,"kmi_title"):
        #kmi title not found, migrate finished
        raise Exception("Migrate to csw has finished.")

    print "Migrate {}".format(layer.layer_name)
    meta_data = layer.builtin_metadata
    meta_data["auto_update"] = True
    if layer.kmi_title and layer.kmi_title.strip():
        #has customized title
        meta_data["title"] = layer.kmi_title
        meta_data["auto_update"] = False

    if layer.kmi_abstract and layer.kmi_abstract.strip():
        #has customized abstract
        meta_data["abstract"] = layer.kmi_abstract
        meta_data["auto_update"] = False

    modify_time = layer.last_modify_time or layer.last_refresh_time
    publish_time = layer.last_publish_time
    insert_time = modify_time if modify_time <= publish_time else publish_time
    meta_data["insert_date"] = insert_time.astimezone(timezone.get_default_timezone()).strftime("%Y-%m-%d %H:%M:%S.%f")
    meta_data["modified"] = modify_time.astimezone(timezone.get_default_timezone()).strftime("%Y-%m-%d %H:%M:%S.%f")
    meta_data["publication_date"] = publish_time.astimezone(timezone.get_default_timezone()).strftime("%Y-%m-%d %H:%M:%S.%f")

    #update catalogue service
    res = requests.post("{}/catalogue/api/records/".format(settings.CSW_URL),json=meta_data,auth=(settings.CSW_USER,settings.CSW_PASSWORD))
    res.raise_for_status()
    meta_data = res.json()
    with open("/tmp/{}.{}.json".format(layer.server.workspace.name,layer.layer_name),"wb") as f:
        json.dump(meta_data, f, indent=4)

