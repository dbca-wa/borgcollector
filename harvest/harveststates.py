import subprocess
import logging
import sys,traceback,os
import shutil
import re
import hashlib
from io import open

import hglib
import json
import requests

from django.db import transaction,models,connection
from django.utils import timezone
from django.conf import settings
from django.core.files import File
from django.template.loader import render_to_string
from django.conf import settings

from tablemanager.models import Publish,Workspace
from harvest.models import Job
from application.models import Application_Layers
from borg_utils.jobintervals import JobInterval
from borg_utils.singleton import SingletonMetaclass,Singleton
from borg_utils.borg_config import BorgConfiguration
from borg_utils.spatial_table import SpatialTable
from harvest.jobstates import JobStateOutcome,JobState,Failed,Completed

logger = logging.getLogger(__name__)


def file_md5(f):
    md5 = hashlib.md5()
    with open(f,"rb") as f:
        for chunk in iter(lambda: f.read(2048),b""):
            md5.update(chunk)
    return md5.hexdigest()

class HarvestStateOutcome(JobStateOutcome):
    """
    Declare all possible harvest job state outcome
    """
    up_to_date = "Up to date"
    def __new__(cls):
        raise Exception("Cannot instantiate.")

class HarvestState(JobState):
    """
    super class for harvest state.
    """
    _stateoutcome_cls = HarvestStateOutcome
    _abstract = True

    @classmethod
    def default_transition_dict(cls):
        return {
            HarvestStateOutcome.failed : cls,
            HarvestStateOutcome.internal_error : cls,
            HarvestStateOutcome.cancelled_by_custodian : PostFailed,
        }

class Waiting(HarvestState):
    """
    Job will be on this state after job is created and before cron job can execute it,
    """
    _name = "Waiting"
    _start_state = True

    @classmethod
    def transition_dict(cls):
        return {HarvestStateOutcome.succeed:BeforeRun,
                HarvestStateOutcome.up_to_date:PostCompleted}

    def execute(self,job,previous_state):
        """
        The job will continue to wait, if
        1. If the publish is still in a running harvest
        2. some dependent input is failed with the same batch id
        3. some dependent normalise is failed with the same batch id
        4. some dependent input is harvested by other jobs with different batch_id and still dependent by other jobs.
        """
        #import ipdb;ipdb.set_trace()
        if job.publish.running > 0:
            #havest job for the same publish is still running.
            return (HarvestStateOutcome.failed, "Harvest job for the same publish is still running.")
        else:
            result = None
            #if some inputs already failed, then the job will continue to wait
            for o in job.inputs:
                if o.job_batch_id and o.job_batch_id == job.batch_id:
                    #input is already executed by the job belonging to the same job batch
                    if o.job_status:
                        #execute successful
                        pass
                    else:
                        #execute failed
                        try:
                            j = Job.objects.get(pk = o.job_id)
                            if j.state in [Failed.instance().name,Completed.instance().name]:
                                #failed job already cancelled. current job can execute
                                pass
                            else:
                                #failed job is still running, current job must wait until the failed job execute successfully or cancelled
                                result = (HarvestStateOutcome.failed,o.job_message)
                                break
                        except:
                            #failed job can not found, current job can execute
                            pass
                elif o.job_batch_id:
                    #input is already executed by the job belonging to different job batch,
                    dependent_jobs = []
                    for j in Job.objects.filter(batch_id = o.job_batch_id).exclude(state__in = [Failed.instance().name,Completed.instance().name]):
                        for i in j.inputs:
                            if i.id == o.id:
                                #input is used by other running jobs, the current job will continue to wait
                                dependent_jobs.append({"id":i.id, "publish":i.name, "state": i.state})

                    if dependent_jobs:
                        #still have some running harvest job dependents on the inputed data. the current job must wait until all dependent job finished.
                        result = (HarvestStateOutcome.failed,"The dependent input {0} is still used by running jobs {1}".format(o.name, dependent_jobs))
                        break
                else:
                    #input is not executed before or no job is dependent on it.
                    pass

            if result:
                #already failed
                return result

            #if some normalise already failed, then the job will continue to wait
            for o in job.normalises:
                if o.job_batch_id and o.job_batch_id == job.batch_id:
                    #normalise is already executed
                    if o.job_status:
                        #executed successful
                        pass
                    else:
                        #executed failed
                        try:
                            j = Job.objects.get(pk = o.job_id)
                            if j.state in [Failed.instance().name,Completed.instance().name]:
                                #failed job already cancelled. current job can execute
                                pass
                            else:
                                #failed job is still running, current job must wait until the failed job execute successfully or cancelled
                                result = (HarvestStateOutcome.failed,o.job_message)
                                break
                        except:
                            #failed job can not found, current job can execute
                            pass
                else:
                    #normalise is not executed before
                    pass

            if not result:
                result = (HarvestStateOutcome.succeed,None)

                if job.publish.is_up_to_date(job):
                    #publis is up to date, no need to run.
                    if (job.is_manually_created):
                        result = (HarvestStateOutcome.succeed, "Publish is up to date, but forced by custodian")
                    else:
                        return (HarvestStateOutcome.up_to_date,"Publish is up to date, no need to publish again.")

            return result

