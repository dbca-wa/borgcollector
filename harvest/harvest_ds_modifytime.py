import os
import pytz
import time
import threading
import logging
import traceback

from datetime import datetime

from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone

from borg_utils.spatial_table import SpatialTable
from borg_utils.resource_status import ResourceStatus

from tablemanager.models import Input,Style

logger = logging.getLogger(__name__)

class HarvestModifyTime(object):
    def __init__(self,check,check_interval,async=False):
        self._check = check
        self._check_interval = check_interval
        self._async = async

    def _harvest_ds_time(self):
        modify_time = None
        new_modify_time = None
        counter = 0
        reload_style_counter = 0
        delete_style_counter = 0
        for i in Input.objects.filter(foreign_table__isnull=True):
            new_modify_time = None
            for ds in i.datasource:
                if os.path.exists(ds):
                    modify_time = datetime.utcfromtimestamp(os.path.getmtime(ds)).replace(tzinfo=pytz.UTC)
                    if new_modify_time:
                        if new_modify_time < modify_time:
                            new_modify_time = modify_time
                    else:
                        new_modify_time = modify_time
                else:
                    new_modify_time = None
                    break
            if i.ds_modify_time != new_modify_time:
                i.ds_modify_time = new_modify_time
                i.save(update_fields=["ds_modify_time"])
                counter += 1
                #try to reload style file for spatial publish
                for p in i.publish_set.all() :
                    if SpatialTable.check_normal(p.spatial_type):
                        continue

                    existing_builtin_style = None
                    builtin_style = None
                    try:
                        existing_builtin_style = p.style_set.get(name="builtin")
                    except ObjectDoesNotExist:
                        pass

                    builtin_style_file = p.builtin_style_file
                    if builtin_style_file:
                        #have builtin style
                        builtin_style = existing_builtin_style or Style(name="builtin",description=builtin_style_file,status=ResourceStatus.Enabled.name,publish=p)
                        builtin_style.last_modify_time = timezone.now()
                        with open(builtin_style_file) as f:
                            builtin_style.sld = f.read()
                        builtin_style.sld = builtin_style.format_style()
                        builtin_style.save()

                        #set the default style if it is not set.
                        if not p.default_style:
                            p.default_style = builtin_style
                            p.last_modify_time = timezone.now()
                            p.save(update_fields=["default_style","last_modify_time"])

                        reload_style_counter += 1
                    elif existing_builtin_style:
                        #no builtin style, but builtin style existed in db
                        #try set another default style if default style is the builtin style
                        if(p.default_style == existing_builtin_style):
                            try:
                                p.default_style = p.style_set.exclude(pk=existing_builtin_style.pk).filter(status=ResourceStatus.Enabled.name)[0]
                            except:
                                p.default_style = None
                            p.last_modify_time = timezone.now()
                            p.save(update_fields=["default_style","last_modify_time"])

                        existing_builtin_style.delete()
                        delete_style_counter += 1

        return (counter,reload_style_counter,delete_style_counter)

    def _repeated_harvest(self):
        while(True):
            logger.info("Begin to havest datasource's last modify time.")
            try:
                counter = self._harvest_ds_time()
                logger.info("{} datasources have been changed,{} builtin publish styles are reloaded, {} builtin publish styles are removed after latest harvesting.".format(*counter))
            except:
                logger.info("Failed to havest datasource's last modify time.{0}{1}".format(os.linesep,traceback.format_exc()))

            time.sleep(self._check_interval)

    def __call__(self):
        self._repeated_harvest();
 
    def harvest(self):
        if not self._check: return None
        if self._check_interval > 0:
            if self._async:
                t = threading.Thread(name="harvest_ds_modify_time",target=self)
                t.setDaemon(True)
                t.start()
            else:
                #Repearted job
                self._repeated_harvest()
            return None
        else:
            #one time job
            return self._harvest_ds_time()



