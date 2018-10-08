import sys,traceback
import logging
import json

from django.contrib import admin
from django.utils import timezone
from django.contrib import messages
from django.utils.safestring import mark_safe
from django.db import transaction

from livelayermanager.models import Datasource, Layer, PublishedLayer,SqlViewLayer
from livelayermanager.forms import DatasourceForm,LayerForm,SqlViewLayerForm
from borg.admin import site
from borg_utils.resource_status import ResourceStatus,ResourceAction
from borg_utils.hg_batch_push import try_set_push_owner, try_clear_push_owner, increase_committed_changes, try_push_to_repository

logger = logging.getLogger(__name__)

class DatasourceAdmin(admin.ModelAdmin):
    list_display = ("name","workspace","host","db_name","schema","_layers", "status","last_publish_time", "last_modify_time", "last_refresh_time")
    readonly_fields = ("_layers","status","last_publish_time", "last_modify_time","last_unpublish_time","last_refresh_time")
    search_fields = ["name","status"]

    actions = ['publish','unpublish','refresh']
    ordering = ("name",)

    form = DatasourceForm

    def _layers(self,o):
        if o.layers > 0:
            return "<a href='/livelayermanager/layer/?q=&datasource__id__exact={0}'>{1}</a>".format(o.pk,o.layers)
        elif o.last_refresh_time:
            return "0"
        else:
            return ""
    _layers.allow_tags = True
    _layers.short_description = "Layers"
    _layers.admin_order_field = "layers"

    def refresh(self,request,queryset):
        result = None
        failed_datasources = []
        for datasource in queryset:
            #modify the table data
            try:
                datasource.refresh()
            except:
                error = sys.exc_info()
                failed_datasources.append((datasource.name,traceback.format_exc()))
                continue

        if failed_datasources:
            messages.warning(request, mark_safe("Refresh failed for some selected datasources:<ul>{0}</ul>".format("".join(["<li>{0} : {1}</li>".format(o[0],o[1]) for o in failed_datasources]))))
        else:
            messages.success(request, "Refresh successfully for all selected datasources")

    refresh.short_description = "Refresh"
    
    def publish(self,request,queryset):
        self._change_status(request,queryset,ResourceAction.PUBLISH,["status","last_publish_time"])
    publish.short_description = "Publish selected datasources"

    def unpublish(self,request,queryset):
        self._change_status(request,queryset,ResourceAction.UNPUBLISH,["status","last_unpublish_time"])
    unpublish.short_description = "Unpublish selected datasources"

    def _change_status(self,request,queryset,action,update_fields=None):
        result = None
        failed_objects = []
        try_set_push_owner("datasource_admin",enforce=True)
        warning_message = None
        try:
            for datasource in queryset:
                #import ipdb;ipdb.set_trace()
                try:
                    target_status = datasource.next_status(action)
                    if target_status == datasource.status and not datasource.publish_required and not datasource.unpublish_required:
                        #status not changed
                        continue
                    else:
                        datasource.status = target_status
                        datasource.save(update_fields=update_fields)
                except:
                    logger.error(traceback.format_exc())
                    error = sys.exc_info()
                    failed_objects.append(("{0}:{1}".format(datasource.workspace.name,datasource.name),traceback.format_exception_only(error[0],error[1])))
                    #remove failed, continue to process the next publish
                    continue
            try:
                try_push_to_repository('datasource_admin',enforce=True)
            except:
                error = sys.exc_info()
                warning_message = traceback.format_exception_only(error[0],error[1])
                logger.error(traceback.format_exc())
        finally:
            try_clear_push_owner("datasource_admin",enforce=True)

        if failed_objects or warning_message:
            if failed_objects:
                if warning_message:
                    messages.warning(request, mark_safe("<ul><li>{0}</li><li>Some selected datasources are processed failed:<ul>{1}</ul></li></ul>".format(warning_message,"".join(["<li>{0} : {1}</li>".format(o[0],o[1]) for o in failed_objects]))))
                else:
                    messages.warning(request, mark_safe("Some selected datasources are processed failed:<ul>{0}</ul>".format("".join(["<li>{0} : {1}</li>".format(o[0],o[1]) for o in failed_objects]))))
            else:
                messages.warning(request, mark_safe(warning_message))
        else:
            messages.success(request, "All selected datasources are processed successfully.")

    def custom_delete_selected(self,request,queryset):
        if request.POST.get('post') != 'yes':
            #the confirm page, or user not confirmed
            return self.default_delete_action[0](self,request,queryset)
    
        result = None
        failed_objects = []
        try_set_push_owner("datasource_admin",enforce=True)
        warning_message = None
        try:
            for datasource in queryset:
                #import ipdb;ipdb.set_trace()
                try:
                    #delete the datasource
                    datasource.delete()
                except:
                    logger.error(traceback.format_exc())
                    error = sys.exc_info()
                    failed_objects.append(("{0}:{1}".format(datasource.workspace.name,datasource.name),traceback.format_exception_only(error[0],error[1])))
                    #remove failed, continue to process the next publish
                    continue
            try:
                try_push_to_repository('datasource_admin',enforce=True)
            except:
                error = sys.exc_info()
                warning_message = traceback.format_exception_only(error[0],error[1])
                logger.error(traceback.format_exc())
        finally:
            try_clear_push_owner("datasource_admin",enforce=True)

        if failed_objects or warning_message:
            if failed_objects:
                if warning_message:
                    messages.warning(request, mark_safe("<ul><li>{0}</li><li>Some selected datasources are deleted failed:<ul>{1}</ul></li></ul>".format(warning_message,"".join(["<li>{0} : {1}</li>".format(o[0],o[1]) for o in failed_objects]))))
                else:
                    messages.warning(request, mark_safe("Some selected datasources are deleted failed:<ul>{0}</ul>".format("".join(["<li>{0} : {1}</li>".format(o[0],o[1]) for o in failed_objects]))))
            else:
                messages.warning(request, mark_safe(warning_message))
        else:
            messages.success(request, "All selected datasources are deleted successfully.")

    def get_actions(self, request):
        actions = super(DatasourceAdmin, self).get_actions(request)
        self.default_delete_action = actions['delete_selected']
        del actions['delete_selected']
        actions['delete_selected'] = (DatasourceAdmin.custom_delete_selected,self.default_delete_action[1],self.default_delete_action[2])
        return actions 

