import traceback,sys
import hglib
import threading
import logging

from django.db import connection,transaction
from django.core.urlresolvers import reverse
from django.contrib import messages
from django.http import HttpResponseRedirect
from django.utils.safestring import mark_safe
from django.utils import timezone

from tablemanager.models import (
    ForeignTable, Input, NormalTable,
    Normalise, Workspace, Publish, Replica,
    Normalise_NormalTable,Style,
    PublishChannel,DataSource
)
from tablemanager.forms import (
    NormaliseForm,PublishForm,ForeignTableForm,
    InputForm,NormalTableForm,WorkspaceForm,DataSourceForm,
    PublishChannelForm,StyleForm
)
from harvest.models import Job
from harvest.jobstates import JobState
from borg.admin import site
from harvest.jobstatemachine import JobStatemachine
from borg_utils.jobintervals import Manually
from borg_utils.spatial_table import SpatialTable
from borg_utils.borg_config import BorgConfiguration
from borg_utils.resource_status import ResourceStatus
from borg_utils.hg_batch_push import try_set_push_owner, try_clear_push_owner, increase_committed_changes, try_push_to_repository
from borg_utils.admin import BorgAdmin

logger = logging.getLogger(__name__)

def instantiate(modeladmin, request, queryset):
    for table in queryset:
        table.instantiate()
instantiate.short_description = "Create selected tables in database"

class JobFields(object):
    def _job_status(self,o):
        if o.job_id:
            try:
                j = Job.objects.get(pk=o.job_id)
                state = JobState.get_jobstate(j.state)
                if state.is_end_state:
                    return state.name
                elif state.is_error_state:
                    return "Waiting approve" if state.is_interactive_state else "Error"
                else:
                    return "running"
            except:
                return ""
        else:
            return ""
    _job_status.short_description = "Job Status"

    def _job_id(self,o):
        if o.job_id:
            return "<a href='/harvest/job/{0}'>{0}</a>".format(o.job_id)
        else:
            return ''

    _job_id.allow_tags = True
    _job_id.short_description = "Job ID"
    _job_id.admin_order_field = "job_id"

    def _job_batch_id(self,o):
        if o.job_batch_id:
            return "<a href='/harvest/job/?q={0}'>{0}</a>".format(o.job_batch_id)
        else:
            return ''

    _job_batch_id.allow_tags = True
    _job_batch_id.short_description = "Job Batch ID"
    _job_batch_id.admin_order_field = "job_batch_id"

    def _job_message(self,o):
        if o.job_message:
            return "<p style='white-space:pre'>" + o.job_message + "</p>"
        else:
            return ''

    _job_message.allow_tags = True
    _job_message.short_description = "Job message"

class PublishChannelAdmin(BorgAdmin):
    list_display = ("name", "sync_postgres_data","sync_geoserver_data","last_modify_time")
    readonly_fields = ("last_modify_time",)
    form = PublishChannelForm

    def custom_delete_selected(self,request,queryset):
        if request.POST.get('post') != 'yes':
            #the confirm page, or user not confirmed
            return self.default_delete_action[0](self,request,queryset)
    
        #user confirm to delete the workspaces, execute the custom delete logic.
        result = None
        failed_publish_channels = []

        try_set_push_owner("publish_channel_admin",enforce=True)
        warning_message = None
        try:
            for publish_channel in queryset:
                try:
                    with transaction.atomic():
                        publish_channel.delete()
                except:
                    error = sys.exc_info()
                    failed_publish_channels.append((workspace.name,traceback.format_exception_only(error[0],error[1])))
                    #remove failed, continue to process the next publish_channel
                    continue

            try:
                try_push_to_repository('publish_channel_admin',enforce=True)
            except:
                error = sys.exc_info()
                warning_message = traceback.format_exception_only(error[0],error[1])
                logger.error(traceback.format_exc())
        finally:
            try_clear_push_owner("publish_channel_admin",enforce=True)

        if failed_publish_channels or warning_message:
            if failed_publish_channels:
                if warning_message:
                    messages.warning(request, mark_safe("<ul><li>{0}</li><li>Some selected publish channels are deleted failed:<ul>{1}</ul></li></ul>".format(warning_message,"".join(["<li>{0} : {1}</li>".format(o[0],o[1]) for o in failed_publish_channels]))))
                else:
                    messages.warning(request, mark_safe("Some selected publish channels are deleted failed:<ul>{0}</ul>".format("".join(["<li>{0} : {1}</li>".format(o[0],o[1]) for o in failed_publish_channels]))))
            else:
                messages.warning(request, mark_safe(warning_message))
        else:
            messages.success(request, "All selected publish channels are deleted successfully")

    def get_actions(self, request):
        #import ipdb;ipdb.set_trace()
        actions = super(PublishChannelAdmin, self).get_actions(request)
        self.default_delete_action = actions['delete_selected']
        del actions['delete_selected']
        actions['delete_selected'] = (PublishChannelAdmin.custom_delete_selected,self.default_delete_action[1],self.default_delete_action[2])
        return actions 


