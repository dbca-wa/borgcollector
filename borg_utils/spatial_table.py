from django.conf import settings

from .db_util import defaultDbUtil

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

    _check_table_exist_sql = "SELECT count(1) FROM pg_catalog.pg_class a JOIN pg_catalog.pg_namespace b ON a.relnamespace = b.oid WHERE b.nspname = '{0}' AND a.relname = '{1}'"

    _get_geometry_columns_sql = "SELECT f_geometry_column,type  FROM public.geometry_columns WHERE f_table_catalog = '{0}' AND f_table_schema = '{1}' AND f_table_name = '{2}'"
    _get_geography_columns_sql = "SELECT f_geography_column,type  FROM public.geography_columns WHERE f_table_catalog = '{0}' AND f_table_schema = '{1}' AND f_table_name = '{2}'"
    _get_raster_columns_sql = "SELECT r_raster_column  FROM public.raster_columns WHERE r_table_catalog = '{0}' AND r_table_schema = '{1}' AND r_table_name = '{2}'"

    _check_index_sql = "SELECT COUNT(1) FROM pg_catalog.pg_index a JOIN pg_catalog.pg_class b ON a.indexrelid = b.oid JOIN pg_catalog.pg_class c ON a.indrelid = c.oid JOIN pg_catalog.pg_namespace d ON c.relnamespace = d.oid WHERE d.nspname='{0}' AND c.relname='{1}' AND b.relname='{2}'"
    _create_index_sql = "CREATE INDEX \"{2}\" ON \"{0}\".\"{1}\" USING GIST ({3})"
    _drop_index_sql = "DROP INDEX IF EXISTS \"{0}\".\"{1}\""

    _retrieve_bbox_sql = "SELECT public.ST_XMIN(a.bbox), public.ST_YMIN(a.bbox), public.ST_XMAX(a.bbox), public.ST_YMAX(a.bbox) FROM (SELECT public.st_extent(\"{2}\") AS bbox  FROM \"{0}\".\"{1}\") a"
    _retrieve_crs_sql = "SELECT FIND_SRID('{0}','{1}','{2}');"

    _cache = dict()

    _types = ['GEOMETRY','POINT','LINESTRING','POLYGON','MULTIPOINT','MULTILINESTRING','MULTIPOLYGON']

    @staticmethod
    def get_instance(schema,table,refresh=False,bbox=False,crs=False,dbUtil=None):
        dbUtil = dbUtil or defaultDbUtil
        o = None
        if refresh:
            o = SpatialTable(dbUtil,schema,table)
            SpatialTable._cache[(dbUtil.id,schema,table)] = o
        else:
            try:
                o = SpatialTable._cache[(dbUtil.id,schema,table)]
            except:
                o = SpatialTable(dbUtil,schema,table)
                SpatialTable._cache[(schema,table)] = o

        if bbox and not o._bbox:
            o._retrieve_bbox()
        if crs and not o._crs:
            o._retrieve_crs()
        return o

    def __init__(self,dbUtil,schema,table):
        self._dbUtil = dbUtil
        self._geometry_columns = []
        self._geography_columns = []
        self._raster_columns = []
        self._spatial_type = 0
        self._spatial_type_desc = ""
        self._schema = schema
        self._table = table
        self._bbox = False
        self._crs = False
        self._initialize()
    
    def reset(self):
        """
        Clear the cache and reload all information from database.
        """
        self.__init__()

    @staticmethod
    def get_type_id(type_name):
        try:
            return SpatialTable._type_dict[type_name.upper()]           
        except:
            if hasattr(SpatialTable,"_type_dict"):
                return 0
            else:
                type_id = 0
                type_dict = {}
                for t in SpatialTable._types:
                    type_dict[t] = type_id
                    type_id += 1
                SpatialTable._type_dict = type_dict
                return SpatialTable.get_type_id(type_name)
                       
    def _initialize(self):
        #not exist, reload again
        if self._dbUtil.table_exists(self._table,self._schema):
            rows = self._dbUtil.query(SpatialTable._get_geometry_columns_sql.format(self._dbUtil.database,self._schema,self._table))
            self._geometry_columns = [[x[0],x[1],None,None] for x in rows]
            
            rows = self._dbUtil.query(SpatialTable._get_geography_columns_sql.format(self._dbUtil.database,self._schema,self._table))
            self._geography_columns = [[x[0],x[1],None,None] for x in rows]
            
            rows = self._dbUtil.query(SpatialTable._get_raster_columns_sql.format(self._dbUtil.database,self._schema,self._table))
            self._raster_columns = [x[0] for x in rows]

            self._spatial_type = 0
            
            column_index = 0
            if self._geometry_columns:
                for column in self._geometry_columns:
                    self._spatial_type += ((1 << 4) | SpatialTable.get_type_id(column[1])) << (column_index * 6)
                    column_index += 1
                    if column_index >= 5: break;

            if self._geography_columns and column_index < 5:
                for column in self._geography_columns:
                    self._spatial_type += ((2 << 4) | SpatialTable.get_type_id(column[1])) << (column_index * 6)
                    column_index += 1
                    if column_index >= 5: break;

            if self._raster_columns and column_index < 5:
                for column in self._raster_columns:
                    self._spatial_type += (3 << 4) << (column_index * 6)
                    column_index += 1
                    if column_index >= 5: break;

            self._spatial_type_desc = SpatialTable.get_spatial_type_desc(self._spatial_type)

    def _retrieve_bbox(self):
        self._bbox = False
        if self._geometry_columns:
            row = None
            for column in self._geometry_columns:
                row = self._dbUtil.get(SpatialTable._retrieve_bbox_sql.format(self._schema,self._table,column[0]))
                if any(row):
                    column[2] =  (row[0],row[1],row[2],row[3])
                else:
                    column[2] =  (108,-45,155,-10)
                
        if self._geography_columns:
            row = None
            for column in self._geography_columns:
                row = self._dbUtil.get(SpatialTable._retrieve_bbox_sql.format(self._schema,self._table,column[0]))
                if row[0]:
                    column[2] =  (row[0],row[1],row[2],row[3])
                else:
                    column[2] =  (108,-45,155,-10)
                
        self._bbox = True

    def _retrieve_crs(self):
        self._crs = False
        if self._geometry_columns:
            row = None
            for column in self._geometry_columns:
                row = self._dbUtil.get(SpatialTable._retrieve_crs_sql.format(self._schema,self._table,column[0]))
                column[3] =  "EPSG:{}".format(row[0]) if row else settings.DEFAULT_CRS
                
        if self._geography_columns:
            row = None
            for column in self._geography_columns:
                row = self._dbUtil.get(SpatialTable._retrieve_crs_sql.format(self._schema,self._table,column[0]))
                column[3] =  "EPSG:{}".format(row[0]) if row else settings.DEFAULT_CRS
                
        self._crs = True


    @property
    def spatial_column(self):
        return self._geometry_columns[0][0] if self._geometry_columns else (self._geography_columns[0][0] if self._geography_columns else ( self._raster_columns[0][0] if self._raster_columns else None))

    @property
    def bbox(self):
        return self._geometry_columns[0][2] if self._geometry_columns else (self._geography_columns[0][2] if self._geography_columns else ( self._raster_columns[0][2] if self._raster_columns else None))

    @property
    def crs(self):
        return self._geometry_columns[0][3] if self._geometry_columns else (self._geography_columns[0][3] if self._geography_columns else ( self._raster_columns[0][3] if self._raster_columns else None))

    @property
    def geometry_columns(self):
        return self._geometry_columns

    @property
    def geography_columns(self):
        return self._geography_columns

    @property
    def spatial_type(self):
        return self._spatial_type

    @property
    def spatial_type_desc(self):
        return self._spatial_type_desc

    @property
    def is_geometry(self):
        return SpatialTable.check_geometry(self._spatial_type)

    @property
    def is_geography(self):
        return SpatialTable.check_geography(self._spatial_type)

    @property
    def is_raster(self):
        return SpatialTable.check_raster(self._spatial_type)

    @property
    def is_normal(self):
        return SpatialTable.check_normal(self._spatial_type)

    @property
    def is_spatial(self):
        return SpatialTable.check_spatial(self._spatial_type)

    def create_indexes(self):
        """
        create gist index for each geometry column
        """
        index_name = None
        index_exists = False
        for c in self._geometry_columns:
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
        for c in self._geometry_columns:
            #import ipdb; ipdb.set_trace()
            index_name = "{0}_{1}".format(self._table,c[0])
            self._dbUtil.update(SpatialTable._drop_index_sql.format(self._schema,index_name))

    @staticmethod
    def get_spatial_type_desc(spatial_type):
        if spatial_type:
            index = 0   
            desc = None
            while index < 5:
                type_category = (spatial_type  >> (index * 6) + 4) & 0b11
                column_type_id = (spatial_type  >> (index * 6)) & 0b001111
                index += 1
                if type_category == 0:
                    break
                elif type_category == 1:
                    s = "Geometry"
                elif type_category == 2:
                    s = "Geography"
                elif type_category == 3:
                    s = "Raster"
                if column_type_id > 0:
                    try:
                        s = "{0}({1})".format(s,SpatialTable._types[column_type_id])
                    except:
                        pass
                if desc:
                    desc = "{0} | {1}".format(desc,s)
                else:
                    desc = s
            return desc
        else:
            return "Normal Table"

    @staticmethod
    def check_geometry(spatial_type):
        index = 0
        while index < 5:
            value = (spatial_type >> index * 6) & 0b110000
            if value == 0: 
                break
            elif value == 0b010000: 
                return True
            index = index + 1

        return False
            
    @staticmethod
    def check_geography(spatial_type):
        index = 0
        while index < 5:
            value = (spatial_type >> index * 6) & 0b110000
            if value == 0: 
                break
            elif value == 0b100000: 
                return True
            index = index + 1

        return False
            
    @staticmethod
    def check_raster(spatial_type):
        index = 0
        while index < 5:
            value = (spatial_type >> index * 6) & 0b110000
            if value == 0: 
                break
            elif value == 0b110000: 
                return True
            index = index + 1

        return False
            
    @staticmethod
    def check_normal(spatial_type):
        return spatial_type == 0
            
    @staticmethod
    def check_spatial(spatial_type):
        return spatial_type > 0
            
        
class SpatialTableMixin(object):
    @property
    def is_normal(self):
        return SpatialTable.check_normal(self.spatial_type)
    
    @property
    def is_spatial(self):
        return SpatialTable.check_spatial(self.spatial_type)
    
    @property
    def is_raster(self):
        return SpatialTable.check_raster(self.spatial_type)
    
    @property
    def is_geometry(self):
        return SpatialTable.check_geometry(self.spatial_type)
    
    @property
    def is_geography(self):
        return SpatialTable.check_geography(self.spatial_type)

    @property
    def spatial_type_desc(self):
        return SpatialTable.get_spatial_type_desc(self.spatial_type)
    
