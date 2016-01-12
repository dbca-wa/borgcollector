import logging
import json
import hglib
import os
import traceback
import pytz
from datetime import datetime
from io import open

from django.utils import timezone
from django.db import transaction
from django.db.models import F,Q
from django.core.exceptions import ObjectDoesNotExist
from django.template.loader import render_to_string

from borg_utils.borg_config import BorgConfiguration
from rolemanager.models import Role,User,UserRoleStatus,UserRoleSyncStatus,SyncLog
from tablemanager.models import PublishChannel

logger = logging.getLogger(__name__)

class UserRoleSyncUtil(object):
    """
    The thread to load user roles and upload to the repository
    """
    def __init__(self): 
        raise Exception("Utility class, can not instantiate.")

    @staticmethod
    def load_userrole(sync_log):
        """
        Load the user and role from json file into table
        """
        sync_log.load_status = UserRoleSyncStatus.FAILED

        now = timezone.now()
        if BorgConfiguration.USERLIST.startswith("http"):
            # Load JSON user/group dump from URL
            data = request.get(BorgConfiguration.USERLIST, 
                            auth=requests.auth.HTTPBasicAuth(
                                BorgConfiguration.USERLIST_USERNAME,
                                BorgConfiguration.USERLIST_PASSWORD
                            ))
            
            if data.status_code != 200:
                raise Exception("GET {} returned HTTP status {}".format(BorgConfiguration.USERLIST, data.status_code))
            
            user_data_raw = data.content
        else:
            user_data_raw = open(BorgConfiguration.USERLIST, "rb").read()

        user_data = json.loads(user_data_raw.decode("utf-8-sig"))
        
        # Sort data alphabetically, order it for the template
        keys = user_data.keys()
        users = [(k, sorted(user_data[k])) for k in keys]
        roles = set()
        for g in user_data.values():
            roles.update(g)

        row = None
        #remove the removed roles.
        Role.objects.exclude(status__in=[UserRoleStatus.REMOVE,UserRoleStatus.REMOVED]).exclude(pk__in=roles).update(status=UserRoleStatus.REMOVE,last_update_time=now)
        #update the existing roels or add non existing roles
        for r in roles:
            try:
                row = Role.objects.get(pk=r)
                if row.status == UserRoleStatus.REMOVED:
                    row.status = UserRoleStatus.NEW
                    row.last_update_time = now
                    row.save()
            except ObjectDoesNotExist:
                row = Role(name=r,status=UserRoleStatus.NEW,last_update_time = now)
                row.save()

        #remove the removed users.
        User.objects.exclude(status__in=[UserRoleStatus.REMOVE,UserRoleStatus.REMOVED]).exclude(pk__in=keys).update(status=UserRoleStatus.REMOVE,last_update_time=now,latest_roles=None)
        for u in users:
            try:
                row = User.objects.get(pk=u[0])
                if row.status in [UserRoleStatus.REMOVED,UserRoleStatus.REMOVE]:
                    row.status = UserRoleStatus.NEW
                    row.last_update_time = now
                    row.latest_roles = u[1]
                    row.save()
                elif row.synced_roles != u[1]:
                    row.status = UserRoleStatus.UPDATE
                    row.last_update_time = now
                    row.latest_roles = u[1]
                    row.save()
            except ObjectDoesNotExist:
                row = User(name=u[0],synced_roles=None,latest_roles=u[1],status=UserRoleStatus.NEW,last_update_time=now)
                row.save()

        sync_log.load_status = UserRoleSyncStatus.SUCCEED
        
    @staticmethod
    def sync_userrole(force,sync_log):
        """
        1.generate the sql file to populate postgres role and geoserver user,role
        2.commit and push the sql file to repository
        """
        #import ipdb;ipdb.set_trace()
        # Generate user data SQL through template
        sync_log.commit_status = UserRoleSyncStatus.FAILED
        sync_log.push_status = UserRoleSyncStatus.NOT_EXECUTED

        hg = hglib.open(BorgConfiguration.BORG_STATE_REPOSITORY)
        try:
            changed = force
            if not changed:
                modified_rows = User.objects.filter(status__in = [UserRoleStatus.REMOVE,UserRoleStatus.NEW,UserRoleStatus.UPDATE])
                if modified_rows.count() == 0:
                    modified_rows = Role.objects.filter(status__in = [UserRoleStatus.REMOVE,UserRoleStatus.NEW])
                    changed = modified_rows.count() > 0
                else:
                    changed = True
                

            if not changed :
                sync_log.commit_status = UserRoleSyncStatus.NOT_CHANGED
            else:
                all_roles = Role.objects.all().order_by('name')

                removed_roles = [r for r in all_roles if r.status in [UserRoleStatus.REMOVE,UserRoleStatus.REMOVED]]
                roles = [r for r in all_roles if r.status not in [UserRoleStatus.REMOVE,UserRoleStatus.REMOVED]]

                all_users = User.objects.all().order_by('name')
                removed_users = [u for u in all_users if u.status in [UserRoleStatus.REMOVE,UserRoleStatus.REMOVED]]
                users = [u for u in all_users if u.status not in [UserRoleStatus.REMOVE,UserRoleStatus.REMOVED]]

                title = "Automatically generated by borg collector at {0}".format(timezone.now())

                # Try and commit to repository, if no changes then continue
                result = render_to_string("slave_roles_2.sql", {"removed_users": removed_users,"users": users, "removed_roles": removed_roles,"roles":roles,"title":title})
                # Write output SQL file, commit + push
                output_filename = os.path.join(BorgConfiguration.BORG_STATE_REPOSITORY, "slave_roles.sql")
                #create dir if required
                if not os.path.exists(os.path.dirname(output_filename)):
                    os.makedirs(os.path.dirname(output_filename))

                with open(output_filename, "w", encoding="utf-8") as output:
                    output.write(result)

                # Try and commit to repository, if no changes then continue
                if hg.status():
                    hg.commit(include=[output_filename],addremove=True, user="borgcollector", message="roles updated")
                    sync_log.commit_status = UserRoleSyncStatus.SUCCEED
                else:
                    sync_log.commit_status = UserRoleSyncStatus.NOT_CHANGED


            sync_log.push_status = UserRoleSyncStatus.FAILED
            hg.push(ssh=BorgConfiguration.BORG_STATE_SSH)
            sync_log.push_status = UserRoleSyncStatus.SUCCEED

            now = timezone.now()
            if changed:
                with transaction.atomic():
                    Role.objects.filter(status__in=[UserRoleStatus.REMOVED,UserRoleStatus.REMOVE]).update(last_sync_time=now,status=UserRoleStatus.REMOVED)
                    Role.objects.exclude(status=UserRoleStatus.REMOVED).update(last_sync_time=now,status=UserRoleStatus.SYNCED)

                    User.objects.filter(status__in=[UserRoleStatus.REMOVED,UserRoleStatus.REMOVE]).update(last_sync_time=now,status=UserRoleStatus.REMOVED,synced_roles=None)
                    User.objects.exclude(status=UserRoleStatus.REMOVED).update(last_sync_time=now,status=UserRoleStatus.SYNCED,synced_roles=F("latest_roles"))
        finally:
            hg.close()

    @staticmethod
    def sync(automatic,load=None,distribute=None):
        """
        invoke the load_userrole and upload_userrole to sync user role.
        """
        sync_log = SyncLog(sync_time = timezone.now(),automatic=automatic,message=None,load_status=UserRoleSyncStatus.NO_NEED,commit_status=UserRoleSyncStatus.NO_NEED,push_status=UserRoleSyncStatus.NO_NEED)
        try:
            if automatic:
                UserRoleSyncUtil.load_userrole(sync_log)
                UserRoleSyncUtil.sync_userrole(False,sync_log)
            else:
                if load:
                    UserRoleSyncUtil.load_userrole(sync_log)

                if distribute:
                    UserRoleSyncUtil.sync_userrole(True,sync_log)

        except:
            sync_log.message = traceback.format_exc()
            if not automatic:
                raise
        finally:
            sync_log.end_time = timezone.now()
            sync_log.save()

