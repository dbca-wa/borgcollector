import os
import pytz
import time
import threading
import logging
import traceback

from datetime import datetime

from tablemanager.models import Input

logger = logging.getLogger(__name__)

class HarvestModifyTime(object):
    def __init__(self,check,check_interval,async=False):
        self._check = check
        self._check_interval = check_interval
        self._async = async

    def _harvest_ds_time(self):
        modify_time = None
        new_modify_time = None
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

    def _repeated_harvest(self):
        while(True):
            logger.info("Begin to havest datasource's last modify time.")
            try:
                self._harvest_ds_time()
                logger.info("End to havest datasource's last modify time.")
            except:
                logger.info("Failed to havest datasource's last modify time.{0}{1}".format(os.linesep,traceback.format_exc()))

            time.sleep(self._check_interval)

    def __call__(self):
        self._repeated_harvest();
 
    def harvest(self):
        if not self._check: return
        if self._check_interval > 0:
            if self._async:
                t = threading.Thread(name="harvest_ds_modify_time",target=self)
                t.setDaemon(True)
                t.start()
            else:
                #Repearted job
                self._repeated_harvest()
        else:
            #one time job
            self._harvest_ds_time()



