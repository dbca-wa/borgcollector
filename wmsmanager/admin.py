import sys,traceback
import logging
import json

from django.contrib import admin
from django.utils import timezone
from django.contrib import messages
from django.utils.safestring import mark_safe
from django.db import transaction

from wmsmanager.models import WmsServer, WmsLayer, PublishedWmsLayer, InterestedWmsLayer
from wmsmanager.forms import WmsServerForm,WmsLayerForm
from layergroup.models import LayerGroupLayers
from borg.admin import site
from borg_utils.resource_status import ResourceStatus,ResourceAction
from borg_utils.hg_batch_push import try_set_push_owner, try_clear_push_owner, increase_committed_changes, try_push_to_repository

logger = logging.getLogger(__name__)

class WmsServerAdmin(admin.ModelAdmin):
    list_display = ("name","capability_url","_layers", "status","last_publish_time","last_unpublish_time", "last_modify_time", "last_refresh_time")
    readonly_fields = ("_layers","status","last_publish_time", "last_modify_time","last_unpublish_time","last_refresh_time")
    search_fields = ["name","status"]

    actions = ['publish','unpublish','refresh_layers']
    ordering = ("name",)

    form = WmsServerForm

    def _layers(self,o):
        if o.layers > 0:
            return "<a href='/wmsmanager/wmslayer/?q={0}'>{1}</a>".format(o.name,o.layers)
        elif o.last_refresh_time:
            return "0"
        else:
            return ""
    _layers.allow_tags = True
    _layers.short_description = "Layers"
    _layers.admin_order_field = "layers"

    def refresh_layers(self,request,queryset):
        result = None
        failed_servers = []
        for server in queryset:
            #modify the table data
            try:
                server.refresh_layers()
                server.save()
                
            except:
                error = sys.exc_info()
                #failed_servers.append((server.name,traceback.format_exception_only(error[0],error[1])))
                failed_servers.append((server.name,traceback.format_exc()))
                #update table failed, continue to process the next server
                continue

        if failed_servers:
            messages.warning(request, mark_safe("Refresh failed for some selected servers:<ul>{0}</ul>".format("".join(["<li>{0} : {1}</li>".format(o[0],o[1]) for o in failed_servers]))))
        else:
            messages.success(request, "Refresh successfully for all selected servers")

    refresh_layers.short_description = "Refresh WMS Layers"
    
    def publish(self,request,queryset):
        self._change_status(request,queryset,ResourceAction.PUBLISH,["status","last_publish_time"])
    publish.short_description = "Publish selected servers"

    def unpublish(self,request,queryset):
        self._change_status(request,queryset,ResourceAction.UNPUBLISH,["status","last_unpublish_time"])
    unpublish.short_description = "Unpublish selected servers"

    def _change_status(self,request,queryset,action,update_fields=None):
        result = None
        failed_objects = []
        try_set_push_owner("wmsserver_admin",enforce=True)
        warning_message = None
        try:
            for server in queryset:
                #import ipdb;ipdb.set_trace()
                try:
                    target_status = server.next_status(action)
                    if target_status == server.status and not server.publish_required and not server.unpublish_required:
                        #status not changed
                        continue
                    else:
                        server.status = target_status
                        server.save(update_fields=update_fields)
                except:
                    logger.error(traceback.format_exc())
                    error = sys.exc_info()
                    failed_objects.append(("{0}:{1}".format(server.workspace.name,server.name),traceback.format_exception_only(error[0],error[1])))
                    #remove failed, continue to process the next publish
                    continue
            try:
                try_push_to_repository('wmsserver_admin',enforce=True)
            except:
                error = sys.exc_info()
                warning_message = traceback.format_exception_only(error[0],error[1])
                logger.error(traceback.format_exc())
        finally:
            try_clear_push_owner("wmsserver_admin",enforce=True)

        if failed_objects or warning_message:
            if failed_objects:
                if warning_message:
                    messages.warning(request, mark_safe("<ul><li>{0}</li><li>Some selected servers are processed failed:<ul>{1}</ul></li></ul>".format(warning_message,"".join(["<li>{0} : {1}</li>".format(o[0],o[1]) for o in failed_objects]))))
                else:
                    messages.warning(request, mark_safe("Some selected servers are processed failed:<ul>{0}</ul>".format("".join(["<li>{0} : {1}</li>".format(o[0],o[1]) for o in failed_objects]))))
            else:
                messages.warning(request, mark_safe(warning_message))
        else:
            messages.success(request, "All selected servers are processed successfully.")

    def custom_delete_selected(self,request,queryset):
        if request.POST.get('post') != 'yes':
            #the confirm page, or user not confirmed
            return self.default_delete_action[0](self,request,queryset)
    
        result = None
        failed_objects = []
        try_set_push_owner("wmsserver_admin",enforce=True)
        warning_message = None
        try:
            for server in queryset:
                #import ipdb;ipdb.set_trace()
                try:
                    #delete the server
                    server.delete()
                except:
                    logger.error(traceback.format_exc())
                    error = sys.exc_info()
                    failed_objects.append(("{0}:{1}".format(server.workspace.name,server.name),traceback.format_exception_only(error[0],error[1])))
                    #remove failed, continue to process the next publish
                    continue
            try:
                try_push_to_repository('wmsserver_admin',enforce=True)
            except:
                error = sys.exc_info()
                warning_message = traceback.format_exception_only(error[0],error[1])
                logger.error(traceback.format_exc())
        finally:
            try_clear_push_owner("wmsserver_admin",enforce=True)

        if failed_objects or warning_message:
            if failed_objects:
                if warning_message:
                    messages.warning(request, mark_safe("<ul><li>{0}</li><li>Some selected servers are deleted failed:<ul>{1}</ul></li></ul>".format(warning_message,"".join(["<li>{0} : {1}</li>".format(o[0],o[1]) for o in failed_objects]))))
                else:
                    messages.warning(request, mark_safe("Some selected servers are deleted failed:<ul>{0}</ul>".format("".join(["<li>{0} : {1}</li>".format(o[0],o[1]) for o in failed_objects]))))
            else:
                messages.warning(request, mark_safe(warning_message))
        else:
            messages.success(request, "All selected ervers are deleted successfully.")

    def get_actions(self, request):
        actions = super(WmsServerAdmin, self).get_actions(request)
        self.default_delete_action = actions['delete_selected']
        del actions['delete_selected']
        actions['delete_selected'] = (WmsServerAdmin.custom_delete_selected,self.default_delete_action[1],self.default_delete_action[2])
        return actions 

