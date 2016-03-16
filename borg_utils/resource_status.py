import threading

from django.core.exceptions import ValidationError

from borg_utils.singleton import SingletonMetaclass,Singleton

class ResourceStatusMetaclass(SingletonMetaclass):
    """
    A metaclass for Resource Status class
    """
    _classes = []
    def __init__(cls,name,base,dct):
        """
        cache all resource status classes.
        """
        super(ResourceStatusMetaclass,cls).__init__(name,base,dct)
        if name != 'ResourceStatus':
            ResourceStatusMetaclass._classes.append(cls)

    @property
    def all_classes(self):
        return ResourceStatusMetaclass._classes

class ResourceAction(object):
    #None action
    NONE = 'None'
    #Enable the resource
    ENABLE = 'Enable'
    #Disable the resource
    DISABLE = 'Disable'

    #update the resource configuration
    UPDATE = 'Update'

    #publish a resource triggered by user
    PUBLISH = 'Publish' 
    #publish a resource triggered by parent resource
    CASCADE_PUBLISH = 'CascadePublish' 
    #publish a resource triggered by child resource
    DEPENDENT_PUBLISH = 'DependentPublish' 

    #unpublish a resource
    UNPUBLISH = 'Unpublish' 
    #cascade unpublish a resource triggered by parent resource
    CASCADE_UNPUBLISH = 'CascadeUnpublish' 

class ResourceStatus(Singleton):
    """
    super class for resource status
    """
    __metaclass__ = ResourceStatusMetaclass

    #all status
    all_status = None
    _status_dict = None
    _published = False
    _publish_enabled = True

    publish_status_options = None
    layer_status_options = None
    interested_layer_status_names = None
    published_status = None

    @staticmethod
    def _initialize():
        if not ResourceStatus.all_status:
            #collect all possible resource status objects
            ResourceStatus.all_status = [c() for c in ResourceStatus.all_classes]
            ResourceStatus.published_status = [c for c in ResourceStatus.all_status if c.published]
            #populate the dictionary for all possible status object
            ResourceStatus._status_dict = dict([(o.name.lower(),o) for o in ResourceStatus.all_status])
            #set a property in ResourceStatus for all possible status object
            for o in ResourceStatus.all_status:
                setattr(ResourceStatus,type(o).__name__,o)

            #the options for publish
            ResourceStatus.publish_status_options = ((ResourceStatus.Enabled.name,ResourceStatus.Enabled.name),(ResourceStatus.Disabled.name,ResourceStatus.Disabled.name))
            #the options for layers(layergroup, wms layer)
            ResourceStatus.interested_layer_status_names = [status.name for status in ResourceStatus.all_status if status not in (ResourceStatus.Enabled,ResourceStatus.Disabled,ResourceStatus.New)]
            ResourceStatus.layer_status_options = tuple([(status.name,status.name) for status in ResourceStatus.all_status if status not in (ResourceStatus.Enabled,ResourceStatus.Disabled)])
        

    @staticmethod
    def get_status(status):
        """
        if status is correct, return the resource status instance.
        otherwise throw exception
        """
        if isinstance(status, ResourceStatus):
            #status is a PublishStatus instance, return directly
            return status

        try:
            return ResourceStatus._status_dict[status.lower()]
        except:
            raise ValueError("The publish status {0} is not recognized.".format(status))

    @property
    def published(self):
        return self._published

    @property
    def unpublished(self):
        return not self._published

    @property
    def name(self):
        return self._name

    @property
    def publish_enabled(self):
        return self._publish_enabled

    def next_status(self,action):
        """
        Return a tuble(next_status,action?) based on action.
        if action is false, no publish/unpublish action is required
        if action is true, a pubish/unpublish action(decided by next_status) is required.
        """
        return (self,False)

    def __str__(self):
        return self._name

class Enabled(ResourceStatus):
    """
    The resource is enabled
    A enabled resource can be published or unpublished.
    """
    _name = "Enabled"
    _published = None

    def next_status(self,action):
        if action == ResourceAction.ENABLE:
            return (self.Enabled,False)
        elif action == ResourceAction.DISABLE:
            return (self.Disabled,True)
        else:
            raise ValidationError("Not supported.current status is {0}, action is {1}".format(self.name,action))
        
class Disabled(ResourceStatus):
    """
    The resource is disnabled
    """
    _name = "Disabled"
    _publish_enabled = False

    def next_status(self,action):
        if action == ResourceAction.ENABLE:
            return (self.Enabled,False)
        elif action == ResourceAction.DISABLE:
            return (self.Disabled,True)
        else:
            raise ValidationError("Not supported.current status is {0}, action is {1}".format(self.name,action))
        
