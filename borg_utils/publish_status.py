from django.utils import timezone

from borg_utils.singleton import SingletonMetaclass,Singleton

class PublishStatusMetaclass(SingletonMetaclass):
    """
    A metaclass for Publish Status class
    """
    _classes = []
    def __init__(cls,name,base,dct):
        """
        cache all publish status classes.
        """
        super(PublishStatusMetaclass,cls).__init__(name,base,dct)
        if name != 'PublishStatus':
            PublishStatusMetaclass._classes.append(cls)

    @property
    def all_classes(self):
        return PublishStatusMetaclass._classes

class PublishStatus(Singleton):
    """
    super class for publish status
    """
    __metaclass__ = PublishStatusMetaclass

    _all_status = None
    _status_dict = None
    _all_options = None
    _publish_enabled = False

    @staticmethod
    def _initialize():
        if not PublishStatus._all_status:
            PublishStatus._all_status = [c() for c in PublishStatus.all_classes]
            PublishStatus._status_dict = dict([(o.name.lower(),o) for o in PublishStatus._all_status])
            PublishStatus._all_options = tuple([(o.name,o.name) for o in PublishStatus._all_status])
        

    @staticmethod
    def all_status():
        """
        return all possible publish status
        """
        return PublishStatus._all_status

    @staticmethod
    def get_status(status):
        """
        if status is correct, return the publish status instance.
        otherwise throw exception
        """
        if isinstance(status, PublishStatus):
            #status is a PublishStatus instance, return directly
            return status

        try:
            return PublishStatus._status_dict[status.lower()]
        except:
            raise ValueError("The publish status {0} is not recognized.".format(status))

    @property
    def publish_enabled(self):
        return self._publish_enabled

    @property
    def name(self):
        return self._name

    @staticmethod
    def all_options():
        PublishStatus._initialize()
        return PublishStatus._all_options

    def __str__(self):
        return self._name

class EnabledStatus(PublishStatus):
    _name = "Enabled"
    _publish_enabled = True

class DisabledStatus(PublishStatus):
    _name = "Disabled"
    _publish_enabled = False



PublishStatus._initialize()