class DataSourceAdmin(BorgAdmin):
    list_display = ("name","type", "last_modify_time")
    search_fields = ["name"]
    form = DataSourceForm

    def custom_delete_selected(self,request,queryset):
        if request.POST.get('post') != 'yes':
            #the confirm page, or user not confirmed
            return self.default_delete_action[0](self,request,queryset)
    
        #user confirm to delete the workspaces, execute the custom delete logic.
        result = None
        failed_datasources = []

        try_set_push_owner("datasource_admin",enforce=True)
        warning_message = None
        try:
            for datasource in queryset:
                try:
                    with transaction.atomic():
                        datasource.delete()
                except:
                    error = sys.exc_info()
                    failed_datasources.append((workspace.name,traceback.format_exception_only(error[0],error[1])))
                    #remove failed, continue to process the next datasource
                    continue

            try:
                try_push_to_repository('datasource_admin',enforce=True)
            except:
                error = sys.exc_info()
                warning_message = traceback.format_exception_only(error[0],error[1])
                logger.error(traceback.format_exc())
        finally:
            try_clear_push_owner("datasource_admin",enforce=True)

        if failed_datasources or warning_message:
            if failed_datasources:
                if warning_message:
                    messages.warning(request, mark_safe("<ul><li>{0}</li><li>Some selected datasources are deleted failed:<ul>{1}</ul></li></ul>".format(warning_message,"".join(["<li>{0} : {1}</li>".format(o[0],o[1]) for o in failed_datasources]))))
                else:
                    messages.warning(request, mark_safe("Some selected datasources are deleted failed:<ul>{0}</ul>".format("".join(["<li>{0} : {1}</li>".format(o[0],o[1]) for o in failed_datasources]))))
            else:
                messages.warning(request, mark_safe(warning_message))
        else:
            messages.success(request, "All selected datasources are deleted successfully")

    def get_actions(self, request):
        #import ipdb;ipdb.set_trace()
        actions = super(DataSourceAdmin, self).get_actions(request)
        self.default_delete_action = actions['delete_selected']
        del actions['delete_selected']
        actions['delete_selected'] = (DataSourceAdmin.custom_delete_selected,self.default_delete_action[1],self.default_delete_action[2])
        return actions 


class WorkspaceAdmin(BorgAdmin):
    list_display = ("name","publish_channel","auth_level","_schema","_test_schema",)
    readonly_fields = ("_schema","_view_schema","_test_schema","_test_view_schema")
    #actions = [instantiate]
    search_fields = ["name"]

    form = WorkspaceForm

    def _schema(self,o): 
        return o.schema
    
    _schema.short_description = "Schema"

    def _view_schema(self,o): 
        return o.view_schema;
    
    _view_schema.short_description = "View Schema"

    def _test_schema(self,o): 
        return o.test_schema;
    
    _test_schema.short_description = "Test Schema"

    def _test_view_schema(self,o): 
        return o.test_view_schema;
    
    _test_view_schema.short_description = "Test View Schema"

    def custom_delete_selected(self,request,queryset):
        if request.POST.get('post') != 'yes':
            #the confirm page, or user not confirmed
            return self.default_delete_action[0](self,request,queryset)
    
        #user confirm to delete the workspaces, execute the custom delete logic.
        result = None
        failed_workspaces = []

        try_set_push_owner("workspace_admin",enforce=True)
        warning_message = None
        try:
            for workspace in queryset:
                try:
                    with transaction.atomic():
                        workspace.delete()
                except:
                    error = sys.exc_info()
                    failed_workspaces.append((workspace.name,traceback.format_exception_only(error[0],error[1])))
                    #remove failed, continue to process the next workspace
                    continue

            try:
                try_push_to_repository('workspace_admin',enforce=True)
            except:
                error = sys.exc_info()
                warning_message = traceback.format_exception_only(error[0],error[1])
                logger.error(traceback.format_exc())
        finally:
            try_clear_push_owner("workspace_admin",enforce=True)

        if failed_workspaces or warning_message:
            if failed_workspaces:
                if warning_message:
                    messages.warning(request, mark_safe("<ul><li>{0}</li><li>Some selected workspaces are deleted failed:<ul>{1}</ul></li></ul>".format(warning_message,"".join(["<li>{0} : {1}</li>".format(o[0],o[1]) for o in failed_workspaces]))))
                else:
                    messages.warning(request, mark_safe("Some selected workspaces are deleted failed:<ul>{0}</ul>".format("".join(["<li>{0} : {1}</li>".format(o[0],o[1]) for o in failed_workspaces]))))
            else:
                messages.warning(request, mark_safe(warning_message))
        else:
            messages.success(request, "All selected workspaces are deleted successfully")

    def get_actions(self, request):
        #import ipdb;ipdb.set_trace()
        actions = super(WorkspaceAdmin, self).get_actions(request)
        self.default_delete_action = actions['delete_selected']
        del actions['delete_selected']
        actions['delete_selected'] = (WorkspaceAdmin.custom_delete_selected,self.default_delete_action[1],self.default_delete_action[2])
        return actions 

