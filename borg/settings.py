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
DEBUG = str(os.environ.get('DEBUG') or 'false').lower() in ("true","on","yes","y","t")
FDW_URL_SETTINGS = None
if FDW_URL:
    FDW_URL_SETTINGS = dj_database_url.parse(FDW_URL)
    if 'PORT' not in FDW_URL_SETTINGS: FDW_URL_SETTINGS['PORT'] = 5432
    if 'USER' not in FDW_URL_SETTINGS: FDW_URL_SETTINGS['USER'] = ""
    if 'PASSWORD' not in FDW_URL_SETTINGS: FDW_URL_SETTINGS['PASSWORD'] = ""
else:
    FDW_URL_SETTINGS = {}

ALLOWED_HOSTS=[h.strip() for h in (os.environ.get('ALLOWED_HOSTS') or '*').split(',') if h.strip()]

CSW_URL = os.environ.get('CSW_URL','')
CSW_USER = os.environ.get('CSW_USER','')
CSW_PASSWORD = os.environ.get('CSW_PASSWORD','')
CSW_CERT_VERIFY = str(os.environ.get('CSW_CERT_VERIFY') or 'true').lower() in ("true","on","yes","y","t")
DEFAULT_CRS=os.environ.get("DEFAULT_CRS","EPSG:4326")

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
    'django.contrib.postgres',
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
    'livelayermanager',
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

UWSGI_CACHE_FALLBACK = (os.environ.get('UWSGI_CACHE_FALLBACK') or 'false').lower() in ('true','yes','on')

ROOT_URLCONF = 'borg.urls'
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.dummy.DummyCache",
    },
    "shared":  {
        "BACKEND":"uwsgicache.UWSGICache",
        "LOCATION":"default"
    }
}


WSGI_APPLICATION = 'borg.wsgi.application'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [
            # insert your TEMPLATE_DIRS here
        ],
        'APP_DIRS': True,
        'OPTIONS': {
            "debug" : DEBUG,
            'context_processors': [
                # Insert your TEMPLATE_CONTEXT_PROCESSORS here or use this
                # list if you haven't customized them:
                'django.contrib.auth.context_processors.auth',
                'django.template.context_processors.debug',
                'django.template.context_processors.i18n',
                'django.template.context_processors.media',
                'django.template.context_processors.request',
                'django.template.context_processors.static',
                'django.template.context_processors.tz',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

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
    "BORG_SCHEMA" : os.environ.get("BORG_SCHEMA") or "public",
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
    "LIVE_LAYER_DIR" : os.path.abspath(os.path.join(DOWNLOAD_ROOT, "live_layer")),
    "WMS_STORE_DIR" : os.path.abspath(os.path.join(DOWNLOAD_ROOT, "wms_store")),
    "LIVE_STORE_DIR" : os.path.abspath(os.path.join(DOWNLOAD_ROOT, "live_store")),
    "PREVIEW_DIR" : os.path.abspath(PREVIEW_ROOT),
    "WORKSPACE_AS_SCHEMA" : True,
    "MAX_TEST_IMPORT_TIME" : int(os.environ.get("MAX_TEST_DATA_IMPORT_TIME") or 300), #seconds
    "RETRY_INTERVAL" : 300, #seconds
    "IMPORT_CANCEL_TIME" : 60, #seconds
    "BORG_STATE_REPOSITORY" : os.environ.get("BORG_STATE_REPOSITORY", os.path.join(BASE_DIR, "borgcollector-state")),
    "BORG_STATE_USER": os.environ.get("BORG_STATE_USER", "borgcollector"),
    "BORG_STATE_SSH": "ssh -i " + os.environ.get("BORG_STATE_SSH", "~/.ssh/id_rsa"),
    "USERLIST": os.environ.get("USERLIST", ""),
    "USERLIST_USERNAME": os.environ.get("USERLIST_USERNAME", ""),
    "USERLIST_PASSWORD": os.environ.get("USERLIST_PASSWORD", ""),
    "MASTER_PATH_PREFIX": os.environ.get("MASTER_PATH_PREFIX", ""),
    "MUDMAP_HOME": os.environ.get("MUDMAP_HOME", os.path.abspath(os.path.join(BASE_DIR,"mudmap"))),
    "DATA_DUMP":os.environ.get("DATA_DUMP") or "pg_dump",
    "PG_DUMP":os.environ.get("PG_DUMP") or "pg_dump"
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

