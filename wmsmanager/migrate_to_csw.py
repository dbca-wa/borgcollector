import os
import re
from datetime import datetime
import pytz
import requests
import json

from django.utils import timezone
from django.conf import settings

from wmsmanager.models import WmsLayer
from borg_utils.resource_status import ResourceStatus

migrate_info = {}
def migrate_all(debug=False):
    """
    Migrate all meta data to csw
    """
    for layer in WmsLayer.objects.filter(status__in=[ResourceStatus.Published.name,ResourceStatus.CascadePublished.name,ResourceStatus.Updated.name]):
        migrate(layer,debug)

    if debug: print "\n".join(["{}={}".format(key,migrate_info[key]) for key in migrate_info.iterkeys()])

empty_regex = re.compile("\s")
def migrate(layer,debug=False):
    """
    Migrate one meta data to csw
    """
    if not hasattr(layer,"kmi_title"):
        #kmi title not found, migrate finished
        raise Exception("Migrate to csw has finished.")

    print "Migrate {}".format(layer.kmi_name)
    meta_data = layer.builtin_metadata
    meta_data["auto_update"] = True
    if layer.kmi_title and layer.kmi_title.strip() and empty_regex.sub("",layer.kmi_title) != empty_regex.sub("",meta_data.get("title") or ""):
        #has customized title
        meta_data["title"] = layer.kmi_title
        meta_data["auto_update"] = False
        migrate_info[layer.kmi_name] = migrate_info.get(layer.kmi_name,"") + "title "

    if layer.kmi_abstract and layer.kmi_abstract.strip() and empty_regex.sub("",layer.kmi_abstract) != empty_regex.sub("",meta_data.get("abstract") or ""):
        #has customized abstract
        meta_data["abstract"] = layer.kmi_abstract
        meta_data["auto_update"] = False
        migrate_info[layer.kmi_name] = migrate_info.get(layer.kmi_name,"") + "abstract "

    modify_time = layer.last_modify_time
    publish_time = layer.last_publish_time
    insert_time = modify_time if modify_time and modify_time <= publish_time else publish_time
    meta_data["insert_date"] = insert_time.astimezone(timezone.get_default_timezone()).strftime("%Y-%m-%d %H:%M:%S.%f")
    meta_data["modified"] = modify_time.astimezone(timezone.get_default_timezone()).strftime("%Y-%m-%d %H:%M:%S.%f") if modify_time else None
    meta_data["publication_date"] = publish_time.astimezone(timezone.get_default_timezone()).strftime("%Y-%m-%d %H:%M:%S.%f")

    #update catalogue service
    res = requests.post("{}/catalogue/api/records/".format(settings.CSW_URL),json=meta_data,auth=(settings.CSW_USER,settings.CSW_PASSWORD))
    try:
        res.raise_for_status()
    except:
        print "Failed.{}:{}".format(res.status_code,res.content)
        return

    meta_data = res.json()
    with open("/tmp/{}.{}.json".format(layer.server.workspace.name,layer.kmi_name),"wb") as f:
        json.dump(meta_data, f, indent=4)


def update_all():
    """
    Migrate all meta data to csw
    """
    file_name = "/tmp/update_wms_in_csw.sql"
    with open(file_name,"wb") as f:
        for layer in WmsLayer.objects.filter(status__in=[ResourceStatus.Published.name,ResourceStatus.CascadePublished.name,ResourceStatus.Updated.name]):
            update(layer,f)

def update(layer,f):
    """
    Migrate one meta data to csw
    """
    print "Update {}".format(layer.kmi_name)
    meta_data = {}
    modify_time = layer.last_modify_time
    publish_time = layer.last_publish_time
    insert_time = publish_time
    meta_data["insert_date"] = insert_time.astimezone(timezone.get_default_timezone()).strftime("%Y-%m-%d %H:%M:%S.%f")
    meta_data["modified"] = modify_time.astimezone(timezone.get_default_timezone()).strftime("%Y-%m-%d %H:%M:%S.%f") if modify_time else None
    meta_data["publication_date"] = publish_time.astimezone(timezone.get_default_timezone()).strftime("%Y-%m-%d %H:%M:%S.%f")

    sql = "UPDATE catalogue_record SET {} WHERE identifier = '{}';\n".format(" , ".join(["{}={}".format(k,"'{}'".format(v) if v else 'null') for k,v in meta_data.iteritems()]),"{}:{}".format(layer.server.workspace.name,layer.kmi_name))

    f.write(sql)
