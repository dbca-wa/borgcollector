import logging
import sys,traceback,os

from borg_utils.singleton import SingletonMetaclass,Singleton

logger = logging.getLogger(__name__)

class JobStateOutcome(object):
    """
    Declare all possible job state outcome
    """
    succeed = "Succeed"
    failed = "Failed"
    shutdown = "Shutdown"
    warning = "Warning"
    internal_error = "Internal Error"
    approved_by_custodian = "Approved by Custodian"
    cancelled_by_custodian = "Cancelled by Custodian"

    _manual_outcomes = {approved_by_custodian.lower(), cancelled_by_custodian.lower()}
    _succeed_outcomes = {succeed}

    @classmethod
    def is_manual_outcome(cls,outcome):
        return outcome.lower() in cls._manual_outcomes
    
    @classmethod
    def succeed_outcomes(cls):
        return cls._succeed_outcomes
    
    def __new__(cls):
        raise Exception("Cannot instantiate.")


class JobStateMetaclass(SingletonMetaclass):
    """
    A metaclass for job state class
    """
    _classes = []
    _failed_classes = []
    _failed_class_names = []
    def __init__(cls,name,base,dct):
        """
        cache all JobState sub classes.
        """
        super(JobStateMetaclass,cls).__init__(name,base,dct)
        #set cls's _abstract to False if _abstract is not declared in cls.
        if "_abstract" not in cls.__dict__:
            setattr(cls,"_abstract",False)

        if not cls.is_abstract():
            JobStateMetaclass._classes.append(cls)
            if not cls._end_state and not issubclass(cls,FailedState):
                #create a Failed state
                d = {"_name":cls._name + " Failed","_interactive_state":cls._interactive_if_failed,"_normal_state":cls}
                failed_cls = type(name + "Failed",(FailedState,),d)
                JobStateMetaclass._failed_classes.append(failed_cls)
                JobStateMetaclass._failed_class_names.append(failed_cls._name)
                setattr(cls,"_failed_state",failed_cls)
                #create a internal error state
                d = {"_name":cls._name + " Internal Error","_normal_state":cls}
                error_cls = type(name + "InternalError",(FailedState,),d)
                JobStateMetaclass._failed_classes.append(error_cls)
                JobStateMetaclass._failed_class_names.append(error_cls._name)
                setattr(cls,"_internal_error_state",error_cls)

    @property
    def all_classes(self):
        return JobStateMetaclass._classes

    @property
    def all_failed_classes(self):
        return JobStateMetaclass._failed_classes

    @property
    def all_failed_class_names(self):
        return JobStateMetaclass._failed_class_names