class ForeignTableAdmin(BorgAdmin):
    list_display = ("name","server","last_modify_time")
    readonly_fields = ("last_modify_time",)
    #actions = [instantiate]
    search_fields = ["name"]

    form = ForeignTableForm

    def custom_delete_selected(self,request,queryset):
        if request.POST.get('post') != 'yes':
            #the confirm page, or user not confirmed
            return self.default_delete_action[0](self,request,queryset)
    
        #user confirm to delete the foreign_tablees, execute the custom delete logic.
        result = None
        failed_foreign_tables = []

        try_set_push_owner("foreign_table_admin",enforce=True)
        warning_message = None
        try:
            for foreign_table in queryset:
                try:
                    with transaction.atomic():
                        foreign_table.delete()
                except:
                    error = sys.exc_info()
                    failed_foreign_tables.append((foreign_table.name,traceback.format_exception_only(error[0],error[1])))
                    #remove failed, continue to process the next foreign_table
                    continue

            try:
                try_push_to_repository('foreign_table_admin',enforce=True)
            except:
                error = sys.exc_info()
                warning_message = traceback.format_exception_only(error[0],error[1])
                logger.error(traceback.format_exc())
        finally:
            try_clear_push_owner("foreign_table_admin",enforce=True)

        if failed_foreign_tables or warning_message:
            if failed_foreign_tables:
                if warning_message:
                    messages.warning(request, mark_safe("<ul><li>{0}</li><li>Some selected foreign tables are deleted failed:<ul>{1}</ul></li></ul>".format(warning_message,"".join(["<li>{0} : {1}</li>".format(o[0],o[1]) for o in failed_foreign_tables]))))
                else:
                    messages.warning(request, mark_safe("Some selected foreign tables are deleted failed:<ul>{0}</ul>".format("".join(["<li>{0} : {1}</li>".format(o[0],o[1]) for o in failed_foreign_tables]))))
            else:
                messages.warning(request, mark_safe(warning_message))
        else:
            messages.success(request, "All selected foreign tables are deleted successfully")

    def get_actions(self, request):
        #import ipdb;ipdb.set_trace()
        actions = super(ForeignTableAdmin, self).get_actions(request)
        self.default_delete_action = actions['delete_selected']
        del actions['delete_selected']
        actions['delete_selected'] = (ForeignTableAdmin.custom_delete_selected,self.default_delete_action[1],self.default_delete_action[2])
        return actions 

def _up_to_date(o):
    return o.is_up_to_date()
_up_to_date.short_description = "Up to date"
_up_to_date.boolean = True