class BeforeRun(HarvestState):
    """
    This is a intermediate state for pre processing
    """
    _name = "Before Run"
    _volatile_state = True
    _cancellable = False

    @classmethod
    def transition_dict(cls):
        return {HarvestStateOutcome.succeed:Importing}

    def execute(self,job,previous_state):
        """
        Do some pre processing jobs
        1. Increase "running" and decrease "waiting" for publish
        2. Set publish's "job_end_time" to None
        3. Set job's "launched"
        """
        with transaction.atomic():
            job.publish.running = models.F("running") + 1
            job.publish.waiting = models.F("waiting") - 1
            job.publish.job_create_time = job.created
            job.publish.job_start_time = timezone.now()
            job.publish.job_end_time = None
            job.publish.save(update_fields=['running','waiting','job_create_time','job_start_time','job_end_time'])
            #set the job launch time
            job.launched = timezone.now()
            job.save(update_fields=['launched'])

        return (HarvestStateOutcome.succeed,None)

class ImportAndNormalizeState(HarvestState):
    """
    The state is a abstract super class for all import and normalize states
    """
    _abstract = True

    def _input_tables(self,job,previous_state):
        """
        return a collection of tables which act as the input for the current state
        """
        raise NotImplementedError("The method '_table_collection' is not implemented.")

    def _execute(self,job,previous_state,input_table):
        """
        perform the logic on input table
        """
        raise NotImplementedError("The method '_execute' is not implemented.")

    def _pre_execute(self,job,previous_state):
        """
        perfrom before execute
        """
        pass

    def execute(self,job,previous_state):
        """
        igore the input if it is already imported with the same batchid ,
        failed if some input is failed with the same batchid.
        """
        self._pre_execute(job,previous_state)
        result = None
        job_state = None
        #go through all outdated input tables to import.
        for o in self._input_tables(job,previous_state):
            if o.job_batch_id and o.job_batch_id == job.batch_id:
                #input table already executed by a job belonging to the same batch
                job_state = HarvestState.get_jobstate(o.job_state)
                if job_state == self:
                    #this input table is on the same state.
                    if o.job_status:
                        #already executed successfully
                        continue
                    elif o.job_id == job.id:
                        #faild by the same job. execute it again.
                        pass
                    else:
                        #failed by other job, check whether the failed job is still running or finished.
                        try:
                            j = Job.objects.get(pk=o.job_id)
                            if j.state in [Failed.instance().name,Completed.instance().name]:
                                #failed job has been failed or completed, current job can execute again
                                pass
                            else:
                                #failed job is still running, current job must wait until the failed job cancelled or execute successfully.
                                result = (HarvestStateOutcome.failed,o.job_message)
                                break
                        except:
                            #failed job can not found, current job can execute again.
                            pass
                elif self.is_upstate(job_state):
                    #this input table is on a state after the current state, the current state should have been executed successfully.
                    continue
                else:
                    #this input table is on a state before the current state
                    if o.job_status:
                        #execute the current state
                        pass
                    else:
                        #In general, it is impossible to reach here.
                        #because the logic can go here only when the previous state has been executed successfully.
                        result = (HarvestStateOutcome.failed,o.job_message)
                        break
            #execute
            try:
                result = self._execute(job,previous_state,o)
                if result and result[0] != JobStateOutcome.succeed:
                    #failed
                    o.job_status = False
                    o.job_message = result[1]
                    break
                else:
                    #update the status in input table to prevent other job execute it again
                    o.job_status = True
                    o.job_message = 'Succeed'
            except:
                result = (HarvestStateOutcome.failed, self.get_exception_message())
                #update the status in input table to prevent other job execute it again
                o.job_status = False
                o.job_message = result[1]
                break
            finally:
                o.job_state = self.name
                o.job_batch_id = job.batch_id
                o.job_id = job.id
                o.save(update_fields=['job_state','job_status','job_message','job_batch_id','job_id'])

        if not result:
            result = (HarvestStateOutcome.succeed,None)

        return result

