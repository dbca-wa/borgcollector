import threading

class SignalEnable(object):
    """
    provide enable signal function
    """
    _save_signal_enabled = None

    def try_set_signal_sender(self,action):
        """
        Set the original signal sender, used in cascade operation to include all operation in one transaction
        If sender is already set, then return directly, otherwise, send the current instance as the sender
        return True, if set successfully; otherwise, return False
        """
        sender = getattr(threading.current_thread,"signal_sender",None)
        if sender is None:
            setattr(threading.current_thread,"signal_sender",(self,action))
            return True
        elif sender == (self,action):
            return True
        else:
            return False

    def is_signal_sender(self,action):   
        """
        Return true, if current instance is the signal sender.
        """
        return getattr(threading.current_thread,"signal_sender",None) == (self,action)

    def try_clear_signal_sender(self,action):
        """
        Remove the signal sender,if current instance is the signal sender
        """
        
        if getattr(threading.current_thread,"signal_sender",None) == (self,action):
            delattr(threading.current_thread,"signal_sender")

    def enable_save_signal(self):
        """
        enabled signal will be disabled after the first time execution.
        """
        #import ipdb;ipdb.set_trace()
        self._save_signal_enabled = True

    def save_signal_guard(self):
        """
        if enabled, switch save singal to off and return True;
        if disabled, return False.
        This function should be invoked by the first save signal.
        """
        if self._save_signal_enabled:
            self._save_signal_enabled = False
            return True
        else:
            self._save_signal_enabled = None
            return False

    def save_signal_enabled(self):
        """
        if save signal is enabled, return True; otherwise return False
        This function should be invoked by all save signals except first save signal.
        """
        return self._save_signal_enabled == False

