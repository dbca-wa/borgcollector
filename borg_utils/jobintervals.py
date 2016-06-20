from django.utils import timezone
from datetime import datetime,timedelta

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

    _publish_intervals = None
    _publish_options = None

    @staticmethod
    def _initialize():
        if not JobInterval._all_intervals:
            JobInterval._all_intervals = [c() for c in JobInterval.all_classes ]
            JobInterval._interval_dict = dict([(o.name.lower(),o) for o in JobInterval._all_intervals])

            JobInterval._publish_intervals = [o for o in JobInterval._all_intervals if o not in [Minutely.instance()]]
            JobInterval._publish_options = tuple([(o.name,o.name) for o in JobInterval._publish_intervals if o not in [Realtime.instance(),Triggered.instance(),Minutely.instance()]])

            for o in JobInterval.all_intervals:
                setattr(JobInterval,type(o).__name__,o)

        

    @staticmethod
    def all_intervals():
        """
        return all possible job intervals.
        """
        #JobInterval._initialize()

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

        #JobInterval._initialize()

        try:
            return JobInterval._interval_dict[interval.lower()]
        except:
            raise ValueError("The job interval {0} is not recognized.".format(interval))

    @property
    def name(self):
        return self._name

    @staticmethod
    def publish_intervals():
        #JobInterval._initialize()
        return JobInterval._publish_intervals

    @staticmethod
    def publish_options():
        #JobInterval._initialize()
        return JobInterval._publish_options

    def get_scheduled_time(self,t=None):
        """
        Return the scheduled time at time 't'
        """
        raise NotImplementedError("Not Implemented!")

    def next_scheduled_time(self,t=None):
        """
        Return the next scheduled time after time 't'
        """
        raise NotImplementedError("Not Implemented!")

    def job_batch_id(self,time=None):
        time = time or timezone.now()
        return timezone.localtime(time).strftime('%Y%m%dT%H%M%S')


    def __str__(self):
        return self._name

class Manually(JobInterval):
    _name = "Manually"

    def get_scheduled_time(self,t=None):
        """
        Return the scheduled time at time 't'
        """
        return None

    def next_scheduled_time(self,t=None):
        """
        Return the next scheduled time after time 't'
        """
        return None

class Triggered(JobInterval):
    _name = "Triggered"

    def get_scheduled_time(self,t=None):
        """
        Return the scheduled time at time 't'
        """
        return None

    def next_scheduled_time(self,t=None):
        """
        Return the next scheduled time after time 't'
        """
        return None

class Realtime(JobInterval):
    _name = "Realtime"

    def get_scheduled_time(self,t=None):
        """
        Return the scheduled time at time 't'
        """
        return None

    def next_scheduled_time(self,t=None):
        """
        Return the next scheduled time after time 't'
        """
        return None

class Minutely(JobInterval):
    _name = "Minutely"

    def get_scheduled_time(self,t=None):
        """
        Return the scheduled time at time 't'
        """
        if t:
            t = timezone.localtime(t)
        else:
            t = timezone.localtime(timezone.now())

        return datetime(t.year,t.month,t.day,t.hour,t.minute,tzinfo=t.tzinfo)

    def next_scheduled_time(self,t=None):
        """
        Return the next scheduled time after time 't'
        """
        return self.get_scheduled_time(t) + timedelta(minutes=1)

class Hourly(JobInterval):
    _name = "Hourly"

    def get_scheduled_time(self,t=None):
        """
        Return the scheduled time at time 't'
        """
        if t:
            t = timezone.localtime(t)
        else:
            t = timezone.localtime(timezone.now())

        return datetime(t.year,t.month,t.day,t.hour,tzinfo=t.tzinfo)

    def next_scheduled_time(self,t=None):
        """
        Return the next scheduled time after time 't'
        """
        return self.get_scheduled_time(t) + timedelta(hours=1)


class Daily(JobInterval):
    """
    job will be created every day.
    """
    _name = "Daily"

    def get_scheduled_time(self,t=None):
        """
        Return the scheduled time at time 't'
        """
        if t:
            t = timezone.localtime(t)
        else:
            t = timezone.localtime(timezone.now())

        return datetime(t.year,t.month,t.day,tzinfo=t.tzinfo)

    def next_scheduled_time(self,t=None):
        """
        Return the next scheduled time after time 't'
        """
        return self.get_scheduled_time(t) + timedelta(days=1)
        

class Weekly(JobInterval):
    """
    job will be created every Saturday.
    """
    _name = "Weekly"

    def get_scheduled_time(self,t=None):
        """
        Return the scheduled time at time 't'
        """
        if t:
            t = timezone.localtime(t)
        else:
            t = timezone.localtime(timezone.now())

        day_diff = t.weekday() - 5
        day_diff = day_diff if day_diff >= 0 else day_diff + 7
        if day_diff:
            return datetime(t.year,t.month,t.day,tzinfo=t.tzinfo) - timedelta(day_diff)
        else:
            return datetime(t.year,t.month,t.day,tzinfo=t.tzinfo)

    def next_scheduled_time(self,t=None):
        """
        Return the next scheduled time after time 't'
        """
        return self.get_scheduled_time(t) + timedelta(weeks=1)


class Monthly(JobInterval):
    """
    job will be created at every Month.
    """
    _name = "Monthly"

    def get_scheduled_time(self,t=None):
        """
        Return the scheduled time at time 't'
        """
        if t:
            t = timezone.localtime(t)
        else:
            t = timezone.localtime(timezone.now())

        return datetime(t.year,t.month,1,tzinfo=t.tzinfo)

    def next_scheduled_time(self,t=None):
        """
        Return the next scheduled time after time 't'
        """
        t = self.get_scheduled_time(t)
        if t.month < 12:
            return datetime(t.year,t.month + 1,t.day,tzinfo=t.tzinfo)
        else:
            return datetime(t.year + 1,1,t.day,tzinfo=t.tzinfo)

#initialize job interval
JobInterval. _initialize()
