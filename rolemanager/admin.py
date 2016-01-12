from django.contrib import admin

from borg.admin import site
from rolemanager.models import User,Role,SyncLog

class UserAdmin(admin.ModelAdmin):
    list_display = ("name", "status", "_synced_roles", "_latest_roles","last_sync_time", "last_update_time")
    readonly_fields = ("name", "status", "_synced_roles", "_latest_roles","last_sync_time", "last_update_time")
    search_fields = ["name","synced_roles","latest_roles","status"]
    actions = None
    ordering = ("name",)

    def _latest_roles(self,o):
        if o.latest_roles:
            return ",".join(o.latest_roles)
        else:
            return ""
    _latest_roles.short_description = "Latest Roles"

    def _synced_roles(self,o):
        if o.synced_roles:
            return ",".join(o.synced_roles)
        else:
            return ""
    _synced_roles.short_description = "Synced Roles"

    def has_add_permission(self,request):
        return False

    def has_delete_permission(self,request,obj=None):
        return False

    class Media:
        js = ('/static/js/admin-model-readonly.js',)

class RoleAdmin(admin.ModelAdmin):
    list_display = ("name", "status","last_sync_time", "last_update_time")
    readonly_fields = ("name", "status","last_sync_time", "last_update_time")
    search_fields = ["name"]
    ordering = ("name",)
    actions = None

    def has_add_permission(self,request):
        return False

    def has_delete_permission(self,request,obj=None):
        return False

    class Media:
        js = ('/static/js/admin-model-readonly.js',)

class SyncLogAdmin(admin.ModelAdmin):
    list_display = ("sync_time","automatic", "load_status","commit_status","push_status","end_time")
    readonly_fields = ("sync_time","automatic", "load_status","commit_status","push_status","end_time","_message")
    actions = None

    def _message(self,o):
        if o.message:
            return "<p style='white-space:pre'>" + o.message + "</p>"
        else:
            return ''

    _message.allow_tags = True
    _message.short_description = "Message"

    def has_add_permission(self,request):
        return False

    def has_delete_permission(self,request,obj=None):
        return False

    class Media:
        js = ('/static/js/admin-model-readonly.js',)


site.register(User, UserAdmin)
site.register(Role, RoleAdmin)
site.register(SyncLog, SyncLogAdmin)