class NormalTableAdmin(BorgAdmin):
    list_display = ("name","_normalise","last_modify_time",_up_to_date)
    #actions = [instantiate]
    readonly_fields = ("_normalise","last_modify_time",_up_to_date)
    search_fields = ["name"]

    form = NormalTableForm

    def _normalise(self,o):
        if o.normalise:
            return o.normalise.name
        else:
            return ""
    _normalise.short_description = "Normalise"

    def custom_delete_selected(self,request,queryset):
        if request.POST.get('post') != 'yes':
            #the confirm page, or user not confirmed
            return self.default_delete_action[0](self,request,queryset)
    
        #user confirm to delete the normal_tablees, execute the custom delete logic.
        result = None
        failed_normal_tables = []

        try_set_push_owner("normal_table_admin",enforce=True)
        warning_message = None
        try:
            for normal_table in queryset:
                try:
                    with transaction.atomic():
                        normal_table.delete()
                except:
                    error = sys.exc_info()
                    failed_normal_tables.append((normal_table.name,traceback.format_exception_only(error[0],error[1])))
                    #remove failed, continue to process the next normal_table
                    continue

            try:
                try_push_to_repository('normal_table_admin',enforce=True)
            except:
                error = sys.exc_info()
                warning_message = traceback.format_exception_only(error[0],error[1])
                logger.error(traceback.format_exc())
        finally:
            try_clear_push_owner("normal_table_admin",enforce=True)

        if failed_normal_tables or warning_message:
            if failed_normal_tables:
                if warning_message:
                    messages.warning(request, mark_safe("<ul><li>{0}</li><li>Some selected normal tables are deleted failed:<ul>{1}</ul></li></ul>".format(warning_message,"".join(["<li>{0} : {1}</li>".format(o[0],o[1]) for o in failed_normal_tables]))))
                else:
                    messages.warning(request, mark_safe("Some selected normal tables are deleted failed:<ul>{0}</ul>".format("".join(["<li>{0} : {1}</li>".format(o[0],o[1]) for o in failed_normal_tables]))))
            else:
                messages.warning(request, mark_safe(warning_message))
        else:
            messages.success(request, "All selected normal tables are deleted successfully")

    def get_actions(self, request):
        #import ipdb;ipdb.set_trace()
        actions = super(NormalTableAdmin, self).get_actions(request)
        self.default_delete_action = actions['delete_selected']
        del actions['delete_selected']
        actions['delete_selected'] = (NormalTableAdmin.custom_delete_selected,self.default_delete_action[1],self.default_delete_action[2])
        return actions 

class InputAdmin(BorgAdmin,JobFields):
    list_display = ("name","data_source", "geometry", "extent", "count","last_modify_time",_up_to_date,"_job_id", "_job_batch_id", "_job_status")
    readonly_fields = ("spatial_type_desc","_style_file","title","abstract","_create_table_sql","ds_modify_time","last_modify_time",_up_to_date,"_job_batch_id","_job_id","_job_status","_job_message")
    search_fields = ["name","data_source__name"]

    form = InputForm

    def spatial_type_desc(self,o):
        return SpatialTable.get_spatial_type_desc(o.spatial_type)
    spatial_type_desc.short_description = "Spatial Type"

    def _style_file(self,o):
        if o.style_file:
            return o.style_file
        else:
            return ""
    _style_file.short_description = "Style file"

    def _create_table_sql(self,o):
        if o.create_table_sql:
            return "<p style='white-space:pre'>" + o.create_table_sql + "</p>"
        else:
            return ''

    _create_table_sql.allow_tags = True
    _create_table_sql.short_description = "CREATE info for table"

    def custom_delete_selected(self,request,queryset):
        if request.POST.get('post') != 'yes':
            #the confirm page, or user not confirmed
            return self.default_delete_action[0](self,request,queryset)
    
        #user confirm to delete the inputes, execute the custom delete logic.
        result = None
        failed_inputs = []

        try_set_push_owner("input_admin",enforce=True)
        warning_message = None
        try:
            for input in queryset:
                try:
                    with transaction.atomic():
                        input.delete()
                except:
                    error = sys.exc_info()
                    failed_inputs.append((input.name,traceback.format_exception_only(error[0],error[1])))
                    #remove failed, continue to process the next input
                    continue

            try:
                try_push_to_repository('input_admin',enforce=True)
            except:
                error = sys.exc_info()
                warning_message = traceback.format_exception_only(error[0],error[1])
                logger.error(traceback.format_exc())
        finally:
            try_clear_push_owner("input_admin",enforce=True)

        if failed_inputs or warning_message:
            if failed_inputs:
                if warning_message:
                    messages.warning(request, mark_safe("<ul><li>{0}</li><li>Some selected inputs are deleted failed:<ul>{1}</ul></li></ul>".format(warning_message,"".join(["<li>{0} : {1}</li>".format(o[0],o[1]) for o in failed_inputs]))))
                else:
                    messages.warning(request, mark_safe("Some selected inputs are deleted failed:<ul>{0}</ul>".format("".join(["<li>{0} : {1}</li>".format(o[0],o[1]) for o in failed_inputs]))))
            else:
                messages.warning(request, mark_safe(warning_message))
        else:
            messages.success(request, "All selected inputs are deleted successfully")

    def get_actions(self, request):
        #import ipdb;ipdb.set_trace()
        actions = super(InputAdmin, self).get_actions(request)
        self.default_delete_action = actions['delete_selected']
        del actions['delete_selected']
        actions['delete_selected'] = (InputAdmin.custom_delete_selected,self.default_delete_action[1],self.default_delete_action[2])
        return actions 

