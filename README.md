# Data collection application

## Environment variables

Borg Collector needs the following environment variables defined (e.g. .env for honcho):

 - DEBUG - enable Django debugging messages
 - PORT - server port
 - SECRET_KEY - Django secret key
 - DATABASE_URL - Django model + table manager database URL (database MUST be PostgreSQL) e.g. "postgresql://borg:password@aws-borgcollector-001/borgcollector"
 - FDW_URL - Foreign Data Wrapper database URL (database MUST be PostgreSQL, and the user should be a superuser so it can create PostgreSQL server objects)
 - BORG_STATE_SSH - SSH command used for repository operations (e.g. "ssh -i /etc/id_rsa_borg")
 - BORG_STATE_REPOSITORY - Full path to the local copy of the state repository (see install guide)
 - MASTER_PATH_PREFIX - Prefix to be used for file copy paths from the master (e.g. "borg@aws-borgcollector-001:")
 - USERLIST - Path for the PowerShell AD user dump (e.g. "/mnt/borg_ad/borg_users.json")

## Installation
 - Set up a PostgreSQL database with a dedicated admin user. This database will be used for both the Django ORM and the creation/storage of intermediate tables for publishing, so make sure the user has the privileges to create schemas, tables, views, etc.
 - Create a SSH keypair for use in deployment.
 - Fork the repository at https://bitbucket.org/dpaw/borgcollector-state and push it to a Mercurial server you control as a private repository. Add the public key you just generated as a deployment key.
 - Check out this repository (https://bitbucket.org/dpaw/borgcollector) to an appropriate location on an application server (e.g. /var/www/borgcollector). Make sure there are three subfolders: **staticfiles**, **download** and **logs**, which are owned by www-data.
 - It's recommended that you create a virtualenv to install all of the dependencies into (using pip install -r requirements.txt), and create a .env file so the server can be started with Honcho.
 - Check out your fork of borgcollector-state to an appropriate location (e.g. /var/www/borgcollector/borgcollector-state). Make sure the path is owned by www-data and readable by the borg user.
 - On the application server, create a new UNIX user "borg". This user will be used by the slaves to initiate rsync transfers of e.g. DB tables over SSH. Make sure this user has the public key you generated added under .ssh/authorized_keys.
 - Install postgresql-client-x.x and gdal-bin. For EPSG autodetection in ESRI shapefiles, it's recommended you find the following files on the internet and add them to your GDAL share path (e.g. /usr/share/gdal/1.10): cubewerx_extra.wkt esri_extra.wkt epsg_esri.wkt.gz
 - If required, do an initial syncdb to create the Django model schema.


## Model info

 - Input tables define ogr2ogr vrt sources from which to import data
 - Publish defines a script to publish an input table with
 - NormalTable is a table definition with constraints of a 'normalised' table
 - Normalise is a script to produce a normal table from input tables
 - Replica is a remote postgresql server which the master (this app) will create databases for each workspace and populate with harvested information.
    - Also includes a geoserver configuration utility
 - ForeignTable is a table that the foreign data wrapper (FDW) server proxies to allow for harvesting