class Importing(ImportAndNormalizeState):
    """
    The state is for importing the data from data source to import schema
    """
    _name = "Importing"
    _interactive_if_failed = False

    @classmethod
    def transition_dict(cls):
        return {HarvestStateOutcome.succeed:GeneratingRowID}

    def _input_tables(self,job,previous_state):
        """
        return a collection of tables which act as the input for the current state
        """
        return [i for i in job.inputs if not i.is_up_to_date(job,previous_state.is_error_state)]

    def _execute(self,job,previous_state,input_table):
        """
        perform the logic on input table
        """
        return input_table.execute(job.id)

    def _pre_execute(self,job,previous_state):
        """
        perfrom before execute
        """
        return
        """
        #import ipdb;ipdb.set_trace()
        if previous_state.is_error_state:
            #if failed before, force to import and normalise all data.
            with transaction.atomic():
                for o in self.inputs:
                    o.job_batch_id = None
                    o.job_id = None
                    o.job_state = None
                    o.job_status = None
                    o.job_message = None
                    o.compatible_job_id = None
                    o.compatible_job_batch_id = None
                    o.save(update_fields=['job_batch_id','job_id','job_status','job_message','compatible_job_id','compatible_job_batch_id'])
                for o in job.normalises:
                    o.job_batch_id = None
                    o.job_id = None
                    o.job_status = None
                    o.job_message = None
                    o.save(update_fields=['job_batch_id','job_id','job_status','job_message'])
        """


class GeneratingRowID(ImportAndNormalizeState):
    """
    The state is for generating a row id for data source which has not a primary key columns.
    """
    _name = "Generating RowID"
    _interactive_if_failed = True

    @classmethod
    def transition_dict(cls):
        return {HarvestStateOutcome.succeed:Normalizing,HarvestStateOutcome.failed:Importing}

    def _input_tables(self,job,previous_state):
        """
        return a collection of tables which act as the input for the current state
        """
        return [i for i in job.inputs if i.job_id == job.id and i.generate_rowid]

    def _execute(self,job,previous_state,input_table):
        input_table.populate_rowid()


class Normalizing(ImportAndNormalizeState):
    """
    The state is for normalizing the data from import schema to normal_form schema and performing all required validation
    """
    _name = "Normalizing"
    _interactive_if_failed = True

    @classmethod
    def transition_dict(cls):
        return {HarvestStateOutcome.succeed:Publishing,HarvestStateOutcome.failed:Importing}

    def _input_tables(self,job,previous_state):
        """
        return a collection of tables which act as the input for the current state
        """
        return [n for n in job.normalises if not n.is_up_to_date(job)]

    def _execute(self,job,previous_state,input_table):
        """
        perform the logic on input table
        """
        input_table.execute()

