from django.conf import settings

class SpatialTable(object):
    """
    get a table's spatial type
    """

    _check_table_exist_sql = "SELECT count(1) FROM pg_catalog.pg_class a JOIN pg_catalog.pg_namespace b ON a.relnamespace = b.oid WHERE b.nspname = '{0}' AND a.relname = '{1}'"

    _get_geometry_columns_sql = "SELECT f_geometry_column,type  FROM public.geometry_columns WHERE f_table_catalog = '{0}' AND f_table_schema = '{1}' AND f_table_name = '{2}'"
    _get_geography_columns_sql = "SELECT f_geography_column,type  FROM public.geography_columns WHERE f_table_catalog = '{0}' AND f_table_schema = '{1}' AND f_table_name = '{2}'"
    _get_raster_columns_sql = "SELECT r_raster_column  FROM public.raster_columns WHERE r_table_catalog = '{0}' AND r_table_schema = '{1}' AND r_table_name = '{2}'"

    _check_index_sql = "SELECT COUNT(1) FROM pg_index a JOIN pg_class b ON a.indexrelid = b.oid JOIN pg_class c ON a.indrelid = c.oid JOIN pg_namespace d ON c.relnamespace = d.oid WHERE d.nspname='{0}' AND c.relname='{1}' AND b.relname='{2}'"
    _create_index_sql = "CREATE INDEX \"{2}\" ON \"{0}\".\"{1}\" USING GIST ({3})"
    _drop_index_sql = "DROP INDEX IF EXISTS \"{0}\".\"{1}\""

    _retrieve_bbox_sql = "SELECT ST_XMIN(a.bbox), ST_YMIN(a.bbox), ST_XMAX(a.bbox), ST_YMAX(a.bbox) FROM (SELECT st_extent(\"{2}\") AS bbox  FROM \"{0}\".\"{1}\") a"
    _retrieve_crs_sql = "SELECT public.ST_SRID({2}) FROM \"{0}\".\"{1}\" LIMIT 1;"

    _database = (settings.DATABASES["default"])["NAME"]
    _cache = dict()

    _types = ['GEOMETRY','POINT','LINESTRING','POLYGON','MULTIPOINT','MULTILINESTRING','MULTIPOLYGON']

    @staticmethod
    def get_instance(cursor,schema,table,refresh=False,bbox=False,crs=False):
        o = None
        if refresh:
            o = SpatialTable(cursor,schema,table,bbox)
            SpatialTable._cache[(schema,table)] = o
        else:
            try:
                o = SpatialTable._cache[(schema,table)]
            except:
                o = SpatialTable(cursor,schema,table,bbox)
                SpatialTable._cache[(schema,table)] = o

            if bbox and not o._bbox:
                o._retrieve_bbox(cursor)
            if bbox and not o._crs:
                o._retrieve_crs(cursor)
        return o

    def __init__(self,cursor,schema,table,bbox=False,crs=False):
        self._exists = False
        self._geometry_columns = []
        self._geography_columns = []
        self._raster_columns = []
        self._spatial_type = 0
        self._spatial_type_desc = ""
        self._schema = schema
        self._table = table
        self._bbox = bbox
        self._crs = crs
        self._initialize(cursor)
    
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
                       
    def _initialize(self,cursor):
        if not self._exists:
            #not exist, reload again
            sql_result = cursor.execute(SpatialTable._check_table_exist_sql.format(self._schema,self._table))
            if sql_result:               
                self._exists = sql_result.fetchone()[0] and True or False
            else:
                self._exists = row = cursor.fetchone()[0] and True or False
            if self._exists:
                sql_result = cursor.execute(SpatialTable._get_geometry_columns_sql.format(SpatialTable._database,self._schema,self._table))
                if sql_result:               
                    self._geometry_columns = [[x[0],x[1],None,None] for x in sql_result.fetchall()]
                else:
                    self._geometry_columns = [[x[0],x[1],None,None] for x in cursor.fetchall()]
                
                sql_result = cursor.execute(SpatialTable._get_geography_columns_sql.format(SpatialTable._database,self._schema,self._table))
                if sql_result:               
                    self._geography_columns = [[x[0],x[1],None,None] for x in sql_result.fetchall()]
                else:
                    self._geography_columns = [[x[0],x[1],None,None] for x in cursor.fetchall()]
                
                sql_result = cursor.execute(SpatialTable._get_raster_columns_sql.format(SpatialTable._database,self._schema,self._table))
                if sql_result:               
                    self._raster_columns = [x[0] for x in sql_result.fetchall()]
                else:
                    self._raster_columns = [x[0] for x in cursor.fetchall()]

                self._spatial_type = 0
                
                if self._bbox:
                    self._retrieve_bbox(cursor)

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

    def _retrieve_bbox(self,cursor):
        self._bbox = False
        if self._geometry_columns:
            row = None
            for column in self._geometry_columns:
                sql_result = cursor.execute(SpatialTable._retrieve_bbox_sql.format(self._schema,self._table,column[0]))
                if sql_result:               
                    row = sql_result.fetchone()
                else:
                    row = cursor.fetchone()
                if row[0]:
                    column[2] =  (row[0],row[1],row[2],row[3])
                
        if self._geography_columns:
            row = None
            for column in self._geography_columns:
                sql_result = cursor.execute(SpatialTable._retrieve_bbox_sql.format(self._schema,self._table,column[0]))
                if sql_result:               
                    row = sql_result.fetchone()
                else:
                    row = cursor.fetchone()
                if row[0]:
                    column[2] =  (row[0],row[1],row[2],row[3])
                
        self._bbox = True

    def _retrieve_crs(self,cursor):
        self._crs = False
        if self._geometry_columns:
            row = None
            for column in self._geometry_columns:
                sql_result = cursor.execute(SpatialTable._retrieve_crs_sql.format(self._schema,self._table,column[0]))
                if sql_result:               
                    row = sql_result.fetchone()
                else:
                    row = cursor.fetchone()
                column[3] =  "EPSG:{}".format(row[0]) if row else settings.DEFAULT_CRS
                
        if self._geography_columns:
            row = None
            for column in self._geography_columns:
                sql_result = cursor.execute(SpatialTable._retrieve_bbox_sql.format(self._schema,self._table,column[0]))
                if sql_result:               
                    row = sql_result.fetchone()
                else:
                    row = cursor.fetchone()
                column[3] =  "EPSG:{}".format(row[0]) if row else settings.DEFAULT_CRS
                
        self._crs = True


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

    def create_indexes(self,cursor):
        """
        create gist index for each geometry column
        """
        index_name = None
        index_exists = False
        for c in self._geometry_columns:
            #import ipdb; ipdb.set_trace()
            index_name = "{0}_{1}".format(self._table,c[0])
            sql_result = cursor.execute(SpatialTable._check_index_sql.format(self._schema,self._table,index_name))
            if sql_result:               
                index_exists = sql_result.fetchone()[0] and True or False
            else:
                index_exists = cursor.fetchone()[0] and True or False
            
            if not index_exists:
                cursor.execute(SpatialTable._create_index_sql.format(self._schema,self._table,index_name,c[0]))
            
    def drop_indexes(self,cursor):
        """
        drop gist index for each geometry column and geography column
        """
        index_name = None
        for c in self._geometry_columns:
            #import ipdb; ipdb.set_trace()
            index_name = "{0}_{1}".format(self._table,c[0])
            sql_result = cursor.execute(SpatialTable._drop_index_sql.format(self._schema,index_name))

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
            
        

