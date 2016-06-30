import json
import base64
import os
import logging
import traceback
import time
from datetime import timedelta

from restless.dj import DjangoResource
from restless.resources import skip_prepare

from django.conf.urls import  url
from django.template import Context, Template
try:
    from django.utils.encoding import smart_text
except ImportError:
    from django.utils.encoding import smart_unicode as smart_text

from django.contrib import auth
from django.utils import timezone

from harvest.models import Job
from tablemanager.models import Publish,Workspace,Input,DataSource
from wmsmanager.models import WmsLayer
from harvest.jobstatemachine import JobStatemachine
from monitor.models import SlaveServer,PublishSyncStatus

from borg_utils.hg_batch_push import try_set_push_owner, try_clear_push_owner, try_push_to_repository
from borg_utils.jobintervals import JobInterval
from borg_utils.borg_config import BorgConfiguration
from borg_utils.resource_status import ResourceStatus
from harvest.jobstates import Completed

logger = logging.getLogger(__name__)

class BasicHttpAuthMixin(object):
    """
    :py:class:`restless.views.Endpoint` mixin providing user authentication
    based on HTTP Basic authentication.
    """

    def authenticate(self, request):
        if 'HTTP_AUTHORIZATION' in request.META:
            authdata = request.META['HTTP_AUTHORIZATION'].split()
            if len(authdata) == 2 and authdata[0].lower() == "basic":
                try:
                    raw = authdata[1].encode('ascii')
                    auth_parts = base64.b64decode(raw).split(b':')
                except:
                    return
                try:
                    uname, passwd = (smart_text(auth_parts[0]),
                        smart_text(auth_parts[1]))
                except DjangoUnicodeDecodeError:
                    return

                user = auth.authenticate(username=uname, password=passwd)
                if user is not None and user.is_active:
                    # We don't user auth.login(request, user) because
                    # may be running without session
                    request.user = user
        return request.user.is_authenticated()


class JobResource(DjangoResource,BasicHttpAuthMixin):
    def is_authenticated(self):
        if self.request.user.is_authenticated():
            return True
        else:
            return self.authenticate(self.request)

    @staticmethod
    def urls():
        return [
            url(r'^jobs/$',JobResource.as_list(),name='create_job'),
        ]
     
    @skip_prepare
    def create(self):
        job_batch_id = JobInterval.Triggered.job_batch_id()
        resp = {"status":True}
        result = None
        for name in self.data.get('publishes') or []:
            resp[name] = {}
            result = JobStatemachine.create_job_by_name(name,JobInterval.Triggered,job_batch_id)
            if result[0]:
                resp[name]["status"] = True
                resp[name]["job_id"] = result[1]
                resp[name]["message"] = "Succeed"
            else:
                resp["status"] = False
                resp[name]["status"] = False
                resp[name]["message"] = result[1]
        return resp

class MetaResource(DjangoResource,BasicHttpAuthMixin):
    def is_authenticated(self):
        if self.request.user.is_authenticated():
            return True
        else:
            return self.authenticate(self.request)

    @staticmethod
    def urls():
        return[
            url(r'^metajobs/$',MetaResource.as_list(),name='publish_meta'),
        ]
     
    @skip_prepare
    def create(self):
        resp = {"status":True}
        result = None
        try_set_push_owner("meta_resource")
        try:
            for layer in self.data.get('layers') or []:
                workspace,name = layer.split(":")
                resp[layer] = {}
                #get the workspace object
                try:
                    workspace = Workspace.objects.get(name=workspace)
                except Workspace.DoesNotExist:
                    #workspace does not exist
                    resp["status"] = False
                    resp[layer]["status"] = False
                    resp[layer]["message"] = "Workspace does not exist.".format(name)
                    continue
                    
                try:
                    #try to locate it from publishs, and publish the meta data if found
                    pub = Publish.objects.get(workspace=workspace,name=name)
                    try:
                        pub.publish_meta_data()
                        resp[layer]["status"] = True
                        resp[layer]["message"] = "Succeed."
                    except Exception as e:
                        resp["status"] = False
                        resp[layer]["status"] = False
                        resp[layer]["message"] = "Publish meta data failed!{}".format(e)
                        continue
                except Publish.DoesNotExist:
                    #not a publish object, try to locate it from wms layers, and publish it if found
                    try:
                        wmslayer = WmsLayer.objects.get(server__workspace=workspace,kmi_name=name)
                        try:
                            wmslayer.publish()
                            resp[layer]["status"] = True
                            resp[layer]["message"] = "Succeed."
                        except Exception as e:
                            resp["status"] = False
                            resp[layer]["status"] = False
                            resp[layer]["message"] = "Publish wms layer failed!{}".format(e)
                            continue
                    except WmsLayer.DoesNotExist:
                        #layer does not exist,
                        resp["status"] = False
                        resp[layer]["status"] = False
                        resp[layer]["message"] = "Does not exist.".format(name)
                        continue

            #push all files into repository at once.
            try:
                try_push_to_repository('meta_resource',enforce=True)
            except Exception as e:
                #push failed, set status to false, and proper messages for related layers.
                resp["status"] = False
                for layer in self.data.get('layers') or []:
                    if resp[layer]["status"]:
                        #publish succeed but push failed
                        resp[layer]["status"] = False
                        resp[layer]["message"] = "Push to repository failed!{}".format(e)
        finally:
            try_clear_push_owner("meta_resource")
            
        return resp


