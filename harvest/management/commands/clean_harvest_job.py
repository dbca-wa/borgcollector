from django.core.management.base import BaseCommand
from optparse import make_option

from harvest.jobcleaner import HarvestJobCleaner

class Command(BaseCommand):
    help = 'Clean outdated harvest job'
    option_list = BaseCommand.option_list + (
        make_option(
            '-e',
            '--expire-days',
            action='store',
            dest='expire_days',
            help='The expire days of a job after publish time; default is 90'
        ),
        make_option(
            '-n',
            '--min-jobs',
            action='store',
            dest='min_jobs',
            help='The specified number of successful jobs should be kept in the system for each publish; default is 1'
        ),
    )

    def handle(self, *args, **options):
        # Parse the days argument as an integer.
        if options['expire_days']:
            try:
                options['expire_days'] = int(options['expire_days'])
            except:
                raise Exception("expire-days should be integer")

            if options['expire_days'] < 0:
                raise Exception("expire-days should not be negative integer")
        else:
            options['expire_days'] = 90

        if options['min_jobs']:
            try:
                options['min_jobs'] = int(options['min_jobs'])
            except:
                raise Exception("min-jobs should be positive integer")

            if options['min_jobs'] <= 0:
                raise Exception("min-jobs should be positive integer")
        else:
            options['min_jobs'] = 1

        HarvestJobCleaner(options['expire_days'],options['min_jobs']).clean()

        return 0