class NormaliseAdmin(BorgAdmin,JobFields):
    list_display = ("name","output_table","last_modify_time",_up_to_date,"_job_id", "_job_batch_id","_job_status")
    readonly_fields = ("last_modify_time",_up_to_date,"_job_batch_id","_job_id","_job_status","_job_message")
    search_fields = ["__name"]

    form = NormaliseForm

    def custom_delete_selected(self,request,queryset):
        if request.POST.get('post') != 'yes':
            #the confirm page, or user not confirmed
            return self.default_delete_action[0](self,request,queryset)
    
        #user confirm to delete the normalisees, execute the custom delete logic.
        result = None
        failed_normalises = []

        try_set_push_owner("normalise_admin",enforce=True)
        warning_message = None
        try:
            for normalise in queryset:
                try:
                    with transaction.atomic():
                        normalise.delete()
                except:
                    error = sys.exc_info()
                    failed_normalises.append((normalise.name,traceback.format_exception_only(error[0],error[1])))
                    #remove failed, continue to process the next normalise
                    continue

            try:
                try_push_to_repository('normalise_admin',enforce=True)
            except:
                error = sys.exc_info()
                warning_message = traceback.format_exception_only(error[0],error[1])
                logger.error(traceback.format_exc())
        finally:
            try_clear_push_owner("normalise_admin",enforce=True)

        if failed_normalises or warning_message:
            if failed_normalises:
                if warning_message:
                    messages.warning(request, mark_safe("<ul><li>{0}</li><li>Some selected normalises are deleted failed:<ul>{1}</ul></li></ul>".format(warning_message,"".join(["<li>{0} : {1}</li>".format(o[0],o[1]) for o in failed_normalises]))))
                else:
                    messages.warning(request, mark_safe("Some selected normalises are deleted failed:<ul>{0}</ul>".format("".join(["<li>{0} : {1}</li>".format(o[0],o[1]) for o in failed_normalises]))))
            else:
                messages.warning(request, mark_safe(warning_message))
        else:
            messages.success(request, "All selected normalises are deleted successfully")

    def get_actions(self, request):
        #import ipdb;ipdb.set_trace()
        actions = super(NormaliseAdmin, self).get_actions(request)
        self.default_delete_action = actions['delete_selected']
        del actions['delete_selected']
        actions['delete_selected'] = (NormaliseAdmin.custom_delete_selected,self.default_delete_action[1],self.default_delete_action[2])
        return actions 

