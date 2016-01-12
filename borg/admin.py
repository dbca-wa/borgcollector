from django.contrib import admin
from django.contrib.auth import models as auth_models

site = admin.AdminSite()
site.register(auth_models.User, admin.ModelAdmin)
site.register(auth_models.Group, admin.ModelAdmin)
