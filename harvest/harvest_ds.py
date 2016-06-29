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

from tablemanager.models import Input

logger = logging.getLogger(__name__)

class HarvestDatasource(object):
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
                t = threading.Thread(name="harvest_ds",target=self)
                t.setDaemon(True)
                t.start()
            else:
                #Repearted job
                self._repeated_harvest()
            return None
        else:
            #one time job
            return self._harvest_ds_time()