class Publishing(HarvestState):
    """
    The state is for publishing the data from import schema and normal form schema into  publish schema
    """
    _name = "Publishing"

    @classmethod
    def transition_dict(cls):
        return {HarvestStateOutcome.succeed:GenerateLayerAccessRule}
        #return {HarvestStateOutcome.succeed:PullUserList}

    def execute(self,job,previous_state):
        """
        publish the import data
        """
        result = None
        o = job.publish
        #import ipdb; ipdb.set_trace()
        try:
            o.execute()
            #update the status in input table to prevent other job execute it again
            o.job_status = True
            o.job_message = 'Succeed'
        except:
            result = (HarvestStateOutcome.failed, self.get_exception_message())
            #update the status in input table to prevent other job execute it again
            o.job_status = False
            o.job_message = result[1]
        finally:
            o.job_state = self.name
            o.job_batch_id = job.batch_id
            o.job_id = job.id
            o.pgdump_file = None
            o.style_file = None
            o.save(update_fields=['job_batch_id','job_id','job_status','job_message','job_state','pgdump_file','style_file'])

        if not result:
            result = (HarvestStateOutcome.succeed,None)

        return result

class PullUserList(HarvestState):
    """
    This state is for pulling the user/group list as JSON from an URL and
    converting it to a SQL script.

    The list should be formatted as follows:
    {
        "user1": ["group1", "group2", ...],
        "user2": ["group1", "group3", ...],
        ...
    }
    """
    _name = "Pull User List"

    @classmethod
    def transition_dict(cls):
        return {HarvestStateOutcome.succeed:GenerateLayerAccessRule}

    def execute(self, job, previous_state):
        if BorgConfiguration.USERLIST.startswith("http"):
            # Load JSON user/group dump from URL
            try:
                data = request.get(BorgConfiguration.USERLIST,
                                auth=requests.auth.HTTPBasicAuth(
                                    BorgConfiguration.USERLIST_USERNAME,
                                    BorgConfiguration.USERLIST_PASSWORD
                                ))
            except request.exceptions.RequestException as e:
                return (JobStateOutcome.failed, "Failed to download user list: {}".format(e))

            if data.status_code != 200:
                return (JobStateOutcome.failed, "GET {} returned HTTP status {}".format(BorgConfiguration.USERLIST, data.status_code))

            user_data_raw = data.content
        else:
            try:
                user_data_raw = open(BorgConfiguration.USERLIST, "rb").read()
            except:
                return (JobStateOutcome.failed, "Opening path {} failed".format(BorgConfiguration.USERLIST))

        user_data = json.loads(user_data_raw.decode("utf-8-sig"))

        # Sort data alphabetically, order it for the template
        keys = user_data.keys()
        keys.sort()
        users = [{"name": k, "groups": user_data[k]} for k in keys]
        roles = set()
        for g in user_data.values():
            roles.update(g)

        # Generate user data SQL through template
        result = render_to_string("slave_roles.sql", {"users": users, "roles": roles})

        # Write output SQL file, commit + push
        output_filename = os.path.join(BorgConfiguration.BORG_STATE_REPOSITORY, "slave_roles.sql")
        with open(output_filename, "w", encoding="utf-8") as output:
            output.write(result)

        # Try and commit to repository, if no changes then continue
        hg = hglib.open(BorgConfiguration.BORG_STATE_REPOSITORY)
        try:
            hg.commit(include=output_filename, user=BorgConfiguration.BORG_STATE_USER, message="{} - roles updated".format(job.publish.job_batch_id))
        except hglib.error.CommandError as e:
            if e.out != "nothing changed\n":
                return (HarvestStateOutcome.failed, self.get_exception_message())
        finally:
            hg.close()

        return (JobStateOutcome.succeed, None)