class AbstractLayerAdmin(admin.ModelAdmin):
    list_display = ("table","name","_workspace","_datasource","spatial_column","spatial_type","crs", "status","last_publish_time","last_refresh_time")
    readonly_fields = ("_workspace","_datasource","spatial_column","spatial_type","crs","_bounding_box","status","spatial_info_desc","_sql","last_publish_time","last_unpublish_time", "last_refresh_time","last_modify_time")
    search_fields = ["table", "name"]
    ordering = ("datasource","name","table")
    list_filter = ("datasource",)

    form = LayerForm

    html = "<table > \
<tr > \
    <th style='width:100px;border-bottom:None' align='left'>Min X</th> \
    <th style='width:100px;border-bottom:None' align='left'>Min Y</th> \
    <th style='width:100px;border-bottom:None' align='left'>Max X</th> \
    <th style='width:100px;border-bottom:None' align='left'>Max Y</th> \
</tr> \
<tr> \
    <td style='border-bottom:None'>{}</td> \
    <td style='border-bottom:None'>{}</td> \
    <td style='border-bottom:None'>{}</td> \
    <td style='border-bottom:None'>{}</td> \
</tr> \
</table>"
    def _bounding_box(self,instance):
        bounding_box = ["-","-","-","-"]
        if instance.bbox:
            try:
                bounding_box = instance.bbox
                if not bounding_box :
                    bounding_box = ["-","-","-","-"]
            except:
                bounding_box = ["-","-","-","-"]

        return self.html.format(*bounding_box)
    _bounding_box.allow_tags = True
    _bounding_box.short_description = "Bounding Box"

    def _sql(self,o):
        if o.sql:
            return "<p style='white-space:pre'>" + o.sql + "</p>"
        else:
            return ''

    _sql.allow_tags = True
    _sql.short_description = "CREATE info for table"

    def _datasource(self,o):
        if o.datasource:
            return "<a href='/livelayermanager/datasource/{0}/'>{1}</a>".format(o.datasource.pk,o.datasource.name)
        else:
            return ""
    _datasource.allow_tags = True
    _datasource.short_description = "Datasource"
    _datasource.admin_order_field = "datasource"

    def _workspace(self,o):
        return o.datasource.workspace
    _workspace.short_description = "Workspace"
    _workspace.admin_order_field = "datasource__workspace"

    def has_add_permission(self,request):
        return False

    def has_delete_permission(self,request,obj=None):
        return False

    def refresh(self,request,queryset):
        result = None
        failed_layers = []
        for layer in queryset:
            #modify the table data
            try:
                layer.refresh()
            except:
                error = sys.exc_info()
                failed_layers.append((layer,traceback.format_exc()))
                continue

        if failed_layers:
            messages.warning(request, mark_safe("Refresh failed for some selected layers:<ul>{0}</ul>".format("".join(["<li>{0} : {1}</li>".format(o[0],o[1]) for o in failed_layers]))))
        else:
            messages.success(request, "Refresh successfully for all selected layers")

    refresh.short_description = "Refresh"
    
    def empty_gwc(self,request,queryset):
        result = None
        failed_objects = []
        try_set_push_owner("livelayer_admin",enforce=True)
        warning_message = None
        try:
            for l in queryset:
                try:
                    if l.publish_status.unpublished:
                        #Not published before.
                        failed_objects.append(("{0}:{1}".format(l.datasource,l.kmi_name),"Not published before, no need to empty gwc."))
                        continue

                    l.empty_gwc()
                except:
                    logger.error(traceback.format_exc())
                    error = sys.exc_info()
                    failed_objects.append(("{0}:{1}".format(l.datasource,l.kmi_name),traceback.format_exception_only(error[0],error[1])))
                    #remove failed, continue to process the next publish
                    continue
            try:
                try_push_to_repository('livelayer_admin',enforce=True)
            except:
                error = sys.exc_info()
                warning_message = traceback.format_exception_only(error[0],error[1])
                logger.error(traceback.format_exc())
        finally:
            try_clear_push_owner("livelayer_admin",enforce=True)

        if failed_objects or warning_message:
            if failed_objects:
                if warning_message:
                    messages.warning(request, mark_safe("<ul><li>{0}</li><li>Some selected layers are processed failed:<ul>{1}</ul></li></ul>".format(warning_message,"".join(["<li>{0} : {1}</li>".format(o[0],o[1]) for o in failed_objects]))))
                else:
                    messages.warning(request, mark_safe("Some selected layers are processed failed:<ul>{0}</ul>".format("".join(["<li>{0} : {1}</li>".format(o[0],o[1]) for o in failed_objects]))))
            else:
                messages.warning(request, mark_safe(warning_message))
        else:
            messages.success(request, "All selected layers are processed successfully.")

    empty_gwc.short_description = "Empty GWC"

    def publish(self,request,queryset):
        self._change_status(request,queryset,ResourceAction.PUBLISH,["status","last_publish_time"])
    publish.short_description = "Publish selected layers"

    def unpublish(self,request,queryset):
        self._change_status(request,queryset,ResourceAction.UNPUBLISH,["status","last_unpublish_time"])
    unpublish.short_description = "Unpublish selected layers"

    def _change_status(self,request,queryset,action,update_fields=None):
        result = None
        failed_objects = []
        try_set_push_owner("livelayer_admin",enforce=True)
        warning_message = None
        try:
            for l in queryset:
                try:
                    target_status = l.next_status(action)
                    if target_status == l.status and not l.publish_required and not l.unpublish_required:
                        #status not changed 
                        continue
                    else:
                        l.status = target_status
                        l.save(update_fields=update_fields)
                except:
                    logger.error(traceback.format_exc())
                    error = sys.exc_info()
                    failed_objects.append(("{0}:{1}".format(l.datasource,l.kmi_name),traceback.format_exception_only(error[0],error[1])))
                    #remove failed, continue to process the next publish
                    continue
            try:
                try_push_to_repository('livelayer_admin',enforce=True)
            except:
                error = sys.exc_info()
                warning_message = traceback.format_exception_only(error[0],error[1])
                logger.error(traceback.format_exc())
        finally:
            try_clear_push_owner("livelayer_admin",enforce=True)

        if failed_objects or warning_message:
            if failed_objects:
                if warning_message:
                    messages.warning(request, mark_safe("<ul><li>{0}</li><li>Some selected layers are processed failed:<ul>{1}</ul></li></ul>".format(warning_message,"".join(["<li>{0} : {1}</li>".format(o[0],o[1]) for o in failed_objects]))))
                else:
                    messages.warning(request, mark_safe("Some selected layers are processed failed:<ul>{0}</ul>".format("".join(["<li>{0} : {1}</li>".format(o[0],o[1]) for o in failed_objects]))))
            else:
                messages.warning(request, mark_safe(warning_message))
        else:
            messages.success(request, "All selected layers are processed successfully.")

    def get_search_results(self,request,queryset,search_term):
        try:
            datasource = Datasource.objects.get(pk = search_term)
            return self.model.objects.filter(datasource = datasource).order_by("name"),False
        except:
            return super(AbstractLayerAdmin,self).get_search_results(request,queryset,search_term)

    actions = ['publish','empty_gwc','unpublish','refresh']
    def get_actions(self, request):
        #import ipdb;ipdb.set_trace()
        actions = super(AbstractLayerAdmin, self).get_actions(request)
        del actions['delete_selected']
        return actions 

