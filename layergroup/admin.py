import sys,traceback
import logging

from django.contrib import admin
from django.utils import timezone
from django.contrib import messages
from django.utils.safestring import mark_safe
from django.db import transaction

from layergroup.models import LayerGroup,LayerGroupLayers
from layergroup.forms import LayerGroupForm,LayerGroupLayersForm
from borg.admin import site
from borg_utils.resource_status import ResourceStatus,ResourceAction
from borg_utils.hg_batch_push import try_set_push_owner, try_clear_push_owner, increase_committed_changes, try_push_to_repository

logger = logging.getLogger(__name__)

class LayerGroupAdmin(admin.ModelAdmin):
    list_display = ("name","workspace" ,"title","srs", "status","last_publish_time","last_unpublish_time", "last_modify_time","_layers")
    readonly_fields = ("status","last_publish_time","last_unpublish_time","last_modify_time","_layers")
    search_fields = ["name","status"]
    ordering = ("name",)

    form = LayerGroupForm

    def _layers(self,o):
        return "<a href='/layergroup/layergrouplayers/?q={}'>Layers</a>".format(o.name)

    _layers.allow_tags = True
    _layers.short_description = "Layers"

    def publish(self,request,queryset):
        self._change_status(request,queryset,ResourceAction.PUBLISH,["status","last_publish_time","last_unpublish_time"])
    publish.short_description = "Publish selected groups"

    def unpublish(self,request,queryset):
        self._change_status(request,queryset,ResourceAction.UNPUBLISH,["status","last_unpublish_time"])
    unpublish.short_description = "Unpublish selected groups"

    def _change_status(self,request,queryset,action,update_fields=None):
        result = None
        failed_objects = []
        try_set_push_owner("layergroup_admin",enforce=True)
        warning_message = None
        try:
            for group in queryset:
                #import ipdb;ipdb.set_trace()
                try:
                    target_status = group.next_status(action)
                    if target_status == group.status and not group.publish_required and not group.unpublish_required:
                        #status not changed
                        continue
                    else:
                        group.status = target_status
                        group.save(update_fields=update_fields)
                except:
                    logger.error(traceback.format_exc())
                    error = sys.exc_info()
                    failed_objects.append(("{0}".format(group.name),traceback.format_exception_only(error[0],error[1])))
                    #remove failed, continue to process the next publish
                    continue
            try:
                try_push_to_repository('layergroup_admin',enforce=True)
            except:
                error = sys.exc_info()
                warning_message = traceback.format_exception_only(error[0],error[1])
                logger.error(traceback.format_exc())
        finally:
            try_clear_push_owner("layergroup_admin",enforce=True)

        if failed_objects or warning_message:
            if failed_objects:
                if warning_message:
                    messages.warning(request, mark_safe("<ul><li>{0}</li><li>Some selected groups are processed failed:<ul>{1}</ul></li></ul>".format(warning_message,"".join(["<li>{0} : {1}</li>".format(o[0],o[1]) for o in failed_objects]))))
                else:
                    messages.warning(request, mark_safe("Some selected groups are processed failed:<ul>{0}</ul>".format("".join(["<li>{0} : {1}</li>".format(o[0],o[1]) for o in failed_objects]))))
            else:
                messages.warning(request, mark_safe(warning_message))
        else:
            messages.success(request, "All groups are processed successfully.")

    def custom_delete_selected(self,request,queryset):
        if request.POST.get('post') != 'yes':
            #the confirm page, or user not confirmed
            return self.default_delete_action[0](self,request,queryset)
    
        result = None
        failed_objects = []
        try_set_push_owner("layergroup_admin",enforce=True)
        warning_message = None
        try:
            for group in queryset:
                #import ipdb;ipdb.set_trace()
                try:
                    #delete the group
                    group.delete()
                except:
                    logger.error(traceback.format_exc())
                    error = sys.exc_info()
                    failed_objects.append(("{0}:{1}".format(group.workspace.name,group.name),traceback.format_exception_only(error[0],error[1])))
                    #remove failed, continue to process the next group
                    continue
            try:
                try_push_to_repository('layergroup_admin',enforce=True)
            except:
                error = sys.exc_info()
                warning_message = traceback.format_exception_only(error[0],error[1])
                logger.error(traceback.format_exc())
        finally:
            try_clear_push_owner("layergroup_admin",enforce=True)

        if failed_objects or warning_message:
            if failed_objects:
                if warning_message:
                    messages.warning(request, mark_safe("<ul><li>{0}</li><li>Some selected layer groups are deleted failed:<ul>{1}</ul></li></ul>".format(warning_message,"".join(["<li>{0} : {1}</li>".format(o[0],o[1]) for o in failed_objects]))))
                else:
                    messages.warning(request, mark_safe("Some selected layer groups are deleted failed:<ul>{0}</ul>".format("".join(["<li>{0} : {1}</li>".format(o[0],o[1]) for o in failed_objects]))))
            else:
                messages.warning(request, mark_safe(warning_message))
        else:
            messages.success(request, "All selected layer groups are deleted successfully.")

    def empty_gwc(self,request,queryset):
        result = None
        failed_objects = []
        try_set_push_owner("layergroup_admin",enforce=True)
        warning_message = None
        try:
            for g in queryset:
                try:
                    if g.publish_status.unpublished:
                        #Not published before.
                        failed_objects.append(("{0}:{1}".format(g.workspace,g.name),"Not published before, no need to empty gwc."))
                        continue

                    g.empty_gwc()
                except:
                    logger.error(traceback.format_exc())
                    error = sys.exc_info()
                    failed_objects.append(("{0}:{1}".format(l.server,l.name),traceback.format_exception_only(error[0],error[1])))
                    #remove failed, continue to process the next publish
                    continue
            try:
                try_push_to_repository('layergroup_admin',enforce=True)
            except:
                error = sys.exc_info()
                warning_message = traceback.format_exception_only(error[0],error[1])
                logger.error(traceback.format_exc())
        finally:
            try_clear_push_owner("layergroup_admin",enforce=True)

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

    actions = ['publish','empty_gwc','unpublish']
    def get_actions(self, request):
        #import ipdb;ipdb.set_trace()
        actions = super(LayerGroupAdmin, self).get_actions(request)
        self.default_delete_action = actions['delete_selected']
        del actions['delete_selected']
        actions['delete_selected'] = (LayerGroupAdmin.custom_delete_selected,self.default_delete_action[1],self.default_delete_action[2])
        return actions 

class LayerGroupLayersAdmin(admin.ModelAdmin):
    list_display = ("id","_group","order" ,"_wmslayer")
    readonly_fields = ()
    search_fields = ["group__name","layer__name"]
    ordering = ["group","order"]

    form = LayerGroupLayersForm

    def _group(self,o):
        return "<a href='/layergroup/layergroup/{0}/'>{1}</a>".format(o.group.pk,o.group.name)

    _group.allow_tags = True
    _group.short_description = "Group"

    def _wmslayer(self,o):
        if o.layer:
            return "<a href='/wmsmanager/wmslayer/{0}'>{1}</a>".format(o.layer.pk,o.layer.name)
        else:
            return ""
    _wmslayer.allow_tags = True
    _wmslayer.short_description = "WMS Layer"
    _wmslayer.admin_order_field = "layer__name"

site.register(LayerGroup, LayerGroupAdmin)
site.register(LayerGroupLayers, LayerGroupLayersAdmin)
