import os
import re
from datetime import datetime
import pytz
import requests
import json

from django.utils import timezone
from django.conf import settings

from tablemanager.models import Publish
from harvest.models import Job
from borg_utils.resource_status import ResourceStatus,ResourceStatusManagement

migrate_info = {}
def migrate_all(debug=False):
    """
    Migrate all meta data to csw
    """
    for p in Publish.objects.all():
        migrate(p,debug)

    if debug: print "\n".join(["{}={}".format(key,migrate_info[key]) for key in migrate_info.iterkeys()])

empty_regex = re.compile("\s")
def migrate(p,debug=False):
    """
    Migrate one meta data to csw
    """
    if not hasattr(Publish(),"kmi_title"):
        #kmi title not found, migrate finished
        raise Exception("Migrate to csw has finished.")
    from tablemanager.models import Style

    if p.status != ResourceStatus.Enabled.name:
        #not enabled
        return
    if not p.job_id: 
        #not published
        return
    job = None
    try:
        job = Job.objects.get(pk=p.job_id)
    except:
        #job not exist
        pass
    print "Migrate {}".format(p.table_name)
    meta_data = p.builtin_metadata

    modify_time = None
    meta_data["auto_update"] = True
    if p.kmi_title and p.kmi_title.strip() and empty_regex.sub("",p.kmi_title) != empty_regex.sub("",meta_data.get("title") or ""):
        #has customized title
        meta_data["title"] = p.kmi_title
        meta_data["auto_update"] = False
        migrate_info[p.table_name] = migrate_info.get(p.table_name,"") + "title "

    if p.kmi_abstract and p.kmi_abstract.strip() and empty_regex.sub("",p.kmi_abstract) != empty_regex.sub("",meta_data.get("abstract") or ""):
        #has customized abstract
        meta_data["abstract"] = p.kmi_abstract
        meta_data["auto_update"] = False
        migrate_info[p.table_name] = migrate_info.get(p.table_name,"") + "abstract "

    if meta_data["auto_update"]:
        if p.input_table:
            for ds in p.input_table.datasource:
                if os.path.exists(ds):
                    input_modify_time = datetime.utcfromtimestamp(os.path.getmtime(ds)).replace(tzinfo=pytz.UTC)
                    if modify_time:
                        if modify_time < input_modify_time:
                            modify_time = input_modify_time
                    else:
                        modify_time = input_modify_time
                else:
                    modify_time = p.last_modify_time
        else:
            modify_time = p.last_modify_time
    else:
        modify_time = p.last_modify_time

    if job and job.finished:
        #job exist
        publish_time = job.finished
    else:
        #job not exist
        publish_time = timezone.now()
    insert_time = modify_time if modify_time <= publish_time else publish_time

    meta_data["insert_date"] = insert_time.astimezone(timezone.get_default_timezone()).strftime("%Y-%m-%d %H:%M:%S.%f")
    meta_data["modified"] = modify_time.astimezone(timezone.get_default_timezone()).strftime("%Y-%m-%d %H:%M:%S.%f")
    meta_data["publication_date"] = publish_time.astimezone(timezone.get_default_timezone()).strftime("%Y-%m-%d %H:%M:%S.%f")

    #get builtin style
    builtin_style = None
    for style in meta_data.get("styles",[]):
        if style["format"].lower() == "sld":
            builtin_style = style
            break
    if debug: 
        if builtin_style:
            print "Have builtin style"
        else:
            try:
                style = p.style_set.get(name="builtin")
                builtin_style = {"format":"SLD","content":style.sld.encode("base64")}
                print "Not found builtin style, but retrieve it from style table"
            except:
                print "Not found builtin style"
    #remove sld style file
    meta_data["styles"] = [style for style in meta_data.get("styles",[]) if style["format"].lower() != "sld"]

    #populate sld style files
    styles = {}
    builtin_style_added = False
    if builtin_style and p.default_style and p.default_style.name == "builtin":
        #builtin style is the default style
        builtin_style["default"] = True
        meta_data["styles"].append(builtin_style)
        builtin_style_added = True
        if debug: print "Add builtin style as default style"

    
    for style in p.style_set.exclude(name="builtin").filter(status="Enabled"):
        if not style.sld or not style.sld.strip():
            #sld is empty
            continue
        style_data = {"format":"SLD"}
        if style.name == "customized":
            if builtin_style:
                #has builtin style, this customized is the revised version of buitlin style, disable auto update
                meta_data["auto_update"] = False
                migrate_info[p.table_name] = migrate_info.get(p.table_name,"") + "customized-style "
                builtin_style_added = True
                if debug: print "Add customized style as revised default style"
            else:
                #no builtin style,change the name "customized"  to "initial"
                style_data["name"] = "initial"
                if debug: print "Add customized style as initial style"
        else:
            style_data["name"] = style.name
            if debug: print "Add {} style".format(style_data["name"])

        if style == p.default_style:
            style_data["default"] = True

        style_data["content"] = style.sld.encode("base64")
        meta_data["styles"].append(style_data)

    if not builtin_style_added and builtin_style:        
        meta_data["styles"].append(builtin_style)
        if debug: print "Add builtin style"

    #update catalogue service
    res = requests.post("{}/catalogue/api/records/".format(settings.CSW_URL),json=meta_data,auth=(settings.CSW_USER,settings.CSW_PASSWORD))
    try:
        res.raise_for_status()
    except:
        print "Failed.{}:{}".format(res.status_code,res.content)
        return

    meta_data = res.json()
    if debug:
        with open("/tmp/{}.{}.json".format(p.workspace.name,p.table_name),"wb") as f:
            json.dump(meta_data, f, indent=4)

