import os
from django.conf import settings

class BorgConfiguration():
    @staticmethod
    def initialize():
        setattr(BorgConfiguration,"DEBUG",getattr(settings,"DEBUG",False))
        config = getattr(settings,"HARVEST_CONFIG")
        if not config:
            config = {}

        for name, value in config.iteritems():
            setattr(BorgConfiguration, name, value)

        setattr(BorgConfiguration,"TEST_INPUT_SCHEMA",BorgConfiguration.test_schema(BorgConfiguration.INPUT_SCHEMA))
        setattr(BorgConfiguration,"TEST_NORMAL_SCHEMA",BorgConfiguration.test_schema(BorgConfiguration.NORMAL_SCHEMA))
        setattr(BorgConfiguration,"TEST_TRANSFORM_SCHEMA",BorgConfiguration.test_schema(BorgConfiguration.TRANSFORM_SCHEMA))

    @staticmethod
    def test_schema(schema):
        return "test_" + schema

BorgConfiguration.initialize()
#import ipdb;ipdb.set_trace()

