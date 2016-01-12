import django.dispatch

refresh_select_choices = django.dispatch.Signal(providing_args=["choice_family"])

def inherit_support_receiver(signal, **kwargs):
    """
    A decorator for connecting receivers to signals. Used by passing in the
    signal (or list of signals) and keyword arguments to connect::

        @receiver(post_save, sender=MyModel)
        def signal_receiver(sender, **kwargs):
            ...

        @receiver([post_save, post_delete], sender=MyModel)
        def signals_receiver(sender, **kwargs):
            ...

    """
    def _decorator(func):
        if isinstance(signal, (list, tuple)):
            for s in signal:
                s.connect(func, **kwargs)
                if "sender" in kwargs:
                    for c in kwargs['sender'].__subclasses__():
                        kwargs['sender'] = c
                        s.connect(func,**kwargs)
        else:
            signal.connect(func, **kwargs)
            if "sender" in kwargs:
                for c in kwargs['sender'].__subclasses__():
                    kwargs['sender'] = c
                    signal.connect(func,**kwargs)
        return func
    return _decorator