class PublishAdmin(BorgAdmin,JobFields):
    list_display = ("name","workspace","spatial_type_desc","_default_style","interval","_enabled","_publish_content","_job_id", "_job_batch_id", "_job_status","waiting","running","completed","failed")
    readonly_fields = ("_default_style","applications","_create_table_sql","spatial_type_desc","last_modify_time","_publish_content","_job_batch_id","_job_id","_job_status","_job_message","waiting","running","completed","failed")
    search_fields = ["name","status","workspace__name"]

    form = PublishForm

    _geoserver_setting_fields = [f[0] for f in PublishForm.base_fields.items() if hasattr(f[1],"setting_type") and f[1].setting_type == "geoserver_setting"]

    def _enabled(self,o):
        return o.status == ResourceStatus.Enabled.name

    _enabled.boolean = True
    _enabled.short_description = "Enabled"

    def _publish_content(self,o):
        result = o.is_up_to_date()
        return str(result) if result is not None else ""
    _publish_content.short_description = "Publish"

    def spatial_type_desc(self,o):
        return SpatialTable.get_spatial_type_desc(o.spatial_type)
    spatial_type_desc.short_description = "Spatial Type"
    spatial_type_desc.admin_order_field = "spatial_type"
            
    def _create_table_sql(self,o):
        if o.create_table_sql:
            return "<p style='white-space:pre'>" + o.create_table_sql + "</p>"
        else:
            return ''

    _create_table_sql.allow_tags = True
    _create_table_sql.short_description = "CREATE info for table"


    def _default_style(self,o):
        if o.default_style:
            return "<a href='/tablemanager/style/{}/'>{}</a>".format(o.default_style.pk,o.default_style.name)
        else:
            return ""
    _default_style.allow_tags = True
    _default_style.short_description = "Default Style"

    def custom_delete_selected(self,request,queryset):
        if request.POST.get('post') != 'yes':
            #the confirm page, or user not confirmed
            return self.default_delete_action[0](self,request,queryset)
    
        #user confirm to delete the publishes, execute the custom delete logic.
        result = None
        failed_objects = []

        try_set_push_owner("publish_admin",enforce=True)
        warning_message = None
        try:
            for publish in queryset:
                try:
                    with transaction.atomic():
                        publish.delete()
                except:
                    error = sys.exc_info()
                    failed_objects.append(("{0}:{1}".format(publish.workspace.name,publish.name),traceback.format_exception_only(error[0],error[1])))
                    #remove failed, continue to process the next publish
                    continue

            try:
                try_push_to_repository('publish_admin',enforce=True)
            except:
                error = sys.exc_info()
                warning_message = traceback.format_exception_only(error[0],error[1])
                logger.error(traceback.format_exc())
        finally:
            try_clear_push_owner("publish_admin",enforce=True)

        if failed_objects or warning_message:
            if failed_objects:
                if warning_message:
                    messages.warning(request, mark_safe("<ul><li>{0}</li><li>Some selected publishs are deleted failed:<ul>{1}</ul></li></ul>".format(warning_message,"".join(["<li>{0} : {1}</li>".format(o[0],o[1]) for o in failed_objects]))))
                else:
                    messages.warning(request, mark_safe("Some selected publishs are deleted failed:<ul>{0}</ul>".format("".join(["<li>{0} : {1}</li>".format(o[0],o[1]) for o in failed_objects]))))
            else:
                messages.warning(request, mark_safe(warning_message))
        else:
            messages.success(request, "All selected publishs are deleted successfully")

    def publish_meta_data(self,request,queryset):
        result = None
        failed_objects = []
        #import ipdb;ipdb.set_trace()
        try_set_push_owner("publish_admin",enforce=True)
        warning_message = None
        try:
            for publish in queryset:
                try:
                    publish.publish_meta_data()
                except:
                    error = sys.exc_info()
                    failed_objects.append(("{0}:{1}".format(publish.workspace.name,publish.name),traceback.format_exception_only(error[0],error[1])))
                    #remove failed, continue to process the next publish
                    continue

            try:
                try_push_to_repository('publish_admin',enforce=True)
            except:
                error = sys.exc_info()
                warning_message = traceback.format_exception_only(error[0],error[1])
                logger.error(traceback.format_exc())
        finally:
            try_clear_push_owner("publish_admin",enforce=True)

        if failed_objects or warning_message:
            if failed_objects:
                if warning_message:
                    messages.warning(request, mark_safe("<ul><li>{0}</li><li>Pushing changes to repository failed:<ul>{1}</ul></li></ul>".format(warning_message,"".join(["<li>{0} : {1}</li>".format(o[0],o[1]) for o in failed_objects]))))
                else:
                    messages.warning(request, mark_safe("Publish meta data failed for some selected publishs:<ul>{0}</ul>".format("".join(["<li>{0} : {1}</li>".format(o[0],o[1]) for o in failed_objects]))))
            else:
                messages.warning(request, mark_safe(warning_message))
        else:
            messages.success(request, "Publish meta data successfully for all selected publishs")


    publish_meta_data.short_description = "Publish Meta Data"

    def enable_publish(self,request,queryset):
        result = None
        failed_objects = []
        for publish in queryset:
            #modify the table data
            if publish.status != ResourceStatus.Enabled.name:
                #status is changed
                publish.status = ResourceStatus.Enabled.name
                try:
                    publish.save(update_fields=['status','pending_actions'])
                except:
                    error = sys.exc_info()
                    failed_objects.append(("{0}:{1}".format(publish.workspace.name,publish.name),traceback.format_exception_only(error[0],error[1])))
                    #update table failed, continue to process the next publish
                    continue

        if failed_objects:
            messages.warning(request, mark_safe("Enable failed for some selected publishs:<ul>{0}</ul>".format("".join(["<li>{0} : {1}</li>".format(o[0],o[1]) for o in failed_objects]))))
        else:
            messages.success(request, "Enable successfully for all selected publishs")

    enable_publish.short_description = "Enable selected publishs"

    def disable_publish(self,request,queryset):
        result = None
        failed_objects = []
        #import ipdb;ipdb.set_trace()
        try_set_push_owner("publish_admin",enforce=True)
        warning_message = None
        try:
            for publish in queryset:
                try:
                    publish.remove_publish_from_repository()
                    if publish.status != ResourceStatus.Disabled.name:
                        publish.status = ResourceStatus.Disabled.name
                        publish.pending_actions = None
                        publish.job_id = None
                        publish.job_batch_id = None
                        publish.job_status = None
                        publish.save(update_fields=['status','pending_actions','job_id','job_batch_id','job_status'])
                except:
                    error = sys.exc_info()
                    failed_objects.append(("{0}:{1}".format(publish.workspace.name,publish.name),traceback.format_exception_only(error[0],error[1])))
                    #remove failed, continue to process the next publish
                    continue

            try:
                try_push_to_repository('publish_admin',enforce=True)
            except:
                error = sys.exc_info()
                warning_message = traceback.format_exception_only(error[0],error[1])
                logger.error(traceback.format_exc())
        finally:
            try_clear_push_owner("publish_admin",enforce=True)

        if failed_objects or warning_message:
            if failed_objects:
                if warning_message:
                    messages.warning(request, mark_safe("<ul><li>{0}</li><li>Pushing changes to repository failed:<ul>{1}</ul></li></ul>".format(warning_message,"".join(["<li>{0} : {1}</li>".format(o[0],o[1]) for o in failed_objects]))))
                else:
                    messages.warning(request, mark_safe("Disable failed for some selected publishs:<ul>{0}</ul>".format("".join(["<li>{0} : {1}</li>".format(o[0],o[1]) for o in failed_objects]))))
            else:
                messages.warning(request, mark_safe(warning_message))
        else:
            messages.success(request, "Disable successfully for all selected publishs")

    disable_publish.short_description = "Disable selected publishs"

    def create_harvest_job(self,request,queryset):
        job_batch_id = Manually.instance().job_batch_id()
        result = None
        failed_objects = []
        for publish in queryset:
            result = JobStatemachine.create_job(publish.id,Manually.instance(),job_batch_id)
            if not result[0]:
                failed_objects.append(("{0}:{1}".format(publish.workspace.name,publish.name),result[1]))

        if failed_objects:
            messages.warning(request, mark_safe("Create job failed for some selected publishs:<ul>{0}</ul>".format("".join(["<li>{0} : {1}</li>".format(o[0],o[1]) for o in failed_objects]))))
        else:
            messages.success(request, "Create job successfully for all selected publishs")

    create_harvest_job.short_description = "Create Harvest Job Manually"
    
    def empty_gwc(self,request,queryset):
        result = None
        failed_objects = []
        try_set_push_owner("publish_admin",enforce=True)
        warning_message = None
        try:
            for l in queryset:
                try:
                    if l.publish_status not in [ResourceStatus.Enabled]:
                        #Publish is disabled.
                        failed_objects.append(("{0}:{1}".format(l.workspace.name,l.name),"Disabled, no need to empty gwc."))
                        continue

                    l.empty_gwc()
                except:
                    logger.error(traceback.format_exc())
                    error = sys.exc_info()
                    failed_objects.append(("{0}:{1}".format(l.workspace.name,l.name),traceback.format_exception_only(error[0],error[1])))
                    #remove failed, continue to process the next publish
                    continue
            try:
                try_push_to_repository('publish_admin',enforce=True)
            except:
                error = sys.exc_info()
                warning_message = traceback.format_exception_only(error[0],error[1])
                logger.error(traceback.format_exc())
        finally:
            try_clear_push_owner("publish_admin",enforce=True)

        if failed_objects or warning_message:
            if failed_objects:
                if warning_message:
                    messages.warning(request, mark_safe("<ul><li>{0}</li><li>Some selected publishs are processed failed:<ul>{1}</ul></li></ul>".format(warning_message,"".join(["<li>{0} : {1}</li>".format(o[0],o[1]) for o in failed_objects]))))
                else:
                    messages.warning(request, mark_safe("Some selected publishs are processed failed:<ul>{0}</ul>".format("".join(["<li>{0} : {1}</li>".format(o[0],o[1]) for o in failed_objects]))))
            else:
                messages.warning(request, mark_safe(warning_message))
        else:
            messages.success(request, "All selected publishs are processed successfully.")

    empty_gwc.short_description = "Empty GWC"

    actions = ['enable_publish','disable_publish','create_harvest_job','publish_meta_data','empty_gwc']
    def get_actions(self, request):
        #import ipdb;ipdb.set_trace()
        actions = super(PublishAdmin, self).get_actions(request)
        self.default_delete_action = actions['delete_selected']
        del actions['delete_selected']
        actions['delete_selected'] = (PublishAdmin.custom_delete_selected,self.default_delete_action[1],self.default_delete_action[2])
        return actions 