class New(ResourceStatus):
    """
    Resource has not been published before.
    """
    _name = "New"
    def next_status(self,action):
        if action == ResourceAction.PUBLISH:
            return (self.Published,True)
        elif action == ResourceAction.DEPENDENT_PUBLISH:
            return (self.Published,True)
        else:
            return (self,False)
        
class Updated(ResourceStatus):
    """
    Resource configuration was changed after latest publish
    """
    _name = "Updated"
    _published = True

    def next_status(self,action):
        if action == ResourceAction.PUBLISH:
            return (self.Published,True)
        elif action == ResourceAction.CASCADE_PUBLISH:
            return (self.CascadedPublished,True)
        elif action == ResourceAction.UNPUBLISH:
            return (self.Unpublished,True)
        elif action == ResourceAction.CASCADE_UNPUBLISH:
            return (self.CascadeUnpublished,True)
        else:
            return (self,False)
        

class Published(ResourceStatus):
    """
    Resource published trigged by user
    """
    _name = "Published"
    _published = True

    def next_status(self,action):
        if action == ResourceAction.UPDATE:
            return (self.Updated,False)
        elif action == ResourceAction.PUBLISH:
            return (self.Published,True)
        elif action == ResourceAction.CASCADE_PUBLISH:
            return (self.CascadePublished,True)
        elif action == ResourceAction.UNPUBLISH:
            return (self.Unpublished,True)
        elif action == ResourceAction.CASCADE_UNPUBLISH:
            return (self.CascadeUnpublished,True)
        else:
            return (self,False)
        
class CascadePublished(ResourceStatus):
    """
    Resource published triggered by parent resource
    """
    _name = "CascadePublished"
    _published = True

    def next_status(self,action):
        if action == ResourceAction.UPDATE:
            return (self.Updated,False)
        elif action == ResourceAction.PUBLISH:
            return (self.Published,True)
        elif action == ResourceAction.CASCADE_PUBLISH:
            return (self.CascadePublished,True)
        elif action == ResourceAction.UNPUBLISH:
            return (self.Unpublished,True)
        elif action == ResourceAction.CASCADE_UNPUBLISH:
            return (self.CascadeUnpublished,True)
        else:
            return (self,False)
        
class Unpublished(ResourceStatus):
    """
    Resourse unpublished triggered by user
    """
    _name = "Unpublished"

    def next_status(self,action):
        if action == ResourceAction.PUBLISH:
            return (self.Published,True)
        elif action == ResourceAction.DEPENDENT_PUBLISH:
            return (self.Published,True)
        else:
            return (self,False)

class CascadeUnpublished(ResourceStatus):
    """
    Resourse unpublished triggered by parent resource
    """
    _name = "CascadeUnpublished"

    def next_status(self,action):
        if action == ResourceAction.PUBLISH:
            return (self.Published,True)
        elif action == ResourceAction.CASCADE_PUBLISH:
            return (self.CascadePublished,True)
        elif action == ResourceAction.DEPENDENT_PUBLISH:
            return (self.Published,True)
        elif action == ResourceAction.UNPUBLISH:
            return (self.Unpublished,False)
        else:
            return (self,False)

class ResourceStatusManagement(object):
    """
    Based on current status and expected status, return the target status;
    """
    @property
    def publish_status(self):
        return ResourceStatus.get_status(self.status)

    @property
    def is_published(self):
        return self.publish_status.published

    @property
    def is_unpublished(self):
        return self.publish_status.unpublished

    @property
    def publish_required(self):
        """
        Can only be accessed right after calling next_status method
        Return True: publish the resource
               False: no action is required
        """
        if not hasattr(threading.current_thread,"resource_id"):
            return False
        elif getattr(threading.current_thread,"resource_id",None) != id(self):
            raise ValidationError("Resource object does not match.")
        else:
            return getattr(threading.current_thread,"resource_action",None) == ResourceAction.PUBLISH

    @property
    def unpublish_required(self):
        """
        Can only be accessed right after calling next_status method
        Return True: unpublish the resource
               False: no action is required
        """
        if not hasattr(threading.current_thread,"resource_id"):
            return False
        elif getattr(threading.current_thread,"resource_id",None) != id(self):
            raise ValidationError("Resource object does not match.")
        else:
            return getattr(threading.current_thread,"resource_action",None) == ResourceAction.UNPUBLISH

    def next_status(self,action):
        """
        Return next_status based on action
        """
        s = self.publish_status.next_status(action)
        setattr(threading.current_thread,"resource_id",id(self))
        setattr(threading.current_thread,"resource_action",(ResourceAction.PUBLISH if s[1] and s[0].published else (ResourceAction.UNPUBLISH if s[1] and s[0].unpublished else ResourceAction.NONE)))

        return s[0].name

ResourceStatus._initialize()