class MudmapResource(DjangoResource,BasicHttpAuthMixin):
    def is_authenticated(self):
        if self.request.user.is_authenticated():
            return True
        else:
            return self.authenticate(self.request)

    @staticmethod
    def urls():
        return [
            url(r'^mudmap/(?P<application>[a-zA-Z0-9_\-]+)/(?P<name>[a-zA-Z0-9_\-]+)/(?P<user>[a-zA-Z0-9_\-\.]+@[a-zA-Z0-9\-]+(\.[a-zA-Z0-9\-]+)+)/$',MudmapResource.as_list(),name='publish_mudmap'),
        ]
     
    @skip_prepare
    def create(self,application,name,user, *args, **kwargs):
        try:
            json_data = self.data
            application = application.lower()
            name = name.lower()
            user = user.lower()
            #prepare the folder
            folder = os.path.join(BorgConfiguration.MUDMAP_HOME,application,name)
            if os.path.exists(folder):
                if not os.path.isdir(folder):
                    raise "{} is not a folder".format(folder)
            else:
                os.makedirs(folder)
            #write the json file into folder
            file_name = os.path.join(folder,"{}.json".format(user))
            with open(file_name,"wb") as f:
                f.write(json.dumps(self.data))
            #get list of geojson files
            json_files = [os.path.join(folder,f) for f in os.listdir(folder) if f[-5:] == ".json"]
            
            job_id = self._publish(application,name,user)
            if job_id:
                return {"jobid":job_id}
        except:
            logger.error(traceback.format_exc())
            raise
    
    def _publish(self,application,name,user):
        #get list of geojson files
        folder = os.path.join(BorgConfiguration.MUDMAP_HOME,application,name)
        if os.path.exists(folder):
            json_files = [os.path.join(folder,f) for f in os.listdir(folder) if f[-5:] == ".json"]
        else:
            json_files = None
        #generate the source data
        data_source = DataSource.objects.get(name="mudmap")
        input_name = "{}_{}".format(application,name)
        mudmap_input = None
        if json_files:
            #create or update input 
            try:
                mudmap_input = Input.objects.get(name=input_name)
            except Input.DoesNotExist:
                mudmap_input = Input(name=input_name,data_source=data_source,generate_rowid=False)

            source = Template(data_source.vrt).render(Context({"files":json_files,"self":mudmap_input}))
            mudmap_input.source = source
            mudmap_input.full_clean(exclude=["data_source"])
            if mudmap_input.pk:
                mudmap_input.last_modify_time = timezone.now()
                mudmap_input.save(update_fields=["source","last_modify_time","info"])
            else:
                mudmap_input.save()

            #get or create publish
            mudmap_publish = None
            try:
                mudmap_publish = Publish.objects.get(name=input_name)
            except Publish.DoesNotExist:
                #not exist, create it
                workspace = Workspace.objects.get(name="mudmap")
                mudmap_publish = Publish(
                    name=input_name,
                    workspace=workspace,
                    interval=JobInterval.Manually,
                    status=ResourceStatus.Enabled,
                    kmi_title=name,
                    kmi_abstract=name,
                    input_table=mudmap_input,sql="$$".join(Publish.TRANSFORM).strip()
                )
            mudmap_publish.full_clean(exclude=["interval"])   
            mudmap_publish.save()
            #pubish the job
            result = JobStatemachine._create_job(mudmap_publish,JobInterval.Triggered)

            if result[0]:
                return result[1]
            else:
                raise Exception(result[1])
            
        else:
            #no more json files, delete input, and all other dependent objects.
            try:
                mudmap_input = Input.objects.get(name=input_name)
                mudmap_input.delete()
                return None
            except Input.DoesNotExist:
                #already deleted
                pass

    @skip_prepare
    def delete_list(self,application,name,user, *args, **kwargs):
        try:
            application = application.lower()
            name = name.lower()
            user = user.lower()
            #delere the file from the folder
            folder = os.path.join(BorgConfiguration.MUDMAP_HOME,application,name)
            if os.path.exists(folder) and os.path.isdir(folder):
                #delete the json file from the folder
                file_name = os.path.join(folder,"{}.json".format(user))
                if os.path.exists(file_name):
                    os.remove(file_name)
    
                #get list of geojson files
                files = [f for f in os.listdir(folder)]
                if not files:
                    #remove folder
                    try:
                        os.rmdir(folder)
                    except:
                        #remove failed,but ignore.
                        pass
    
            job_id = self._publish(application,name,user)
        except:
            logger.error(traceback.format_exc())
            raise
    