class StyleAdmin(BorgAdmin):
    list_display = ("id","publish","name","_default_style","_enabled","last_modify_time")
    search_fields = ["name","status","publish__name"]

    form = StyleForm

    def _default_style(self,o):
        return o.default_style if o else False

    _default_style.boolean = True
    _default_style.short_description = "Default Style"

    def _enabled(self,o):
        return o.status == ResourceStatus.Enabled.name

    _enabled.boolean = True
    _enabled.short_description = "Enabled"

    def enable_style(self,request,queryset):
        result = None
        failed_objects = []
        for publishStyle in queryset:
            #modify the table data
            if publishStyle.status != ResourceStatus.Enabled.name:
                #status is changed
                publishStyle.status = ResourceStatus.Enabled.name
                publishStyle.last_modify_time = timezone.now()
                try:
                    publishStyle.save(update_fields=['status','last_modify_time'])
                except:
                    error = sys.exc_info()
                    failed_objects.append(("{0}:{1}:{2}".format(publishStyle.publish.workspace.name,publishStyle.publish.name,publishStyle.name),traceback.format_exception_only(error[0],error[1])))
                    #update table failed, continue to process the next publish
                    continue

        if failed_objects:
            messages.warning(request, mark_safe("Enable failed for some selected styles:<ul>{0}</ul>".format("".join(["<li>{0} : {1}</li>".format(o[0],o[1]) for o in failed_objects]))))
        else:
            messages.success(request, "Enable successfully for all selected styles")

    enable_style.short_description = "Enable selected styles"

    def disable_style(self,request,queryset):
        result = None
        failed_objects = []
        #import ipdb;ipdb.set_trace()
        for publishStyle in queryset:
            try:
                if publishStyle.status != ResourceStatus.Disabled.name:
                    publishStyle.status = ResourceStatus.Disabled.name
                    publishStyle.last_modify_time = timezone.now()
                    publishStyle.save(update_fields=['status','last_modify_time'])
            except:
                error = sys.exc_info()
                failed_objects.append(("{0}:{1}:{2}".format(publishStyle.publish.workspace.name,publishStyle.publish.name,publishStyle.name),traceback.format_exception_only(error[0],error[1])))
                continue

        if failed_objects:
            messages.warning(request, mark_safe("Disable failed for some selected styles:<ul>{0}</ul>".format("".join(["<li>{0} : {1}</li>".format(o[0],o[1]) for o in failed_objects]))))
        else:
            messages.success(request, "Disable successfully for all selected styles")

    disable_style.short_description = "Disable selected styles"

    def set_default_style(self,request,queryset):
        result = None
        failed_objects = []
        #import ipdb;ipdb.set_trace()
        for publishStyle in queryset:
            try:
                if publishStyle.status == ResourceStatus.Disabled.name:
                    failed_objects.append(("{0}:{1}:{2}".format(publishStyle.publish.workspace.name,publishStyle.publish.name,publishStyle.name),"Can't set disabled style as default style."))
                else:
                    publishStyle.publish.last_modify_time = timezone.now()
                    publishStyle.publish.default_style = publishStyle
                    publishStyle.publish.save(update_fields=['default_style','last_modify_time'])
            except:
                error = sys.exc_info()
                failed_objects.append(("{0}:{1}:{2}".format(publishStyle.publish.workspace.name,publishStyle.publish.name,publishStyle.name),traceback.format_exception_only(error[0],error[1])))
                continue

        if failed_objects:
            messages.warning(request, mark_safe("Set default style failed for some selected styles:<ul>{0}</ul>".format("".join(["<li>{0} : {1}</li>".format(o[0],o[1]) for o in failed_objects]))))
        else:
            messages.success(request, "Set default style successfully for all selected styles")

    set_default_style.short_description = "Set default style"

    actions = ['enable_style','set_default_style','disable_style']
    
site.register(Workspace, WorkspaceAdmin)
site.register(ForeignTable, ForeignTableAdmin)
site.register(Input, InputAdmin)
site.register(Publish, PublishAdmin)
site.register(Style, StyleAdmin)
site.register(Normalise, NormaliseAdmin)
site.register(NormalTable, NormalTableAdmin)
site.register(PublishChannel, PublishChannelAdmin)
site.register(DataSource, DataSourceAdmin)
