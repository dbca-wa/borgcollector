from django.core.management.base import BaseCommand
from optparse import make_option

from harvest.jobstatemachine import JobStatemachine
from harvest.harvest_ds_modifytime import HarvestModifyTime

class Command(BaseCommand):
    help = 'Running harvest job'

    option_list = BaseCommand.option_list + (
        make_option(
            '-j',
            '--job-id',
            action='store',
            dest='job_id',
            default=None,
            help='The required run job id'
        ),
        make_option(
            '-s',
            '--job-state',
            action='store',
            dest='job_state',
            default=None,
            help='The current job state'
        ),
        make_option(
            '-a',
            '--action',
            action='store',
            dest='user_action',
            default=None,
            help='The user action'
        ),
        make_option(
            '-i',
            '--interval',
            action='store',
            dest='run_interval',
            default=None,
            help='Run interval'
        ),
        make_option(
            '--check',
            action='store_true',
            dest='check_datasource',
            default=False,
            help='Check datasource\'s last modify time; meanless if job id is specified.'
        ),
        make_option(
            '--check-interval',
            action='store',
            dest='check_interval',
            default=None,
            help='The interval(in minutes) to check datasource\'s last modify time; meanless if check datasource is disabled.'
        ),
    )

    def handle(self, *args, **options):
        check = options["check_datasource"]
        check_interval = 0
        if check:
            try:
                check_interval = int(options["check_interval"]) * 60
                if check_interval < 0:
                    check_interval = 0
            except:
                check_interval = 0

        # Parse the days argument as an integer.
        if options['job_id']:
            try:
                options['job_id'] = int(options['job_id'])
            except:
                raise Exception("job id should be integer")

            if options['user_action']:
                if options['job_state']:
                    JobStatemachine.send_user_action(options['job_id'],options['job_state'],options['user_action'])
                else:
                    JobStatemachine.send_user_action(options['job_id'],None,options['user_action'])
            elif options['job_state']:
                raise Exception("missing action parameter")
            else:
                JobStatemachine.run_job(options['job_id'])
        elif options['run_interval']:
            try:
                options['run_interval'] = int(options['run_interval'])
            except:
                raise Exception("job id should be a positive integer.")

            if options['run_interval'] <= 0:
                raise Exception("job id should be a positive integer.")

            HarvestModifyTime(check,check_interval,True).harvest()
            JobStatemachine.running(options['run_interval'])
        elif check:
            HarvestModifyTime(check,check_interval).harvest()
        else:
            JobStatemachine.run_all_jobs()

        return 0
