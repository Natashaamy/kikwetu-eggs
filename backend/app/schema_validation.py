"""Compare live structures to a frozen engine-native reference schema."""
import re
import sqlite3
import uuid
from pathlib import Path

MIGRATIONS = Path(__file__).resolve().parents[1] / 'migrations'


class SchemaMismatch(RuntimeError):
    pass


def scripts(postgres):
    suffix = 'schema.sql' if postgres else 'schema_sqlite.sql'
    return [(name, (MIGRATIONS / (name + '_' + suffix)).read_text())
            for name in ('000_legacy', '001_financial_admin', '002_payment_safety')]


def _normal(value, prefix=''):
    value = str(value or '').lower().replace(prefix, '')
    value = re.sub(r'nextval\([^)]*\)', 'sequence_default', value)
    value = re.sub(r'\b(?:public|pg_temp_\d+)\.', '', value)
    return re.sub(r'\s+|"', '', value)


def _sqlite_signature(connection, table):
    columns = {r[1]: tuple(r[2:]) for r in connection.execute(f'PRAGMA table_info("{table}")')}
    foreign = {tuple(r[2:]) for r in connection.execute(f'PRAGMA foreign_key_list("{table}")')}
    indexes = set()
    for r in connection.execute(f'PRAGMA index_list("{table}")'):
        columns_in_index = tuple(c[2] for c in connection.execute(f'PRAGMA index_info("{r[1]}")'))
        definition = connection.execute('SELECT sql FROM sqlite_master WHERE type=\'index\' AND name=?',(r[1],)).fetchone()
        predicate = '' if not definition or not definition[0] or 'WHERE' not in definition[0].upper() else re.split('where', definition[0],flags=re.I)[1]
        indexes.add((r[2],columns_in_index,_normal(predicate)))
    definition = connection.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone()
    # Extract balanced CHECK expressions, including IN lists and nested calls.
    checks = set()
    for match in re.finditer(r'\bCHECK\s*\(',definition[0] if definition else '',re.I):
        depth, end = 1, match.end()
        start = end
        while depth and end < len(definition[0]):
            depth += (definition[0][end]=='(') - (definition[0][end]==')')
            end += 1
        checks.add(_normal(definition[0][start:end-1]))
    return columns, foreign, indexes, checks


def _pg_signature(db, schema, table, prefix=''):
    columns = {}
    for row in db.execute('''SELECT a.attname,format_type(a.atttypid,a.atttypmod) AS type,a.attnotnull,
                            pg_get_expr(d.adbin,d.adrelid) AS default_value
                            FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid
                            JOIN pg_namespace n ON n.oid=c.relnamespace
                            LEFT JOIN pg_attrdef d ON d.adrelid=c.oid AND d.adnum=a.attnum
                            WHERE n.nspname=? AND c.relname=? AND a.attnum>0 AND NOT a.attisdropped''',(schema,table)).fetchall():
        columns[row['attname']] = (row['type'],row['attnotnull'],_normal(row['default_value'],prefix))
    constraints = {_normal(r['definition'],prefix) for r in db.execute('''SELECT pg_get_constraintdef(k.oid) AS definition
                   FROM pg_constraint k JOIN pg_class c ON c.oid=k.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace
                   WHERE n.nspname=? AND c.relname=?''',(schema,table)).fetchall()}
    indexes = set()
    for row in db.execute('''SELECT pg_get_indexdef(i.indexrelid) AS definition FROM pg_index i
                            JOIN pg_class c ON c.oid=i.indrelid JOIN pg_namespace n ON n.oid=c.relnamespace
                            WHERE n.nspname=? AND c.relname=?''',(schema,table)).fetchall():
        # Index names may differ; uniqueness, keys, order, expressions and predicate must match.
        definition = row['definition']
        indexes.add((' UNIQUE ' in definition, _normal(definition.split(' USING ',1)[1],prefix)))
    return columns,constraints,indexes


def validate(db, allow_missing_new=False, allow_missing_indexes=False):
    frozen = scripts(db.postgres)
    full = '\n'.join(sql for _,sql in frozen)
    tables = re.findall(r'CREATE TABLE IF NOT EXISTS (\w+)', full)
    legacy = set(re.findall(r'CREATE TABLE IF NOT EXISTS (\w+)', frozen[0][1]))
    if not db.postgres:
        reference = sqlite3.connect(':memory:')
        try:
            reference.executescript(full)
            existing = {r[0] for r in db.connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            for table in tables:
                if table not in existing:
                    if allow_missing_new and table not in legacy:
                        continue
                    raise SchemaMismatch(f'Missing required table: {table}')
                expected = _sqlite_signature(reference,table)
                actual = _sqlite_signature(db.connection,table)
                for column,value in expected[0].items():
                    if actual[0].get(column) != value:
                        raise SchemaMismatch(f'Incompatible column: {table}.{column}')
                for idx,label in ((1,'foreign keys'),(2,'indexes/unique constraints'),(3,'check constraints')):
                    # Only new explicit non-unique indexes may be installed by this migration.
                    required = expected[idx]
                    if idx==2 and allow_missing_indexes:
                        required = {v for v in required if v[0]}
                    if not required.issubset(actual[idx]):
                        raise SchemaMismatch(f'Incompatible {label}: {table}')
        finally:
            reference.close()
        return
    # TEMP relations provide PostgreSQL's own normalized types/defaults/constraints.
    # All references are rewritten to other TEMP relations, never live tables.
    prefix = 'verify_' + uuid.uuid4().hex[:12] + '_'
    rewritten = re.sub(r'\b('+'|'.join(sorted(tables,key=len,reverse=True))+r')\b',lambda m:prefix+m[0],full)
    rewritten = re.sub(r'CREATE TABLE IF NOT EXISTS', 'CREATE TEMP TABLE',rewritten)
    rewritten = re.sub(r'(INDEX IF NOT EXISTS )(\w+)',lambda m:m[1]+prefix+m[2],rewritten)
    for statement in rewritten.split(';'):
        if statement.strip():
            db.execute(statement)
    temp_schema = db.execute('SELECT nspname FROM pg_namespace WHERE oid=pg_my_temp_schema()').fetchone()['nspname']
    live_schema = db.execute('SELECT current_schema() AS name').fetchone()['name']
    existing = {r['table_name'] for r in db.execute('SELECT table_name FROM information_schema.tables WHERE table_schema=?',(live_schema,)).fetchall()}
    try:
        for table in tables:
            if table not in existing:
                if allow_missing_new and table not in legacy:
                    continue
                raise SchemaMismatch(f'Missing required table: {table}')
            expected = _pg_signature(db,temp_schema,prefix+table,prefix)
            actual = _pg_signature(db,live_schema,table)
            for column,value in expected[0].items():
                if actual[0].get(column)!=value:
                    raise SchemaMismatch(f'Incompatible column: {table}.{column}')
            if not expected[1].issubset(actual[1]):
                raise SchemaMismatch(f'Incompatible constraints: {table}')
            required = {v for v in expected[2] if v[0]} if allow_missing_indexes else expected[2]
            if not required.issubset(actual[2]):
                raise SchemaMismatch(f'Incompatible indexes: {table}')
    finally:
        # Reverse dependency order; no CASCADE touches user tables.
        for table in reversed(tables):
            db.execute(f'DROP TABLE {temp_schema}.{prefix}{table}')