class PublishResource(DjangoResource,BasicHttpAuthMixin):
    def is_authenticated(self):
        if self.request.user.is_authenticated():
            return True
        else:
            return self.authenticate(self.request)

    @staticmethod
    def urls():
        return [
            url(r'^/publishs/(?P<name>[a-zA-Z0-9_\-]+)/$',PublishResource.as_detail(),name='publish_status'),
        ]
     

    @classmethod
    def _get_milliseconds(cls,d) :
        if not d: 
            return None
        d = timezone.localtime(d)
        return time.mktime(d.timetuple()) * 1000 + d.microsecond / 1000

    @skip_prepare
    def detail(self,name):
        try:
            try:
                publish = Publish.objects.get(name=name)
            except Publish.DoesNotExist:
                return {
                    "layer" :{
                        "name":publish.name,
                    },
                }
            if publish.status != ResourceStatus.Enabled.name:
                return {
                    "layer" :{
                        "id" : publish.id,
                        "workspace":publish.workspace.name,
                        "name":publish.name,
                        "status":publish.status
                    },
                }
            
            publishing_job = None
            latest_published_job = None
            deploied_job = None
            deploytime = None
            deploymessage = None
            if publish.job_id :
                publishing_job = Job.objects.filter(publish = publish,finished__isnull=True).order_by("-id").first()
                latest_published_job = Job.objects.filter(publish = publish,launched__isnull=False,finished__isnull=False).order_by("-id").first()
                    
        
            sync_statuses = PublishSyncStatus.objects.filter(publish=publish).order_by("-deploied_job_id")
            if len(sync_statuses) >= 1:
                deploied_jobid = sync_statuses[0].deploied_job_id
                deploytime = sync_statuses[0].deploy_time
            outofsync_statuses = [status for status in sync_statuses if status.sync_job_id != None or status.deploied_job_id != deploied_jobid]
    
            resp = {
                "layer" :{
                    "id" : publish.id,
                    "workspace":publish.workspace.name,
                    "name":publish.name,
                    "status":publish.status
                },
            }
            if publish.job_id:
                resp["publish"] = {
                    "publishing_jobid" : publishing_job.id if publishing_job else None,
                    "publishing_failed" : publishing_job.jobstate.is_error_state if publishing_job else False,
                    "publishing_message": publisheding_job.message if publishing_job and publishing_job.jobstate.is_error_state else None,
                    "published_jobid" : latest_published_job.id if latest_published_job else None,
                    "publish_time" : self._get_milliseconds(latest_published_job.finished) if latest_published_job else None,
                    "deploied_jobid":deploied_jobid,
                    "deploy_time":self._get_milliseconds(deploytime) if deploytime else None,
                }
                now = timezone.now()
                if outofsync_statuses:
                    resp["publish"]["outofsync_servers"] = []
                    for status in outofsync_statuses:
                        resp["publish"]["outofsync_servers"].append({
                            "server":status.slave_server.name,
                            "deploied_jobid": status.deploied_job_id,
                            "deploy_time":self._get_milliseconds(status.deploy_time),
                            "sync_jobid": status.sync_job_id,
                            "sync_message": status.sync_message,
                            "sync_time":self._get_milliseconds(status.sync_time),
                            "last_poll_time": self._get_milliseconds(status.slave_server.last_poll_time) ,
                            "last_sync_time": self._get_milliseconds(status.slave_server.last_sync_time) ,
                        })
    
            return resp
        except:
            logger.error(traceback.format_exc())
            raise


urlpatterns =  JobResource.urls() + MetaResource.urls() + MudmapResource.urls() + PublishResource.urls()

