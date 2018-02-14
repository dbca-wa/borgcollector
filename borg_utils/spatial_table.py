from django.conf import settings
import os
from .db_util import defaultDbUtil
import random
import json
import traceback
import hashlib


def hashcode(text):
    m = hashlib.md5()
    m.update(text)
    return m.hexdigest()

class SpatialTable(object):
    """
    get a table's spatial type
    spatial type format:
        support up to 5 spatial column in one table
        each spatial column uses 6 bit postitions, total 5 spatial columns uses 30 bit positions.
        The bit position index from 0 to 5, and from left to right.
        The bit0 and bit1 represents the spatial category, currently support "geometry","geography" and "raster"
        From bit2 to bit5 represents the spatial data type, currently support 'GEOMETRY','POINT','LINESTRING','POLYGON','MULTIPOINT','MULTILINESTRING','MULTIPOLYGON'
    """

    _get_geometry_columns_sql = "SELECT f_geometry_column,type  FROM public.geometry_columns WHERE f_table_catalog = '{0}' AND f_table_schema = '{1}' AND f_table_name = '{2}'"
    _get_geography_columns_sql = "SELECT f_geography_column,type  FROM public.geography_columns WHERE f_table_catalog = '{0}' AND f_table_schema = '{1}' AND f_table_name = '{2}'"
    _get_raster_columns_sql = "SELECT r_raster_column  FROM public.raster_columns WHERE r_table_catalog = '{0}' AND r_table_schema = '{1}' AND r_table_name = '{2}'"

    _check_index_sql = "SELECT COUNT(1) FROM pg_catalog.pg_index a JOIN pg_catalog.pg_class b ON a.indexrelid = b.oid JOIN pg_catalog.pg_class c ON a.indrelid = c.oid JOIN pg_catalog.pg_namespace d ON c.relnamespace = d.oid WHERE d.nspname='{0}' AND c.relname='{1}' AND b.relname='{2}'"
    _create_index_sql = "CREATE INDEX \"{2}\" ON \"{0}\".\"{1}\" USING GIST ({3})"
    _drop_index_sql = "DROP INDEX IF EXISTS \"{0}\".\"{1}\""

    _retrieve_bbox_sql = "SELECT public.ST_XMIN(a.bbox), public.ST_YMIN(a.bbox), public.ST_XMAX(a.bbox), public.ST_YMAX(a.bbox) FROM (SELECT public.st_extent(\"{2}\") AS bbox  FROM \"{0}\".\"{1}\") a"
    _retrieve_geometry_crs_sql = "SELECT srid FROM public.geometry_columns WHERE f_table_schema='{0}' AND f_table_name='{1}' AND f_geometry_column='{2}';"
    _retrieve_geography_crs_sql = "SELECT srid FROM public.geography_columns WHERE f_table_schema='{0}' AND f_table_name='{1}' AND f_geography_column='{2}';"

    def __init__(self,dbUtil,schema,table,sql=None,spatial_info=None,bbox=False,crs=False):
        self._dbUtil = dbUtil
        self._schema = schema
        self._table = table
        self._sql = sql
        self._bbox_retrieved = False
        self._crs_retrieved = False
        self._spatial_info = None
        self._spatial_info_version = None
        self._spatial_info_desc = None
        self._parse(spatial_info)
        if self._spatial_info is None:
            self._spatial_info= [[],[],[]]
            if self._schema is not None:
                self._initialize(bbox,crs)


    @property
    def geometry_columns(self):
        return self._spatial_info[0]

    @property
    def geography_columns(self):
        return self._spatial_info[1]

    @property
    def raster_columns(self):
        return self._spatial_info[2]
    
    
    def refresh(self,bbox=False,crs=False):
        self.__init__(self._dbUtil,self._schema,self._table,sql=self._sql,bbox=bbox,crs=crs)
        self._spatial_info_version = None
        return self

    def load(self,spatial_info):
        self._parse(spatial_info)

    def _parse(self,spatial_info):
        if spatial_info is None or spatial_info == "": 
            return
        try:
            #print "parse spatial info ({}) for table ({}.{})".format(spatial_info,self._schema,self._table)
            info = json.loads(spatial_info)
            if info is None or not isinstance(info,list) or len(info) != 3:
                return

            bbox_retrieved = False
            crs_retrieved = False
            for columns in info:
                for column in columns:
                    if column[2]:
                        bbox_retrieved = True
                    if column[3]:
                        crs_retrieved = True
                    if bbox_retrieved and crs_retrieved:
                        break
                if bbox_retrieved and crs_retrieved:
                    break

            self._spatial_info = info
            self._bbox_retrieved = bbox_retrieved
            self._crs_retrieved = crs_retrieved
            self._spatial_info_version = hashcode(spatial_info)
            self._spatial_info_desc = None
        except:
            pass


    def _initialize(self,bbox=False,crs=False):
        #not exist, reload again
        try:
            #print "Analysis the spatial info for table({}.{}). bbox={}, crs={}".format(self._schema,self._table,bbox,crs)
            if self._sql:
                if self._dbUtil.table_exists(self._schema,self._table):
                    raise "The table/view({0}) already exists, plase choose another name.".foramt(self._table)
                #create the temp view
                self._dbUtil.execute("CREATE VIEW \"{0}\".\"{1}\" AS {2}".format(self._schema,self._table,self._sql))
    
            if self._dbUtil.table_exists(self._table,self._schema):
                rows = self._dbUtil.query(SpatialTable._get_geometry_columns_sql.format(self._dbUtil.database,self._schema,self._table))
                self._spatial_info[0] = [[x[0],x[1],None,None] for x in rows]
                
                rows = self._dbUtil.query(SpatialTable._get_geography_columns_sql.format(self._dbUtil.database,self._schema,self._table))
                self._spatial_info[1] = [[x[0],x[1],None,None] for x in rows]
                
                rows = self._dbUtil.query(SpatialTable._get_raster_columns_sql.format(self._dbUtil.database,self._schema,self._table))
                self._spatial_info[2] = [[x[0],None,None,None] for x in rows]
    
    
    
            if self._sql or bbox:
                self._retrieve_bbox()

            if self._sql or crs:
                self._retrieve_crs()
    
            if self._sql:
                self._create_sql = self._dbUtil.get_create_table_sql(self._table,self._schema)

            self._spatial_info_desc = None
        finally:
            if self._sql:
                self._dbUtil.execute("DROP VIEW IF EXISTS \"{0}\".\"{1}\"".format(self._schema,self._table))

    def _retrieve_bbox(self):
        if self._bbox_retrieved or self._schema is None:
            return

        if self.geometry_columns:
            row = None
            for column in self.geometry_columns:
                row = self._dbUtil.get(SpatialTable._retrieve_bbox_sql.format(self._schema,self._table,column[0]))
                if any(row):
                    column[2] =  (row[0],row[1],row[2],row[3])
                else:
                    column[2] =  (108,-45,155,-10)
                
        if self.geography_columns:
            row = None
            for column in self.geography_columns:
                row = self._dbUtil.get(SpatialTable._retrieve_bbox_sql.format(self._schema,self._table,column[0]))
                if row[0]:
                    column[2] =  (row[0],row[1],row[2],row[3])
                else:
                    column[2] =  (108,-45,155,-10)

        self._spatial_info_desc = None
        self._spatial_info_version = None
        self._bbox_retrieved = True

    def _retrieve_crs(self):
        if self._crs_retrieved or self._schema is None: 
            return

        if self.geometry_columns:
            row = None
            for column in self.geometry_columns:
                row = self._dbUtil.get(SpatialTable._retrieve_geometry_crs_sql.format(self._schema,self._table,column[0]))
                column[3] =  "EPSG:{}".format(row[0]) if row else settings.DEFAULT_CRS
                
        if self.geography_columns:
            row = None
            for column in self.geography_columns:
                row = self._dbUtil.get(SpatialTable._retrieve_geography_crs_sql.format(self._schema,self._table,column[0]))
                column[3] =  "EPSG:{}".format(row[0]) if row else settings.DEFAULT_CRS
                
        self._spatial_info_desc = None
        self._spatial_info_version = None
        self._crs_retrieved = True

    def get_create_table_sql(self):
        sql = getattr(self,"_create_sql",None)
        if not sql and not self._sql:
            sql = self._dbUtil.get_create_table_sql(self._table,self._schema)
            setattr(self,"_create_sql",sql)
        return sql

    @staticmethod
    def get_bbox(dbUtil,sql):
        row = dbUtil.get("SELECT public.ST_XMIN(bbox), public.ST_YMIN(bbox), public.ST_XMAX(bbox), public.ST_YMAX(bbox) FROM (SELECT public.st_extent(the_geom) AS bbox  FROM ({}))".format(sql) )
        if any(row):
            return  (row[0],row[1],row[2],row[3])
        else:
            return  (108,-45,155,-10)

    def _get_spatial_column(self,column_name=None,index=None):
        if column_name:
            for columns in  (self._spatial_info):
                if columns:
                    for column in columns:
                        if column[0] == column_name:
                            return column
        else:
            for columns in  (self._spatial_info):
                if columns:
                    if len(columns) > index:
                        return columns[index]
                    else:
                        index = index - len(columns)
        return None

    def spatial_column(self,index=0):
        column = self._get_spatial_column(index = index)
        return column[0] if column else None

    def spatial_type_by_index(self,index=0):
        column = self._get_spatial_column(index = index)
        return column[1] if column else None

    def bbox(self,column_name):
        self._retrieve_bbox()
        column = self._get_spatial_column(column_name=column_name)
        return column[2] if column else None

    def bbox_by_index(self,index):
        self._retrieve_bbox()
        column = self._get_spatial_column(index=index)
        return column[2] if column else None

    def crs(self,column_name):
        self._retrieve_crs()
        column = self._get_spatial_column(column_name=column_name)
        return column[3] if column else None

    def crs_by_index(self,index):
        self._retrieve_crs()
        column = self._get_spatial_column(index=index)
        return column[3] if column else None

    @property
    def spatial_info(self):
        json_data = json.dumps(self._spatial_info)
        self._spatial_info_version = hashcode(json_data)
        return json_data

    @property
    def spatial_info_desc(self):
        if not self._spatial_info_desc:
            msg = ""
            for columns in self._spatial_info:
                if columns:
                    for column in columns:
                        if column[1]:
                            if column[2]:
                                column_desc = "{} {}({}) {}".format(column[0],column[1] or "Unknown",column[3] or "Unknown" ,column[2] or "")
                            else:
                                column_desc = "{} {}({})".format(column[0],column[1] or "Unknown",column[3] or "Unknown" )
                        msg = "{}{}{}".format(msg,os.linesep,column_desc) if msg else column_desc
            self._spatial_info_desc = msg
        return self._spatial_info_desc

    @property
    def is_geometry(self):
        return self.geometry_columns and True or False

    @property
    def is_geography(self):
        return self.geography_columns and True or False

    @property
    def is_raster(self):
        return self.raster_columns and True or False

    @property
    def is_normal(self):
        return not self.is_spatial

    @property
    def is_spatial(self):
        return self.is_geometry or self.is_geography or self.is_raster

    def create_indexes(self):
        """
        create gist index for each geometry column
        """
        index_name = None
        index_exists = False
        for c in self.geometry_columns:
            #import ipdb; ipdb.set_trace()
            index_name = "{0}_{1}".format(self._table,c[0])
            index_exists = self._dbUtil.exists(SpatialTable._check_index_sql.format(self._schema,self._table,index_name))
            if not index_exists:
                self._dbUtil.update(SpatialTable._create_index_sql.format(self._schema,self._table,index_name,c[0]))
            
    def drop_indexes(self):
        """
        drop gist index for each geometry column and geography column
        """
        index_name = None
        for c in self.geometry_columns:
            #import ipdb; ipdb.set_trace()
            index_name = "{0}_{1}".format(self._table,c[0])
            self._dbUtil.update(SpatialTable._drop_index_sql.format(self._schema,index_name))

