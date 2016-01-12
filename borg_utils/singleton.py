
class SingletonMetaclass(type):
    """
    A customized metaclass to implement singleton class
    """
    _instances = {}
    def __call__(cls,*args,**kwargs):
        if cls not in cls._instances:
            o = super(SingletonMetaclass,cls).__call__(*args,**kwargs)
            cls._instances[cls] = o
            o.__initialize__(*args,**kwargs)
        return cls._instances[cls]


class Singleton(object):
    """
    A super class to implement singleton class logic
    """
    __metaclass__ = SingletonMetaclass

    def __initialize__(self):
        pass

    @classmethod
    def instance(cls,*args,**kwargs):
        """
        return the singleton instance
        """
        return cls(*args,**kwargs)