class AbstractWmsLayerAdmin(admin.ModelAdmin):
    list_display = ("name","kmi_name","_workspace","_server","title","crs", "status","last_publish_time","last_unpublish_time","last_modify_time")
    readonly_fields = ("_workspace","_server","path","title","abstract","crs","_bounding_box", "status","applications","last_publish_time","last_unpublish_time", "last_refresh_time","last_modify_time")
    search_fields = ["name", "title"]
    ordering = ("server","name",)
    list_filter = ("server",)

    form = WmsLayerForm

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
                bounding_box = json.loads(instance.bbox)
                if not bounding_box or not isinstance(bounding_box,list) or len(bounding_box) != 4:
                    bounding_box = ["-","-","-","-"]
            except:
                bounding_box = ["-","-","-","-"]

        return self.html.format(*bounding_box)
    _bounding_box.allow_tags = True
    _bounding_box.short_description = "Bounding Box"

    def _server(self,o):
        if o.server:
            return "<a href='/wmsmanager/wmsserver/{0}'>{1}</a>".format(o.server.pk,o.server.name)
        else:
            return ""
    _server.allow_tags = True
    _server.short_description = "WMS Server"
    _server.admin_order_field = "server"

    def _workspace(self,o):
        return o.server.workspace
    _workspace.short_description = "Workspace"
    _workspace.admin_order_field = "server__workspace"

    def has_add_permission(self,request):
        return False

    def has_delete_permission(self,request,obj=None):
        return False

    def empty_gwc(self,request,queryset):
        result = None
        failed_objects = []
        try_set_push_owner("wmslayer_admin",enforce=True)
        warning_message = None
        try:
            for l in queryset:
                try:
                    if l.publish_status.unpublished:
                        #Not published before.
                        failed_objects.append(("{0}:{1}".format(l.server,l.name),"Not published before, no need to empty gwc."))
                        continue

                    l.empty_gwc()
                    #empty the related layergroup's cache
                    for layer in LayerGroupLayers.objects.filter(layer = l):
                        target_status = layer.group.next_status(ResourceAction.CASCADE_PUBLISH)
                        if layer.group.publish_required:
                            layer.group.empty_gwc()
                    
                except:
                    logger.error(traceback.format_exc())
                    error = sys.exc_info()
                    failed_objects.append(("{0}:{1}".format(l.server,l.name),traceback.format_exception_only(error[0],error[1])))
                    #remove failed, continue to process the next publish
                    continue
            try:
                try_push_to_repository('wmslayer_admin',enforce=True)
            except:
                error = sys.exc_info()
                warning_message = traceback.format_exception_only(error[0],error[1])
                logger.error(traceback.format_exc())
        finally:
            try_clear_push_owner("wmslayer_admin",enforce=True)

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
        try_set_push_owner("wmslayer_admin",enforce=True)
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
                    failed_objects.append(("{0}:{1}".format(l.server,l.name),traceback.format_exception_only(error[0],error[1])))
                    #remove failed, continue to process the next publish
                    continue
            try:
                try_push_to_repository('wmslayer_admin',enforce=True)
            except:
                error = sys.exc_info()
                warning_message = traceback.format_exception_only(error[0],error[1])
                logger.error(traceback.format_exc())
        finally:
            try_clear_push_owner("wmslayer_admin",enforce=True)

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
            server = WmsServer.objects.get(pk = search_term)
            return self.model.objects.filter(server = server).order_by("name"),False
        except:
            return super(AbstractWmsLayerAdmin,self).get_search_results(request,queryset,search_term)

    actions = ['publish','empty_gwc','unpublish']
    def get_actions(self, request):
        #import ipdb;ipdb.set_trace()
        actions = super(AbstractWmsLayerAdmin, self).get_actions(request)
        del actions['delete_selected']
        return actions 

class WmsLayerAdmin(AbstractWmsLayerAdmin):
    pass

class PublishedWmsLayerAdmin(AbstractWmsLayerAdmin):
    def get_queryset(self,request):
        qs = super(PublishedWmsLayerAdmin,self).get_queryset(request)
        return qs.filter(status__in = ResourceStatus.published_status)

class InterestedWmsLayerAdmin(AbstractWmsLayerAdmin):
    def get_queryset(self,request):
        qs = super(InterestedWmsLayerAdmin,self).get_queryset(request)
        return qs.exclude(status = ResourceStatus.New.name,last_modify_time = None)

site.register(WmsServer, WmsServerAdmin)
site.register(WmsLayer, WmsLayerAdmin)
site.register(PublishedWmsLayer, PublishedWmsLayerAdmin)
site.register(InterestedWmsLayer, InterestedWmsLayerAdmin)