class GenerateLayerAccessRule(HarvestState):
    """
    This state is for generating layer access rules
    """
    _name = "Generate Layer Access Rules"

    @classmethod
    def transition_dict(cls):
        return {HarvestStateOutcome.succeed:DumpFullData}

    def execute(self, job, previous_state):
        if not job.publish.workspace.publish_channel.sync_geoserver_data:
            #no need to update geoserver
            return (JobStateOutcome.succeed, None)

        workspaces = Workspace.objects.filter(publish_channel=job.publish.workspace.publish_channel).order_by('name')

        # Generate user data SQL through template
        latest_data = render_to_string("layers.properties", {"workspaces": workspaces})
        old_data = None
        output_filename = os.path.join(BorgConfiguration.BORG_STATE_REPOSITORY,job.publish.workspace.publish_channel.name, "layers.properties")
        #create dir if required
        if os.path.exists(output_filename):
            with open(output_filename,"rb") as output_file:
                old_data = output_file.read()
        elif not os.path.exists(os.path.dirname(output_filename)):
            os.makedirs(os.path.dirname(output_filename))

        if old_data and old_data == latest_data:
            #layer access rule not changed
            return (JobStateOutcome.succeed, None)

        # Write output layer access rule, commit + push
        with open(output_filename, "wb") as output:
            output.write(latest_data)

        # Try and commit to repository, if no changes then continue
        hg = hglib.open(BorgConfiguration.BORG_STATE_REPOSITORY)
        try:
            hg.commit(include=[output_filename],addremove=True, user=BorgConfiguration.BORG_STATE_USER, message="{} - layer access rules updated".format(job.publish.job_batch_id))
        except hglib.error.CommandError as e:
            if e.out != "nothing changed\n":
                return (HarvestStateOutcome.failed, self.get_exception_message())
        finally:
            hg.close()

        return (JobStateOutcome.succeed, None)

class DumpFullData(HarvestState):
    """
    The state is for dumping full data into download folder
    """
    _name = "Dump Full Data"

    def __init__(self):
        """
        load settings from djago.conf.settings
        """
        self.database = settings.DATABASES["default"]
        self.env = os.environ.copy()
        self.dump_cmd = ["pg_dump", "-h", self.database["HOST"], "-d", self.database["NAME"], "-U", self.database["USER"], "-b", "-E", "utf-8", "-F", "t", "-w", "-O"]
        if 'PASSWORD' in self.database and  self.database['PASSWORD'].strip():
            self.env["PGPASSWORD"] = self.database["PASSWORD"]
        if self.database["PORT"]:
            self.dump_cmd += ["-p", str(self.database["PORT"])]

        #import ipdb; ipdb.set_trace()
        if not os.path.exists(BorgConfiguration.FULL_DATA_DUMP_DIR):
            #path does not exist, create it
            os.makedirs(BorgConfiguration.FULL_DATA_DUMP_DIR)


    @classmethod
    def transition_dict(cls):
        return {HarvestStateOutcome.succeed:ConfigGeoServer}

    def execute(self,job,previous_state):
        """
        dump the full table data into download folder
        """
        #create the dir if required
        if not os.path.exists(job.dump_dir):
            #dump dir does not exist, create it
            os.makedirs(job.dump_dir)

        file_name = job.publish.table_name + ".tar"
        dump_file = os.path.join(job.dump_dir,file_name)
        cmd = self.dump_cmd + ["-t", job.publish.workspace.publish_data_schema + "." + job.publish.table_name, "-f", dump_file]

        cursor=connection.cursor()
        if not previous_state.is_error_state:
            #table with same name maybe published by previous job. drop it if have.
            cursor.execute('drop table if exists {0}.{1} cascade'.format(job.publish.workspace.publish_data_schema,job.publish.table_name))
        #move table to publish schema for dump
        cursor.execute('alter table {0}.{1} set schema {2}'.format(job.publish.workspace.schema,job.publish.table_name,job.publish.workspace.publish_data_schema))
        try:
            #import ipdb;ipdb.set_trace()
            output = subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE, env=self.env).communicate()
            logger.debug("execute ({0})\nstdin:{1}\nstdout:{2}".format(cmd,output[0],output[1]))
        finally:
            #move table back to original schema
            cursor.execute('alter table {0}.{1} set schema {2}'.format(job.publish.workspace.publish_data_schema,job.publish.table_name,job.publish.workspace.schema))

        if output[1].strip() :
            return (HarvestStateOutcome.failed,output[1])
        else:
            #import ipdb; ipdb.set_trace()
            with transaction.atomic():
                p = job.publish
                p.pgdump_file.save(file_name,File(open(dump_file,'rb')),False)
                job.pgdump_file = p.pgdump_file
                p.save(update_fields=['pgdump_file'])
                job.save(update_fields=['pgdump_file'])
            return (HarvestStateOutcome.succeed,None)

