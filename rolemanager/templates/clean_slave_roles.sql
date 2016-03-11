/* {{title}} */


/*******************************************************************************************/
/*****************   remove postgres user and role  ************************************/
/*******************************************************************************************/
\connect postgres

/*-----------------------------remove users ------------------------------------------------------*/
{% for user in removed_users %}
DO
$$BEGIN
    IF '{{user.name}}' != current_role AND  EXISTS(SELECT 1 FROM pg_roles WHERE rolname = '{{user.name}}') THEN
        DROP ROLE IF EXISTS "{{ user.name }}";
    END IF;
END$$;
{% endfor %}

{% for user in users %}
DO
$$BEGIN
    IF '{{user.name}}' != current_role AND  EXISTS(SELECT 1 FROM pg_roles WHERE rolname = '{{user.name}}') THEN
        DROP ROLE IF EXISTS "{{ user.name }}";
    END IF;
END$$;
{% endfor %}

\connect kmi
/*-----------------------------remove roles ------------------------------------------------------*/
{% for role in removed_roles %}
DO
$$BEGIN
    IF EXISTS(SELECT 1 FROM pg_namespace WHERE nspname = '{{role.name}}') THEN
        IF '{{role.name}}' != current_role AND EXISTS(SELECT 1 FROM pg_roles WHERE rolname = '{{role.name}}') THEN
            REVOKE ALL ON SCHEMA {{ role.name }} FROM {{ role.name }}; 
            REVOKE ALL ON ALL TABLES IN SCHEMA {{ role.name }} FROM {{ role.name }};
            ALTER DEFAULT PRIVILEGES IN SCHEMA {{ role.name }} REVOKE SELECT ON TABLES FROM {{ role.name }};
        END IF;
        IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname = 'domain_admins') THEN
            REVOKE ALL ON SCHEMA {{ role.name }} FROM domain_admins; 
            REVOKE ALL ON ALL TABLES IN SCHEMA {{ role.name }} FROM domain_admins;
            ALTER DEFAULT PRIVILEGES IN SCHEMA {{ role.name }} REVOKE SELECT ON TABLES FROM domain_admins;
        END IF;
    END IF;
END$$;
{% endfor %}

{% for role in roles %}
DO
$$BEGIN
    IF EXISTS(SELECT 1 FROM pg_namespace WHERE nspname = '{{role.name}}') THEN
        IF '{{role.name}}' != current_role AND EXISTS(SELECT 1 FROM pg_roles WHERE rolname = '{{role.name}}') THEN
            REVOKE ALL ON SCHEMA {{ role.name }} FROM {{ role.name }}; 
            REVOKE ALL ON ALL TABLES IN SCHEMA {{ role.name }} FROM {{ role.name }};
            ALTER DEFAULT PRIVILEGES IN SCHEMA {{ role.name }} REVOKE SELECT ON TABLES FROM {{ role.name }};
        END IF;
        IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname = 'domain_admins') THEN
            REVOKE ALL ON SCHEMA {{ role.name }} FROM domain_admins; 
            REVOKE ALL ON ALL TABLES IN SCHEMA {{ role.name }} FROM domain_admins;
            ALTER DEFAULT PRIVILEGES IN SCHEMA {{ role.name }} REVOKE SELECT ON TABLES FROM domain_admins;
        END IF;
    END IF;
END$$;
{% endfor %}

{% for role in removed_roles %}
DO
$$BEGIN
    IF '{{role.name}}' != current_role AND EXISTS(SELECT 1 FROM pg_roles WHERE rolname = '{{role.name}}') THEN
        DROP ROLE IF EXISTS "{{ role.name }}";
    END IF;
END$$;
{% endfor %}

{% for role in roles %}
DO
$$BEGIN
    IF '{{role.name}}' != current_role AND EXISTS(SELECT 1 FROM pg_roles WHERE rolname = '{{role.name}}') THEN
        DROP ROLE IF EXISTS "{{ role.name }}";
    END IF;
END$$;
{% endfor %}

/*-----------------------------drop not required schmeas ------------------------------------------------------*/
DO
$$BEGIN
    IF EXISTS(SELECT 1 FROM pg_namespace WHERE nspname = 'domain_admins') THEN
        DROP SCHEMA IF EXISTS domain_admins;
    END IF;
END$$;
DO
$$BEGIN
    IF EXISTS(SELECT 1 FROM pg_namespace WHERE nspname = 'everyone') THEN
        DROP SCHEMA IF EXISTS everyone;
    END IF;
END$$;

/*******************************************************************************************/
/*****************   remove geoserver user and role*************************************/
/*******************************************************************************************/

/*-----------------------------remove geo server roles ane users ----------------------------------*/
/* Remove users and user_roles for removed user*/
{% for user in removed_users %}
DELETE FROM gs_auth.user_roles WHERE username = '{{ user.name }}';
DELETE FROM gs_auth.users WHERE name = '{{user.name}}';
{% endfor %}

{% for user in users %}
DELETE FROM gs_auth.user_roles WHERE username = '{{ user.name }}';
DELETE FROM gs_auth.users WHERE name = '{{user.name}}';
{% endfor %}

/* Remove GeoServer auth records for each removed access group (if necessary) */
{% for role in removed_roles %}
DELETE FROM gs_auth.user_roles WHERE rolename = '{{ role.name }}';
DELETE FROM gs_auth.roles WHERE name='{{ role.name }}';
{% endfor %}

{% for role in roles %}
DELETE FROM gs_auth.user_roles WHERE rolename = '{{ role.name }}';
DELETE FROM gs_auth.roles WHERE name='{{ role.name }}';
{% endfor %}

/* Manual override for GeoServer "admin" user */
DO
$$BEGIN
    IF NOT EXISTS (SELECT 1 FROM gs_auth.roles WHERE name='NO_ONE') THEN
        INSERT INTO gs_auth.roles (name, parent) VALUES ('NO_ONE',NULL);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM gs_auth.user_roles WHERE username='admin' AND rolename='ADMIN') THEN
        INSERT INTO gs_auth.user_roles (username, rolename) VALUES ('admin', 'ADMIN');
    END IF;
END$$;

