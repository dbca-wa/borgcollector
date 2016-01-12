from django.core.management.base import BaseCommand
from optparse import make_option

from rolemanager.sync import UserRoleSyncUtil

class Command(BaseCommand):
    help = 'Synchronize user and role'

    option_list = BaseCommand.option_list + (
        make_option(
            '-l',
            '--load',
            action='store_true',
            dest='is_load',
            default=None,
            help='Load the user,role data into table'
        ),
        make_option(
            '-s',
            '--sync',
            action='store_true',
            dest='is_sync',
            default=None,
            help='Sync the user,role data from table to postgres role and geoserver user,role '
        ),
    )

    def handle(self, *args, **options):

        # Parse the days argument as an integer.
        is_load = True
        is_sync = True
        is_automatic = True
        if options['is_load'] or options['is_sync']:
            is_automatic = False
            is_load = False
            is_sync = False

            if options['is_load']:
                is_load = True

            if options['is_sync']:
                is_sync = True

        UserRoleSyncUtil.sync(is_automatic,is_load,is_sync)

        return 0
