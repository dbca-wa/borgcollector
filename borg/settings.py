"""
Django settings for incredibus project.

For more information on this file, see
https://docs.djangoproject.com/en/1.7/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/1.7/ref/settings/
"""

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
import os
import dj_database_url
import logging

from django.db import connection

BASE_DIR = os.path.dirname(os.path.dirname(__file__))

# define the following in the environment
SECRET_KEY = os.environ.get('SECRET_KEY', '')
FDW_URL = os.environ.get('FDW_URL', '')
DEBUG = os.environ.get('DEBUG', False)
TEMPLATE_DEBUG = DEBUG
FDW_URL_SETTINGS = None
if FDW_URL:
    FDW_URL_SETTINGS = dj_database_url.parse(FDW_URL)
    if 'PORT' not in FDW_URL_SETTINGS: FDW_URL_SETTINGS['PORT'] = 5432
    if 'USER' not in FDW_URL_SETTINGS: FDW_URL_SETTINGS['USER'] = ""
    if 'PASSWORD' not in FDW_URL_SETTINGS: FDW_URL_SETTINGS['PASSWORD'] = ""
else:
    FDW_URL_SETTINGS = {}


CSW_URL = os.environ.get('CSW_URL','')
CSW_USER = os.environ.get('CSW_USER','')
CSW_PASSWORD = os.environ.get('CSW_PASSWORD','')
DEFAULT_CRS=os.environ.get("DEFAULT_CRS","EPSG:4326")

from django.conf.global_settings import TEMPLATE_CONTEXT_PROCESSORS as TCP

TEMPLATE_CONTEXT_PROCESSORS = TCP + (
    'django.core.context_processors.request',
    'django.core.context_processors.media',
)

# Django suit

SUIT_CONFIG = {
    'ADMIN_NAME': 'The Borg Collector'
}

# Application definition

INSTALLED_APPS = (
    'borg', # Up top for template overrides
    'suit', # Nice theme
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django_extensions',
    'django_uwsgi',
    #'django_wsgiserver',
    'reversion', # Versioning
    # Sub-app definitions
    'tablemanager',
    'harvest',
    'filemanager',
    #'rolemanager',
    #'application',
    'wmsmanager',
    'layergroup',
    'monitor',
    'borg_utils',
    'dpaw_utils'
)

#from ldap_email_auth import ldap_default_settings
#ldap_default_settings()
AUTHENTICATION_BACKENDS = (
    'django.contrib.auth.backends.ModelBackend',
    #'ldap_email_auth.auth.EmailBackend'
)

MIDDLEWARE_CLASSES = (
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'dpaw_utils.middleware.SSOLoginMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
)

ROOT_URLCONF = 'borg.urls'
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.dummy.DummyCache",
    }
}
if os.environ.get("REDIS_URL",None):
    CACHES["shared"] = {
        "BACKEND":"django_redis.cache.RedisCache",
        "LOCATION": os.environ.get("REDIS_URL"),
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        }
    }


WSGI_APPLICATION = 'borg.wsgi.application'

# Internationalization
# https://docs.djangoproject.com/en/1.7/topics/i18n/
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Australia/Perth'
USE_I18N = True
USE_L10N = True
USE_TZ = True

LOGIN_URL = '/login/'
# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/1.7/howto/static-files/

STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STATICFILES_DIRS = (
    os.path.join(BASE_DIR, "static"),
)

try:
    log_level = int(os.environ.get("LOGGING_LEVEL",logging.INFO))
except:
    log_level = logging.INFO

logging.basicConfig(
    level = log_level,
    format = '%(asctime)s %(levelname)s %(message)s',
)

DOWNLOAD_ROOT = os.path.join(BASE_DIR,'download')
DOWNLOAD_URL = '/download/'

PREVIEW_ROOT = os.path.join(BASE_DIR,'preview')
PREVIEW_URL = '/preview/'

HARVEST_CONFIG = {
    "BORG_SCHEMA" : "public",
    "ROWID_COLUMN" : "_rowid",
    "TEST_SCHEMA" : "test",
    "INPUT_SCHEMA" : "input",
    "NORMAL_SCHEMA" : "normal_form",
    "TRANSFORM_SCHEMA" : "transform",
    "PUBLISH_SCHEMA" : "publish",
    "PUBLISH_VIEW_SCHEMA" : "publish_view",
    "FULL_DATA_DUMP_DIR" : os.path.abspath(os.path.join(DOWNLOAD_ROOT, "full_data")),
    "STYLE_FILE_DUMP_DIR" : os.path.abspath(os.path.join(DOWNLOAD_ROOT, "style_file")),
    "WMS_LAYER_DIR" : os.path.abspath(os.path.join(DOWNLOAD_ROOT, "wms_layer")),
    "WMS_STORE_DIR" : os.path.abspath(os.path.join(DOWNLOAD_ROOT, "wms_store")),
    "WORKSPACE_AS_SCHEMA" : True,
    "MAX_TEST_IMPORT_TIME" : 5, #seconds
    "RETRY_INTERVAL" : 300, #seconds
    "IMPORT_CANCEL_TIME" : 60, #seconds
    "BORG_STATE_REPOSITORY" : os.environ.get("BORG_STATE_REPOSITORY", os.path.join(BASE_DIR, "borgcollector-state")),
    "BORG_STATE_USER": os.environ.get("BORG_STATE_USER", "borgcollector"),
    "BORG_STATE_SSH": "ssh -i " + os.environ.get("BORG_STATE_SSH", "~/.ssh/id_rsa"),
    "USERLIST": os.environ.get("USERLIST", ""),
    "USERLIST_USERNAME": os.environ.get("USERLIST_USERNAME", ""),
    "USERLIST_PASSWORD": os.environ.get("USERLIST_PASSWORD", ""),
    "MASTER_PATH_PREFIX": os.environ.get("MASTER_PATH_PREFIX", "")
}

# Database
# https://docs.djangoproject.com/en/1.7/ref/settings/#databases
DATABASES = {'default': dict(dj_database_url.config(),
                            **{
                                'OPTIONS':{
                                    'options' : '-c search_path=' + HARVEST_CONFIG['BORG_SCHEMA']
                                }
                            }
                            )}
cursor = connection.cursor()
cursor.execute("CREATE SCHEMA IF NOT EXISTS {0}".format(HARVEST_CONFIG['BORG_SCHEMA']))
cursor.close()
cursor = None

