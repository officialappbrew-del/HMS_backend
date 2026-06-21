-- Create extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Create public schema if not exists
CREATE SCHEMA IF NOT EXISTS public;

-- Set search path
SET search_path TO public;

-- Create function to create tenant schema
CREATE OR REPLACE FUNCTION create_tenant_schema(schema_name text)
RETURNS void AS $$
BEGIN
    EXECUTE format('CREATE SCHEMA IF NOT EXISTS %I', schema_name);
END;
$$ LANGUAGE plpgsql;

-- Create function to drop tenant schema
CREATE OR REPLACE FUNCTION drop_tenant_schema(schema_name text)
RETURNS void AS $$
BEGIN
    EXECUTE format('DROP SCHEMA IF EXISTS %I CASCADE', schema_name);
END;
$$ LANGUAGE plpgsql;

-- Create function to list all schemas
CREATE OR REPLACE FUNCTION list_schemas()
RETURNS TABLE(schema_name text) AS $$
BEGIN
    RETURN QUERY
    SELECT n.nspname::text
    FROM pg_catalog.pg_namespace n
    WHERE n.nspname !~ '^pg_' 
    AND n.nspname <> 'information_schema'
    ORDER BY n.nspname;
END;
$$ LANGUAGE plpgsql;