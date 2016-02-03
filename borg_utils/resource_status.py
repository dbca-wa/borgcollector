from django.core.exceptions import ValidationError

class ResourceStatus(object):
    NEW = 'New' #not published before
    UPDATED = 'Updated' #published before
    PUBLISHED = 'Published' #published
    UNPUBLISHED = 'Unpublished' #not published now; 

    PUBLISH = 'Publish' #an intermediate status
    UNPUBLISH = 'Unpublish' #an intermediate status
    CASCADE_UNPUBLISH = 'CascadeUnpublish' #an intermediate status, used to automatically unpulish the descendant resources 
    DEPENDENT_PUBLISH = 'DependentPublish' #an intermediate status, used to automatically publish the parent resources.
    CASCADE_PUBLISH = 'CascadePublish' #an intermediate status, used to automatically publish the descendant resources
    SIDE_PUBLISH = 'SidePublish' #an intermediate status, used to automatically publish the resource affected by the current resource

class ResourceStatusManagement(object):
    """
    Based on current status and expected status, return the target status;
    """
    @property
    def is_published(self):
        return self.status in [ResourceStatus.UPDATED,ResourceStatus.PUBLISHED]

    @property
    def is_unpublished(self):
        return self.status in [ResourceStatus.NEW,ResourceStatus.UNPUBLISHED]

    def get_next_status(self,current_status,expected_status):
        if expected_status == ResourceStatus.UPDATED:
            if current_status in [ResourceStatus.NEW,ResourceStatus.UPDATED,ResourceStatus.UNPUBLISHED]:
                return current_status
            elif current_status == ResourceStatus.PUBLISHED:
                return ResourceStatus.UPDATED
            else:
                raise ValidationError("Not supported.current status is {0}, expected status is {1}".format(current_status,expected_status))
        elif expected_status == ResourceStatus.PUBLISH:
            return ResourceStatus.PUBLISH;
        elif expected_status == ResourceStatus.DEPENDENT_PUBLISH:
            if current_status in [ResourceStatus.NEW,ResourceStatus.UNPUBLISHED]:
                return ResourceStatus.PUBLISH
            else:
                return current_status
        elif expected_status == ResourceStatus.CASCADE_PUBLISH:
            if current_status in [ResourceStatus.NEW]:
                return ResourceStatus.PUBLISH
            else:
                return current_status
        elif expected_status == ResourceStatus.SIDE_PUBLISH:
            if current_status in [ResourceStatus.PUBLISHED,ResourceStatus.UPDATED]:
                return ResourceStatus.PUBLISH
            else:
                return current_status
        elif expected_status == ResourceStatus.PUBLISHED:
            if current_status == ResourceStatus.PUBLISH:
                return ResourceStatus.PUBLISHED
            else:
                raise ValidationError("Not supported.current status is {0}, expected status is {1}".format(current_status,expected_status))
        elif expected_status == ResourceStatus.UNPUBLISH:
            if current_status in [ResourceStatus.NEW,ResourceStatus.UNPUBLISHED]:
                return current_status
            elif current_status in [ResourceStatus.PUBLISHED,ResourceStatus.UPDATED]:
                return ResourceStatus.UNPUBLISH
            else:
                raise ValidationError("Not supported.current status is {0}, expected status is {1}".format(current_status,expected_status))
        elif expected_status == ResourceStatus.CASCADE_UNPUBLISH:
            if current_status in [ResourceStatus.NEW,ResourceStatus.UNPUBLISHED]:
                return current_status
            elif current_status in [ResourceStatus.PUBLISHED,ResourceStatus.UPDATED]:
                return ResourceStatus.UNPUBLISH
            else:
                raise ValidationError("Not supported.current status is {0}, expected status is {1}".format(current_status,expected_status))
        elif expected_status == ResourceStatus.UNPUBLISHED:
            if current_status == ResourceStatus.UNPUBLISH:
                return ResourceStatus.UNPUBLISHED
            else:
                raise ValidationError("Not supported.current status is {0}, expected status is {1}".format(current_status,expected_status))
        else:
            raise ValidationError("Not supported.current status is {0}, expected status is {1}".format(current_status,expected_status))

