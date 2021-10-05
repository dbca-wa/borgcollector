# Dockerfile to build borgcollector image
# Prepare the base environment.
FROM ubuntu:18.04 as builder_base_borg
MAINTAINER asi@dbca.wa.gov.au
ENV DEBIAN_FRONTEND=noninteractive
LABEL org.opencontainers.image.source https://github.com/dbca-wa/borgcollector

#install required utilities
RUN apt-get update && apt-get install -y software-properties-common
RUN add-apt-repository ppa:ubuntugis/ppa \
    && apt-get update \
    && apt-get install -y --no-install-recommends wget git libmagic-dev gcc binutils gdal-bin libgdal-dev vim python python-setuptools python-dev python-pip tzdata mercurial less \
    && pip install --upgrade pip

RUN sh -c 'echo "deb http://apt.postgresql.org/pub/repos/apt/ `lsb_release -cs`-pgdg main" >> /etc/apt/sources.list.d/pgdg.list' \
    && wget -q https://www.postgresql.org/media/keys/ACCC4CF8.asc -O - | apt-key add -  \ 
    && apt-get update  \
    && apt-get install  -y --no-install-recommends postgresql-client-9.6 \
    && apt-get install  -y --no-install-recommends openssh-client

FROM builder_base_borg as python_libs_borg

RUN groupadd  -g 1001 borg
RUN useradd -d /home/borg -m -s /bin/bash -u 1001 -g 1001 borg
RUN useradd -d /home/borgcollector -m -s /bin/bash -u 1002 -g 1001 borgcollector

WORKDIR /etc/mercurial
COPY mercurial/hgrc ./hgrc

WORKDIR /usr/share/gdal
COPY gdal/epsg_esri.wkt.gz ./epsg_esri.wkt.gz

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt 

#patch libgeos.py
COPY geos/libgeos.py /usr/local/lib/python2.7/dist-packages/django/contrib/gis/geos/libgeos.py

# Install the project (ensure that frontend projects have been built prior to this step).
FROM python_libs_borg
COPY manage.py ./
COPY start_server ./
COPY uwsgi.ini.prod ./uwsgi.ini
COPY borg ./borg
COPY application ./application
COPY borg_utils ./borg_utils
COPY filemanager ./filemanager
COPY harvest ./harvest
COPY layergroup ./layergroup
COPY livelayermanager ./livelayermanager
COPY monitor ./monitor
COPY rolemanager ./rolemanager
COPY tablemanager ./tablemanager
COPY wmsmanager ./wmsmanager
COPY static ./static

RUN python manage.py collectstatic --noinput

RUN chown -R borgcollector:borg ./
RUN chmod -R 755 ./


USER borgcollector
EXPOSE 8080
HEALTHCHECK --interval=1m --timeout=5s --start-period=10s --retries=3 CMD ["wget", "-q", "-O", "-", "http://localhost:8080/"]
CMD ["./start_server"]
