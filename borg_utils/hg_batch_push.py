import hglib
import threading
import logging

logger = logging.getLogger(__name__)

from borg_utils.borg_config import BorgConfiguration

def try_set_push_owner(owner,enforce=False):
    if enforce or getattr(threading.current_thread,"push_owner",None) in [None,owner]:
        #no push owner before, set owner to the current push owner
        setattr(threading.current_thread,"push_owner",owner)
        return True
    else:
        return False

def try_clear_push_owner(pusher,enforce=False):
    if enforce or getattr(threading.current_thread,"push_owner",None) == pusher:
        #pusher is the current push owner, clear it
        try:
            delattr(threading.current_thread,"push_owner")
        except:
            pass
        try:
            delattr(threading.current_thread,"committed_changes")
        except:
            pass

def increase_committed_changes():
    setattr(threading.current_thread,"committed_changes",getattr(threading.current_thread,"committed_changes",0) + 1)
    

def try_push_to_repository(pusher,hg=None,enforce=False):
    if not enforce and pusher != getattr(threading.current_thread,"push_owner",None):
        #pusher is not the current push owner, return
        return
    changesets = getattr(threading.current_thread,"committed_changes",0) 
    if changesets <= 0:
        #no committed changes, not need to push
        return

    if BorgConfiguration.DEBUG:
        logger.info("Push {0} changesets to the repository".format(changesets))
    else:
        logger.debug("Push {0} changesets to the repository".format(changesets))

    if hg is None:
        hg = hglib.open(BorgConfiguration.BORG_STATE_REPOSITORY)
        try:
            hg.push(ssh=BorgConfiguration.BORG_STATE_SSH)
        finally:
            hg.close()
    else:
        hg.push(ssh=BorgConfiguration.BORG_STATE_SSH)

