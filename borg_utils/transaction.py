import threading

class TransactionMixin(object):
    def try_begin_transaction(self,transactionid):
        """
        Set the transactionid, used in cascade operation to include all operation in one transaction
        If transactionid is already set, then return directly, otherwise, send the transactionid as the current transactionid
        return True, if set successfully; otherwise, return False
        """
        sender = getattr(threading.current_thread,"transactionid",None)
        if sender is None:
            setattr(threading.current_thread,"transactionid",(self,transactionid))
            return True
        elif sender == (self,transactionid):
            return True
        else:
            return False

    def is_current_transaction(self,transactionid):   
        """
        Return true, if the transactionid is the current transactionid
        """
        return getattr(threading.current_thread,"transactionid",None) == (self,transactionid)

    def try_clear_transaction(self,transactionid):
        """
        clear current transactionid,if transactionid is the current transactionid
        """
        
        if getattr(threading.current_thread,"transactionid",None) == (self,transactionid):
            delattr(threading.current_thread,"transactionid")


