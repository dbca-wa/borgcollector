from django.utils import timezone

from borg_utils.singleton import SingletonMetaclass,Singleton

class JobIntervalMetaclass(SingletonMetaclass):
    """
    A metaclass for job interval class
    """
    _classes = []
    def __init__(cls,name,base,dct):
        """
        cache all JobInterval sub classes.
        """
        super(JobIntervalMetaclass,cls).__init__(name,base,dct)
        if name != 'JobInterval':
            JobIntervalMetaclass._classes.append(cls)

    @property
    def all_classes(self):
        return JobIntervalMetaclass._classes

class JobInterval(Singleton):
    """
    super class for job interval.
    """
    __metaclass__ = JobIntervalMetaclass

    _all_intervals = None
    _interval_dict = None
    _all_options = None

    @staticmethod
    def _initialize():
        if not JobInterval._all_intervals:
            JobInterval._all_intervals = [c() for c in JobInterval.all_classes ]
            JobInterval._interval_dict = dict([(o.name.lower(),o) for o in JobInterval._all_intervals])
            JobInterval._all_options = tuple([(o.name,o.name) for o in JobInterval._all_intervals if o not in [Realtime.instance(),Triggered.instance()]])
        

    @staticmethod
    def all_intervals():
        """
        return all possible job intervals.
        """
        JobInterval._initialize()

        return JobInterval._all_intervals

    @staticmethod
    def get_interval(interval):
        """
        if interval is correct, return the job interval instance.
        otherwise throw exception
        """
        if isinstance(interval, JobInterval):
            #interval is a job interval instance, return directly
            return interval

        JobInterval._initialize()

        try:
            return JobInterval._interval_dict[interval.lower()]
        except:
            raise ValueError("The job interval {0} is not recognized.".format(interval))

    @property
    def job_batch_id(self):
        raise NotImplementedError("The method 'execute' is not implemented.")

    @property
    def name(self):
        return self._name

    @staticmethod
    def all_options():
        JobInterval._initialize()
        return JobInterval._all_options

    def __str__(self):
        return self._name

class Manually(JobInterval):
    _name = "Manually"

    @property
    def job_batch_id(self):
        return timezone.localtime(timezone.now()).strftime('%Y%m%dT%H%M%S')

class Triggered(JobInterval):
    _name = "Triggered"

    @property
    def job_batch_id(self):
        return timezone.localtime(timezone.now()).strftime('%Y%m%dT%H%M%S')

class Realtime(JobInterval):
    _name = "Realtime"

    @property
    def job_batch_id(self):
        return timezone.localtime(timezone.now()).strftime('%Y%m%dT%H%M%S')

class Hourly(JobInterval):
    _name = "Hourly"

    @property
    def job_batch_id(self):
        return timezone.localtime(timezone.now()).strftime('%Y%m%dT%H%M%S')

class Daily(JobInterval):
    _name = "Daily"

    @property
    def job_batch_id(self):
        return timezone.localtime(timezone.now()).strftime('%Y%m%dT%H%M%S')

class Weekly(JobInterval):
    _name = "Weekly"

    @property
    def job_batch_id(self):
        return timezone.localtime(timezone.now()).strftime('%Y%m%dT%H%M%S')

class Monthly(JobInterval):
    _name = "Monthly"

    @property
    def job_batch_id(self):
        return timezone.localtime(timezone.now()).strftime('%Y%m%dT%H%M%S')

