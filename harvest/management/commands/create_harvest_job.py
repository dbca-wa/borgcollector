from django.core.management.base import BaseCommand
from optparse import make_option

from borg_utils.jobintervals import JobInterval,Manually
from harvest.jobstatemachine import JobStatemachine

JobInterval._initialize()

class Command(BaseCommand):
    help = 'Create harvest job'
    option_list = BaseCommand.option_list + (
        make_option(
            '-i',
            '--interval',
            action='store',
            dest='interval_choice',
            help='Create harvest job for all the Publish objects marked with this interval (valid args: {})'.format(', '.join(JobInterval._interval_dict.keys()))
        ),
        make_option(
            '-p',
            '--publish-id',
            action='store',
            dest='publish_id',
            help='Create harvest job for the one Publish object with specified id'
        ),
        make_option(
            '-n',
            '--publish-name',
            action='store',
            dest='publish_name',
            help='Create harvest job for the one Publish object with specified name'
        ),
    )

    def handle(self, *args, **options):
        # Parse the days argument as an integer.
        if options['interval_choice']:
            if options['publish_id'] or options['publish_name'] :
                raise Exception("Three options cannot be used together.")
            else:
                interval = JobInterval.get_interval(options['interval_choice'])
                JobStatemachine.create_jobs(interval)
        elif options['publish_id']:
            if options['publish_name']:
                raise Exception("Three options cannot be used together.")
            else:
                JobStatemachine.create_job(options['publish_id'],Manually.instance())
        elif options['publish_name']:
            JobStatemachine.create_job_by_name(options['publish_name'],Manually.instance())
        else:
            raise Exception("No option is specified")

        return 0