class ConfigGeoServer(HarvestState):
    """
    The state is for configuring the geo server, and save the configuration file into file system.
    """
    _name = "Configure GeoServer"

    @classmethod
    def transition_dict(cls):
        return {HarvestStateOutcome.succeed:SubmitToVersionControl}

    def get_style_file(self,job,previous_state):
        """
        find and copy the style file to the local repository
        """
        sld = job.publish.feature_style

        if sld:
            if not os.path.exists(job.dump_dir):
                #dump dir does not exist, create it
                os.makedirs(job.dump_dir)

            file_name = job.publish.table_name + ".sld"
            dest_file = os.path.join(job.dump_dir,file_name)
            with open(dest_file,"wb") as f:
                f.write(sld)

            with transaction.atomic():
                p = job.publish
                p.style_file.save(file_name,File(open(dest_file,'rb')),False)
                job.style_file = p.style_file
                p.save(update_fields=['style_file'])
                job.save(update_fields=['style_file'])
        else:
            p = job.publish
            p.style_file = None
            p.save(update_fields=['style_file'])

    def execute(self,job,previous_state):
        # TBD
        self.get_style_file(job,previous_state)
        return (HarvestStateOutcome.succeed,None)

class SubmitToVersionControl(HarvestState):
    """
    The state is for submiting the harvest information to version control system and all slave server can obtain the harvest information and apply all the changes
    """
    _name = "Submit to Version Control Server"
    _cancellable = False

    @classmethod
    def transition_dict(cls):
        return {HarvestStateOutcome.succeed:PostCompleted}

    def execute(self,job,previous_state):
        p = job.publish

        #import ipdb;ipdb.set_trace()
        # Write JSON output file
        json_out = {}
        json_out["name"] = p.table_name
        json_out["job_id"] = job.id
        json_out["job_batch_id"] = job.batch_id
        json_out["schema"] = p.workspace.publish_schema
        json_out["data_schema"] = p.workspace.publish_data_schema
        json_out["outdated_schema"] = p.workspace.publish_outdated_schema
        json_out["workspace"] = p.workspace.name
        json_out["channel"] = p.workspace.publish_channel.name
        json_out["spatial_data"] = SpatialTable.check_spatial(job.publish.spatial_type)
        json_out["spatial_type"] = SpatialTable.get_spatial_type_desc(job.publish.spatial_type)
        json_out["sync_postgres_data"] = p.workspace.publish_channel.sync_postgres_data
        json_out["sync_geoserver_data"] = p.workspace.publish_channel.sync_geoserver_data
        json_out["dump_path"] = "{}{}".format(BorgConfiguration.MASTER_PATH_PREFIX, p.pgdump_file.path)
        json_out["data_md5"] = file_md5(p.pgdump_file.path)
        json_out["preview_path"] = "{}{}".format(BorgConfiguration.MASTER_PATH_PREFIX, settings.PREVIEW_ROOT)
        json_out["applications"] = ["{0}:{1}".format(o.application,o.order) for o in Application_Layers.objects.filter(publish=p)]
        json_out["title"] = p.title
        json_out["abstract"] = p.abstract
        json_out["auth_level"] = p.workspace.auth_level
        json_out["publish_time"] = timezone.localtime(timezone.now()).strftime("%Y-%m-%d %H:%M:%S.%f")

        if p.geoserver_setting:
            json_out["geoserver_setting"] = json.loads(p.geoserver_setting)
        if p.workspace.publish_channel.sync_geoserver_data and p.style_file:
            json_out["style_path"] = "{}{}".format(BorgConfiguration.MASTER_PATH_PREFIX, p.style_file.path)
            json_out["style_md5"] = file_md5(p.style_file.path)

        #bbox
        if SpatialTable.check_spatial(job.publish.spatial_type):
            cursor=connection.cursor()
            st = SpatialTable.get_instance(cursor,p.workspace.schema,p.table_name,True)
            if st.geometry_columns:
                json_out["bbox"] = st.geometry_columns[0][2]
            elif st.geography_columns:
                json_out["bbox"] = st.geography_columns[0][2]

        file_name = p.output_filename_abs('publish')
        #create the dir if required
        if not os.path.exists(os.path.dirname(file_name)):
            os.makedirs(os.path.dirname(file_name))

        with open(file_name, "wb") as output:
            json.dump(json_out, output, indent=4)

        # Try and add file to repository, if no changes then continue
        hg = hglib.open(BorgConfiguration.BORG_STATE_REPOSITORY)
        try:
            hg.add(files=[file_name])

            #remove meta json file and empty gwc json file
            files =[p.output_filename_abs(action) for action in ['meta','empty_gwc'] ]
            files =[ f for f in files if os.path.exists(f)]
            if files:
                hg.remove(files=files)

            files.append(file_name)

            hg.commit(include=files,addremove=True, user=BorgConfiguration.BORG_STATE_USER, message="{} - updated {}.{}".format(p.job_batch_id, p.workspace.name, p.name))
        except hglib.error.CommandError as e:
            if e.out != "nothing changed\n":
                return (HarvestStateOutcome.failed, self.get_exception_message())
        finally:
            hg.close()

        return (HarvestStateOutcome.succeed, None)