SpatialTableCache = {}
class SpatialTableMixin(object):
    def spatialTable(self,schema=None,refresh=False,bbox=False,crs=False):
        o = getattr(self,"_spatialTable",None)
        if o:
            if refresh:
                o._schema = schema
                o.refresh(bbox,crs)
        else:
            schema = schema or self.table_schema
            dbUtil = self.db_util or defaultDbUtil
            try:
                o = SpatialTableCache[(dbUtil.id,self.table_schema,self.table_name)]
                if refresh:
                    #print "refresh cached spatialTable for table ({}.{}).bbox={}, crs={}, refresh={}".format(self.table_schema,self.table_name,bbox,crs,refresh)
                    o._schema = schema
                    o.refresh(bbox,crs)
                elif o._spatial_info_version and self.spatial_info and o._spatial_info_version != hashcode(self.spatial_info):
                    #print "reload the spatialTable for table ({}.{}).bbox={}, crs={}, refresh={}, version = {}, new version= {}".format(self.table_schema,self.table_name,bbox,crs,refresh,o._spatial_info_version,hashcode(self.spatial_info))
                    o.load(self.spatial_info)
                else:
                    #print "get cached spatialTable for table ({}.{}).bbox={}, crs={}, refresh={}, version = {}, new version= {}".format(self.table_schema,self.table_name,bbox,crs,refresh,o._spatial_info_version,hashcode(self.spatial_info))
                    pass
            except:
                #print "create spatialTable for table ({}.{}).bbox={}, crs={}, refresh={}".format(self.table_schema,self.table_name,bbox,crs,refresh)
                o = SpatialTable(
                    dbUtil,
                    schema or self.table_schema,
                    self.table_name,
                    sql=getattr(self,"table_sql",None),
                    spatial_info=None if refresh else self.spatial_info,
                    bbox=bbox,
                    crs=crs
                )
                SpatialTableCache[(dbUtil.id,self.table_schema,self.table_name)] = o
            setattr(self,"_spatialTable",o)

        return o

    def refresh_spatial_info(self,schema=None,bbox=True,crs=True):
        self.spatialTable(schema=schema,refresh=True,bbox=bbox,crs=crs)
        return self

    def create_indexes(self,schema=None):
        self.spatialTable(schema).create_indexes()

    def drop_indexes(self,schema=None):
        self.spatialTable(schema).refresh().drop_indexes()

    def get_create_table_sql(self):
        return self.spatialTable().get_create_table_sql()

    @property
    def is_normal(self):
        return self.spatialTable().is_normal
    
    @property
    def is_spatial(self):
        return self.spatialTable().is_spatial
    
    @property
    def is_raster(self):
        return self.spatialTable().is_raster
    
    @property
    def is_geometry(self):
        return self.spatialTable().is_geometry
    
    @property
    def is_geography(self):
        return self.spatialTable().is_geography

    @property
    def spatial_info_desc(self):
        return self.spatialTable().spatial_info_desc

    def get_spatial_info(self):
        return self.spatialTable().spatial_info

    @property
    def spatial_column(self):
        return self.spatialTable().spatial_column(0)

    @property
    def spatial_type(self):
        return self.spatialTable().spatial_type_by_index(0)
  
    @property
    def bbox(self):
        return self.spatialTable().bbox_by_index(0)
    
    @property
    def crs(self):
        return self.spatialTable().crs_by_index(0)