class LayerAdmin(AbstractLayerAdmin):
    pass

class PublishedLayerAdmin(AbstractLayerAdmin):
    def get_queryset(self,request):
        qs = super(PublishedLayerAdmin,self).get_queryset(request)
        return qs.filter(status__in = ResourceStatus.published_status)


class SqlViewLayerAdmin(admin.ModelAdmin):
    list_display = ("name","_workspace","_datasource","spatial_column","spatial_type","crs", "status","last_publish_time","last_refresh_time")
    readonly_fields = ("_workspace","spatial_column","spatial_type","crs","_bounding_box", "status","spatial_info_desc","_sql","last_publish_time","last_unpublish_time", "last_refresh_time","last_modify_time")
    search_fields = [ "name"]
    ordering = ("datasource","name")
    list_filter = ("datasource",)

    form = SqlViewLayerForm

    html = "<table > \
<tr > \
    <th style='width:100px;border-bottom:None' align='left'>Min X</th> \
    <th style='width:100px;border-bottom:None' align='left'>Min Y</th> \
    <th style='width:100px;border-bottom:None' align='left'>Max X</th> \
    <th style='width:100px;border-bottom:None' align='left'>Max Y</th> \
</tr> \
<tr> \
    <td style='border-bottom:None'>{}</td> \
    <td style='border-bottom:None'>{}</td> \
    <td style='border-bottom:None'>{}</td> \
    <td style='border-bottom:None'>{}</td> \
</tr> \
</table>"
    def _bounding_box(self,instance):
        bounding_box = ["-","-","-","-"]
        if instance.bbox:
            try:
                bounding_box = instance.bbox
                if not bounding_box:
                    bounding_box = ["-","-","-","-"]
            except:
                bounding_box = ["-","-","-","-"]

        return self.html.format(*bounding_box)
    _bounding_box.allow_tags = True
    _bounding_box.short_description = "Bounding Box"

    def _sql(self,o):
        if o.sql:
            return "<p style='white-space:normal'>" + o.sql + "</p>"
        else:
            return ''

    _sql.allow_tags = True
    _sql.short_description = "CREATE info for table"

    def _datasource(self,o):
        if o.datasource:
            return "<a href='/livelayermanager/datasource/{0}/'>{1}</a>".format(o.datasource.pk,o.datasource.name)
        else:
            return ""
    _datasource.allow_tags = True
    _datasource.short_description = "Datasource"
    _datasource.admin_order_field = "datasource"

    def _workspace(self,o):
        return o.datasource.workspace
    _workspace.short_description = "Workspace"
    _workspace.admin_order_field = "datasource__workspace"

    def has_add_permission(self,request):
        return True

    def has_delete_permission(self,request,obj=None):
        return True

    def refresh(self,request,queryset):
        result = None
        failed_layers = []
        for layer in queryset:
            #modify the table data
            try:
                layer.refresh()
            except:
                error = sys.exc_info()
                failed_layers.append((layer,traceback.format_exc()))
                continue

        if failed_layers:
            messages.warning(request, mark_safe("Refresh failed for some selected layers:<ul>{0}</ul>".format("".join(["<li>{0} : {1}</li>".format(o[0],o[1]) for o in failed_layers]))))
        else:
            messages.success(request, "Refresh successfully for all selected layers")

    refresh.short_description = "Refresh"
    
    def empty_gwc(self,request,queryset):
        result = None
        failed_objects = []
        try_set_push_owner("livesqlviewlayer_admin",enforce=True)
        warning_message = None
        try:
            for l in queryset:
                try:
                    if l.publish_status.unpublished:
                        #Not published before.
                        failed_objects.append(("{0}:{1}".format(l.datasource,l.kmi_name),"Not published before, no need to empty gwc."))
                        continue

                    l.empty_gwc()
                except:
                    logger.error(traceback.format_exc())
                    error = sys.exc_info()
                    failed_objects.append(("{0}:{1}".format(l.datasource,l.kmi_name),traceback.format_exception_only(error[0],error[1])))
                    #remove failed, continue to process the next publish
                    continue
            try:
                try_push_to_repository('livesqlviewlayer_admin',enforce=True)
            except:
                error = sys.exc_info()
                warning_message = traceback.format_exception_only(error[0],error[1])
                logger.error(traceback.format_exc())
        finally:
            try_clear_push_owner("livesqlviewlayer_admin",enforce=True)

        if failed_objects or warning_message:
            if failed_objects:
                if warning_message:
                    messages.warning(request, mark_safe("<ul><li>{0}</li><li>Some selected layers are processed failed:<ul>{1}</ul></li></ul>".format(warning_message,"".join(["<li>{0} : {1}</li>".format(o[0],o[1]) for o in failed_objects]))))
                else:
                    messages.warning(request, mark_safe("Some selected layers are processed failed:<ul>{0}</ul>".format("".join(["<li>{0} : {1}</li>".format(o[0],o[1]) for o in failed_objects]))))
            else:
                messages.warning(request, mark_safe(warning_message))
        else:
            messages.success(request, "All selected layers are processed successfully.")

    empty_gwc.short_description = "Empty GWC"

    def publish(self,request,queryset):
        self._change_status(request,queryset,ResourceAction.PUBLISH,["status","last_publish_time"])
    publish.short_description = "Publish selected layers"

    def unpublish(self,request,queryset):
        self._change_status(request,queryset,ResourceAction.UNPUBLISH,["status","last_unpublish_time"])
    unpublish.short_description = "Unpublish selected layers"

    def _change_status(self,request,queryset,action,update_fields=None):
        result = None
        failed_objects = []
        try_set_push_owner("livesqlviewlayer_admin",enforce=True)
        warning_message = None
        try:
            for l in queryset:
                try:
                    target_status = l.next_status(action)
                    if target_status == l.status and not l.publish_required and not l.unpublish_required:
                        #status not changed 
                        continue
                    else:
                        l.status = target_status
                        l.save(update_fields=update_fields)
                except:
                    logger.error(traceback.format_exc())
                    error = sys.exc_info()
                    failed_objects.append(("{0}:{1}".format(l.datasource,l.kmi_name),traceback.format_exception_only(error[0],error[1])))
                    #remove failed, continue to process the next publish
                    continue
            try:
                try_push_to_repository('livesqlviewlayer_admin',enforce=True)
            except:
                error = sys.exc_info()
                warning_message = traceback.format_exception_only(error[0],error[1])
                logger.error(traceback.format_exc())
        finally:
            try_clear_push_owner("livesqlviewlayer_admin",enforce=True)

        if failed_objects or warning_message:
            if failed_objects:
                if warning_message:
                    messages.warning(request, mark_safe("<ul><li>{0}</li><li>Some selected layers are processed failed:<ul>{1}</ul></li></ul>".format(warning_message,"".join(["<li>{0} : {1}</li>".format(o[0],o[1]) for o in failed_objects]))))
                else:
                    messages.warning(request, mark_safe("Some selected layers are processed failed:<ul>{0}</ul>".format("".join(["<li>{0} : {1}</li>".format(o[0],o[1]) for o in failed_objects]))))
            else:
                messages.warning(request, mark_safe(warning_message))
        else:
            messages.success(request, "All selected layers are processed successfully.")

    def get_search_results(self,request,queryset,search_term):
        try:
            datasource = Datasource.objects.get(pk = search_term)
            return self.model.objects.filter(datasource = datasource).order_by("name"),False
        except:
            return super(SqlViewLayerAdmin,self).get_search_results(request,queryset,search_term)

    actions = ['publish','empty_gwc','unpublish','refresh']
    def get_actions(self, request):
        #import ipdb;ipdb.set_trace()
        actions = super(SqlViewLayerAdmin, self).get_actions(request)
        return actions 


site.register(Datasource, DatasourceAdmin)
site.register(Layer, LayerAdmin)
site.register(SqlViewLayer, SqlViewLayerAdmin)
site.register(PublishedLayer, PublishedLayerAdmin)