class PostCompleted(HarvestState):
    """
    The state is a intermediate state and exists for post processing.
    """
    _name = "Post Completed"
    _volatile_state = True
    _cancellable = False

    @classmethod
    def transition_dict(cls):
        return {HarvestStateOutcome.succeed:Completed}

    def execute(self,job,previous_state):
        """
        Do some post processing jobs
        1. push all the changes to repository
        2. Increase "completed" and decrease "running" for publish
        3. set publish's "job_end_time"
        4. set job's "finised"
        """
        if previous_state != Waiting.instance():
            #push the changes to repository
            #import ipdb;ipdb.set_trace()
            hg = hglib.open(BorgConfiguration.BORG_STATE_REPOSITORY)
            try:
                if not hg.push(ssh=BorgConfiguration.BORG_STATE_SSH):
                    logger.warning("push (job_id={0}, job_batch_id={1}, publish={2}) to repository failed.".format(job.id,job.batch_id,job.publish.name))

            except hglib.error.CommandError:
                return (HarvestStateOutcome.failed, self.get_exception_message())
            finally:
                hg.close()

        with transaction.atomic():
            p = job.publish
            p.job_end_time = timezone.now()
            p.pending_actions = None
            if previous_state == Waiting.instance():
                p.waiting = models.F("waiting") - 1
            else:
                p.running = models.F("running") - 1
                p.completed = models.F("completed") + 1

            if previous_state == Waiting.instance():
                p.save(update_fields=['job_end_time','waiting','pending_actions'])
            else:
                p.save(update_fields=['job_end_time','running','completed','pending_actions'])

            job.finished = timezone.now()
            job.save(update_fields=['finished'])

        return (HarvestStateOutcome.succeed,None)

class PostFailed(HarvestState):
    """
    The state is a intermediate state and exists for post processing.
    """
    _name = "Post Failed"
    _volatile_state = True
    _cancellable = False

    @classmethod
    def transition_dict(cls):
        return {HarvestStateOutcome.succeed:Failed}

    def execute(self,job,previous_state):
        """
        Do some post processing jobs
        1. Increase "completed" and decrease "running" or "waiting" for publish
        2. set publish's "job_end_time"
        3. set job's "finised"
        """
        with transaction.atomic():
            p = job.publish
            p.job_end_time = timezone.now()

            if previous_state in ( Waiting.instance(),Waiting._failed_state.instance(),Waiting._internal_error_state.instance()):
                p.waiting = models.F("waiting") - 1
            else:
                p.running = models.F("running") - 1
            p.failed = models.F("failed") + 1

            if previous_state in ( Waiting.instance(),Waiting._failed_state.instance(),Waiting._internal_error_state.instance()):
                p.save(update_fields=['job_end_time','waiting','failed'])
            else:
                p.save(update_fields=['job_end_time','running','failed'])

            job.finished = timezone.now()
            job.save(update_fields=['finished'])

        return (HarvestStateOutcome.succeed,None)

