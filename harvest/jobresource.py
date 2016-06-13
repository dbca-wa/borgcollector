import json
import base64
import os
import logging
import traceback

from restless.dj import DjangoResource
from restless.resources import skip_prepare

from django.conf.urls import patterns,  url
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
from borg_utils.hg_batch_push import try_set_push_owner, try_clear_push_owner, try_push_to_repository
from borg_utils.jobintervals import Triggered
from borg_utils.borg_config import BorgConfiguration
from borg_utils.resource_status import ResourceStatus

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
        return patterns('',
            url(r'^/?$',JobResource.as_list(),name='api_job_create'),
        )
     
    @skip_prepare
    def create(self):
        job_batch_id = Triggered.instance().job_batch_id()
        resp = {"status":True}
        result = None
        for name in self.data.get('publishes') or []:
            resp[name] = {}
            result = JobStatemachine.create_job_by_name(name,Triggered.instance(),job_batch_id)
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
        return patterns('',
            url(r'^/?$',MetaResource.as_list(),name='api_meta_create'),
        )
     
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
        return patterns('',
            url(r'^(?P<application>[a-zA-Z0-9_\-]+)/(?P<name>[a-zA-Z0-9_\-]+)/(?P<user>[a-zA-Z0-9_\-\.]+@[a-zA-Z0-9\-]+(\.[a-zA-Z0-9\-]+)+)/$',MudmapResource.as_list(),name='api_mudmap_detail'),
        )
     
    @skip_prepare
    def create(self,application,name,user, *args, **kwargs):
        try:
            json_data = self.data
            application = application.lower()
            name = name.lower()
            user = user.lower()
            input_name = "{}_{}".format(application,name)
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
            #generate the source data
            data_source = DataSource.objects.get(name="mudmap")
            #create or update input 
            mudmap_input = None
            try:
                mudmap_input = Input.objects.get(name=input_name)
                source = Template(data_source.vrt).render(Context({"files":json_files,"self":mudmap_input}))
                mudmap_input.source = source
                mudmap_input.full_clean(exclude=["data_source"])
                mudmap_input.last_modify_time = timezone.now()
                mudmap_input.save(update_fields=["source","last_modify_time","info"])
            except Input.DoesNotExist:
                mudmap_input = Input(name=input_name,data_source=data_source,generate_rowid=False)
                source = Template(data_source.vrt).render(Context({"files":json_files,"self":mudmap_input}))
                mudmap_input.source = source
                mudmap_input.full_clean(exclude=["data_source"])
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
                    interval=Triggered.instance(),
                    status=ResourceStatus.Enabled,
                    kmi_title=name,
                    kmi_abstract=name,
                    input_table=mudmap_input,sql="$$".join(Publish.TRANSFORM).strip()
                )
                mudmap_publish.save()
            #pubish the job
            result = JobStatemachine._create_job(mudmap_publish,Triggered.instance())
    
            if result[0]:
                return {"id":result[1]}
            else:
                raise Exception(result[1])
        except:
            logger.error(traceback.format_exc())
            raise
    
    @skip_prepare
    def delete_list(self,application,name,user, *args, **kwargs):
        application = application.lower()
        name = name.lower()
        user = user.lower()
        input_name = "{}_{}".format(application,name)
        #delere the file from the folder
        folder = os.path.join(BorgConfiguration.MUDMAP_HOME,application,name)
        json_files = None
        if os.path.exists(folder) and os.path.isdir(folder):
            #delete the json file from the folder
            file_name = os.path.join(folder,"{}.json".format(user))
            file_exists = False
            if os.path.exists(file_name):
                os.remove(file_name)
                file_exists = True

            #get list of geojson files
            json_files = [f for f in os.listdir(folder) if f[-5:] == ".json"]
            if not json_files:
                #remove folder
                try:
                    os.rmdir(folder)
                except:
                    #remove failed,but ignore.
                    pass

            if not file_exists:
                #file already removed.
                return

        #update or delete input 
        mudmap_input = Input.objects.get(name=input_name)
        if json_files:
            #generate the source data
            data_source = DataSource.objects.get(name="mudmap")
            source = Template(data_source.vrt).render(Context({"files":json_files}))
            mudmap_input.source = source
            mudmap_input.last_modify_time = timezone.now()
            mudmap_input.save(update_fields=["source","last_modify_time"])
            #pubish the job
            result = JobStatemachine._create_job(mudmap_publish,Triggered.instance())

            if result[0]:
                return 
            else:
                raise result[1]
        else:
            #no more json files, delete input, and all other dependent objects.
            mudmap_input.delete()

