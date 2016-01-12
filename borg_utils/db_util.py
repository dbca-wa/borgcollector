import tempfile
import os
import subprocess

from django.conf import settings
from django.db import connection

class DbUtil(object):
    """
    a set of utility method to access db
    """
    def __init__(self):
        raise Exception("Utility class can't be instantiated.")

    
    _database = settings.DATABASES["default"]
    _env = os.environ.copy()
    _table_schema_dump_cmd = ["pg_dump", "-h", _database["HOST"], "-d", _database["NAME"], "-U", _database["USER"], "-F", "p", "-w", "-x", "-O", "--no-security-labels", "--no-tablespaces", "-s"]
    if 'PASSWORD' in _database and  _database['PASSWORD'].strip():
        _env["PGPASSWORD"] = _database["PASSWORD"]
    if _database["PORT"]:
        _table_schema_dump_cmd += ["-p", str(_database["PORT"])]

    _cursor=connection.cursor()

    _query_index_constraint_sql = """
SELECT s.conname ,s.contype
FROM pg_constraint s JOIN pg_class c ON s.conrelid = c.oid JOIN pg_namespace n on c.relnamespace = n.oid 
WHERE n.nspname='{0}' and c.relname='{1}' and s.contype in ('p','u')
"""
    _query_index_sql = """
SELECT ci.relname,i.indisprimary 
FROM pg_index i JOIN pg_class ci ON i.indexrelid = ci.oid JOIN pg_class ct ON i.indrelid = ct.oid JOIN pg_namespace np on ct.relnamespace = np.oid 
WHERE np.nspname='{0}' and ct.relname='{1}'
"""

    @staticmethod
    def get_create_table_sql(schema,table):
        #get the input table structure
        f = tempfile.NamedTemporaryFile(delete=False)
        f.close()
        cmd = DbUtil._table_schema_dump_cmd + ["-t", schema + "." + table, "-f", f.name]
        output = subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE, env=DbUtil._env).communicate()
        if output[1].strip() :
            raise Exception(output[1])
        try:
            reader = open(f.name,'r') 
            return ''.join([s for s in reader if not (s.startswith('SET') or s.startswith('--')) and s.strip() ])
        finally:
            if reader:
                reader.close()
            os.unlink(f.name)

    @staticmethod
    def drop_all_indexes(schema,table,include_pk=False):
        """
        drop all indexes.
        drop primary key also if include_pk is true
        """
        #drop related constraint first
        #import ipdb;ipdb.set_trace()
        sql_result = DbUtil._cursor.execute(DbUtil._query_index_constraint_sql.format(schema,table))
        rows = None
        if sql_result:               
            rows = sql_result.fetchall()
        else:
            rows = DbUtil._cursor.fetchall()
        drop_constraint_sql = "\r\n".join(["ALTER TABLE \"{0}\".{1} DROP CONSTRAINT IF EXISTS {2} CASCADE;".format(schema,table,r[0]) for r in rows if r[1] != 'p' or include_pk ])
        if drop_constraint_sql:
            DbUtil._cursor.execute(drop_constraint_sql)

        sql_result = DbUtil._cursor.execute(DbUtil._query_index_sql.format(schema,table))
        rows = None
        if sql_result:               
            rows = sql_result.fetchall()
        else:
            rows = DbUtil._cursor.fetchall()
        drop_index_sql = "\r\n".join(["DROP INDEX IF EXISTS \"{0}\".\"{1}\" CASCADE;".format(schema,r[0]) for r in rows if not r[1] or include_pk ])
        if drop_index_sql:
            DbUtil._cursor.execute(drop_index_sql)