class JobState(Singleton):
    """
    super class for job status.
    """
    __metaclass__ = JobStateMetaclass
    _transition_dict = None

    _all_jobstates = None
    _jobstate_dict = None
    _abstract = True
    _stateoutcome_cls = JobStateOutcome

    _interactive_if_failed = False
    _interactive_state = False
    _end_state = False
    _start_state = False
    _volatile_state = False
    _downstates = None
    _cancellable = True

    def __initialize__(self):
        if self.is_error_state:
            #is a error state, already initialized by the associated normal state
            return
        if self.is_end_state:
            # is a end state, does not need to initialize
            return
        
        #construct the transition dict for normal state, failed state and error state
        #merge the transition dict and default transition dict
        normal_dict = dict(self.default_transition_dict())
        d = self.transition_dict()
        if d:
            for k in d:
                normal_dict[k] = d[k]

        #set the default warning transition
        if JobStateOutcome.warning not in normal_dict and JobStateOutcome.succeed in normal_dict:
            normal_dict[JobStateOutcome.warning] = normal_dict[JobStateOutcome.succeed]

        failed_dict = dict(self._failed_state.default_transition_dict())
        failed_dict[JobStateOutcome.failed] = self._failed_state
        failed_dict[JobStateOutcome.shutdown] = self._failed_state
        failed_dict[JobStateOutcome.internal_error] = self._failed_state
        if self._failed_state._interactive_state:
            #import ipdb;ipdb.set_trace()
            #this is a interactive state, replace the succeed outcome with approved_by_custodian
            failed_dict[JobStateOutcome.approved_by_custodian] = normal_dict[JobStateOutcome.failed]    
            if JobStateOutcome.succeed in failed_dict:
                del failed_dict[JobStateOutcome.succeed]
        else:
            failed_dict[JobStateOutcome.succeed] = normal_dict[JobStateOutcome.failed]
        if JobStateOutcome.cancelled_by_custodian in normal_dict:
            failed_dict[JobStateOutcome.cancelled_by_custodian] = normal_dict[JobStateOutcome.cancelled_by_custodian]
        normal_dict[JobStateOutcome.failed] = self._failed_state
        normal_dict[JobStateOutcome.shutdown] = self._failed_state

        error_dict = dict(self._internal_error_state.default_transition_dict())
        error_dict[JobStateOutcome.failed] = self._internal_error_state
        error_dict[JobStateOutcome.shutdown] = self._internal_error_state
        error_dict[JobStateOutcome.internal_error] = self._internal_error_state
        error_dict[JobStateOutcome.succeed] = normal_dict[JobStateOutcome.internal_error]
        if JobStateOutcome.cancelled_by_custodian in normal_dict:
            error_dict[JobStateOutcome.cancelled_by_custodian] = normal_dict[JobStateOutcome.cancelled_by_custodian]
        normal_dict[JobStateOutcome.internal_error] = self._internal_error_state
        #convert the state class to instance
        for k in normal_dict:
            if not isinstance(normal_dict[k],JobState):
                normal_dict[k] = normal_dict[k]()

        for k in failed_dict:
            if not isinstance(failed_dict[k],JobState):
                failed_dict[k] = failed_dict[k]()
        
        for k in error_dict:
            if not isinstance(error_dict[k],JobState):
                error_dict[k] = error_dict[k]()

        self._transition_dict = dict([(k.lower(),normal_dict[k]) for k in normal_dict])
        self._failed_state._transition_dict = dict([(k.lower(),failed_dict[k]) for k in failed_dict])
        self._internal_error_state._transition_dict = dict([(k.lower(),error_dict[k]) for k in error_dict])

        #import ipdb;ipdb.set_trace()

    @classmethod
    def default_transition_dict(cls): 
        return {}
    
    @classmethod
    def transition_dict(cls):
        return {}

    @classmethod
    def _get_transition_dict(cls):
        if cls._transition_dict == None:
            cls._transition_dict = cls.transition_dict()
            if cls._transition_dict == None: cls._transition_dict = {}
            for x in cls._transition_dict:
                cls._transition_dict[x] = (cls._transition_dict[x]).instance()

        return cls._transition_dict

    def next_state(self,outcome):
        """
        Return the next state to which the job will move with the specified outcome.
        """
        try:
            return self._transition_dict[outcome.lower()]
        except:
            raise ValueError("Outcome ({0}) is not recognized by state {1}".format(outcome,self.name))

    
    def execute(self,job,previous_state):
        """
        execute the current state.
        return the job state outcome.
        """
        raise NotImplementedError("The method 'execute' is not implemented.")

    @classmethod
    def is_abstract(cls):
        #import ipdb;ipdb.set_trace()
        return cls._abstract

    @staticmethod
    def _initialize():
        if not JobState._all_jobstates:
            JobState._all_jobstates = [s() for s in JobState.all_classes]
            JobState._jobstate_dict = dict([(s.name,s) for s in JobState._all_jobstates])
    
    @staticmethod
    def all_jobstates():
        """
        return all possible job states.
        """
        JobState._initialize()

        return JobState._all_jobstates

    @staticmethod
    def get_jobstate(state):
        """
        if state is correct, return the job state instance.
        otherwise throw exception
        """
        if isinstance(state, JobState):
            #state is a job state instance, return directly
            return state

        JobState._initialize()
        try:
            return JobState._jobstate_dict[state]
        except:
            raise ValueError("The job state {0} is not recognized.".format(state))

    def downstates(self):
        """
        return all down states, not support cycle relationship
        """
        if self._downstates == None:
            self._downstates = set([self.next_state(s) for s in self._stateoutcome_cls.succeed_outcomes()])
            grand_children = set()
            for s in self._downstates:
                if not s.is_end_state and s != self :
                    grand_children = grand_children.union(s.downstates())
            self._downstates = self._downstates.union(grand_children)
        #import ipdb;ipdb.set_trace()
        return self._downstates

    def is_upstate(self,job_state):
        """
        return true, if job_state is a down state of the current state
        """
        return job_state in self.downstates()

    @property
    def is_interactive_state(self):
        """
        Return true if the custodian need to interfere
        """
        return self._interactive_state

    @property
    def is_start_state(self):
        """
        Return true if the state is a start state. for example: Waiting
        """
        return self._start_state

    @property
    def cancellable(self):
        """
        Return true if the state is cancellable
        """
        return self._cancellable

    @property
    def is_end_state(self):
        """
        Return true if the state is a end state. for example: Failed and Completed
        """
        return self._end_state

    @property
    def is_error_state(self):
        """
        Return true if the state is a error state
        """
        return isinstance(self,FailedState)

    @property
    def is_volatile_state(self):
        """
        Return true if the state is a intermediate state, it exists just for pre and post processing.
        """
        return self._volatile_state

    @property
    def name(self):
        """
        Job state name
        """
        return self._name

    @property
    def outcome_cls(self):
        """
        Job state outcome class
        """
        return self._stateoutcome_cls

    @staticmethod
    def get_exception_message():
        """
        return a formated error message
        """
        return traceback.format_exc()

    def __str__(self):
        return self._name

class FailedState(JobState):
    """
    The is a super class for failed state
    """
    _abstract = True
    #the associate job state
    _normal_state = None

    def execute(self,job,previous_state):
        """
        execute the current state.
        return the job state outcome.
        """
        return (JobStateOutcome.succeed,None)

class Failed(JobState):
    """
    This is a end state, represent the job is failed
    """
    _name = "Failed"
    _end_state = True
    _cancellable = False

class Completed(JobState):
    """
    This is a end state, represent the job is succeed
    """
    _name = "Completed"
    _end_state = True
    _cancellable = False

class CompletedWithWarning(JobState):
    """
    This is a end state, represent the job is succeed but has warning message.
    """
    _name = "CompletedWithWarning"
    _end_state = True
    _cancellable = False

