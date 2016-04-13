/* {{title}} */


/*******************************************************************************************/
/*****************   update the postgres user and role  ************************************/
/*******************************************************************************************/
\connect postgres

/*-----------------------------remove roles ------------------------------------------------------*/
/* Remove Postgres roles for each removed role */
{% for role in removed_roles %}
DROP ROLE IF EXISTS "{{ role.name }}";
{% endfor %}

/* Remove users from postgres role for each removed user  */
{% for user in removed_users %}
DROP ROLE IF EXISTS "{{ user.name }}";
{% endfor %}

/*-----------------------------update roles  -----------------------------------------------------*/
/* Create Postgres roles for each access group (including new and unchanged access group), with empty membership */
{% for role in roles %}
DO 
$$BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='{{ role.name }}') THEN
        CREATE ROLE "{{ role.name }}";
    END IF;
    DELETE FROM pg_auth_members WHERE roleid=(SELECT oid FROM pg_roles p WHERE p.rolname='{{ role.name }}');
END$$;
{% endfor %}

/* Create Postgres roles for each  AD user (including new, updated and unchanged user), wire them up to access groups */
{% for user in users %}
DO 
$$BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='{{ user.name }}') THEN
        CREATE ROLE "{{ user.name }}" WITH LOGIN INHERIT;
    END IF;
    {% for role_name in user.applied_roles %}{% if role_name not in user.latest_roles %}REVOKE "{{role_name}}" FROM "{{user.name}}";
    {% endif %}{% endfor %}
    {% for role_name in user.latest_roles %}GRANT "{{ role_name }}" TO "{{ user.name }}";
    {% endfor %}
END$$;
{% endfor %}

/*******************************************************************************************/
/*****************   update the geoserver user and role*************************************/
/*******************************************************************************************/
\connect kmi

/* Set up schema role mapping */
{% for role in roles %}
DO
$$BEGIN
    CREATE SCHEMA IF NOT EXISTS {{ role.name }}; 
    GRANT USAGE ON SCHEMA {{ role.name }} TO {{ role.name }}, domain_admins; 
    GRANT SELECT ON ALL TABLES IN SCHEMA {{ role.name }} TO {{ role.name }}, domain_admins;
    ALTER DEFAULT PRIVILEGES IN SCHEMA {{ role.name }} GRANT SELECT ON TABLES TO {{ role.name }}, domain_admins;
END$$;
{% endfor %}

/*-----------------------------remove geo server roles ane users ----------------------------------*/
/* Remove users and user_roles for removed user*/
{% for user in removed_users %}
DELETE FROM gs_auth.user_roles WHERE username = '{{ user.name }}';
DELETE FROM gs_auth.users WHERE name = '{{user.name}}';
{% endfor %}

/* Remove GeoServer auth records for each removed access group (if necessary) */
{% for role in removed_roles %}
DELETE FROM gs_auth.user_roles WHERE rolename = '{{ role.name }}';
DELETE FROM gs_auth.roles WHERE name='{{ role.name }}');
{% endfor %}

/*-----------------------------update geo server roles --------------------------------------------*/
/* Create GeoServer roles for each access group (if necessary) */
{% for role in roles %}
INSERT INTO gs_auth.roles (name, parent)
    SELECT '{{ role.name }}', NULL
    WHERE NOT EXISTS (SELECT 1 FROM gs_auth.roles WHERE name='{{ role.name }}');
{% endfor %}
/*-----------------------------update geo server users ---------------------------------------------*/
/* Create GeoServer auth users for each AD user (if necessary), wire them up to access groups */
{% for user in users %}
DO
$$BEGIN
    IF EXISTS (SELECT 1 FROM gs_auth.users WHERE name='{{user.name}}') THEN
        UPDATE gs_auth.users SET password='empty:', enabled='Y' WHERE name='{{ user.name }}';
    ELSE
        INSERT INTO gs_auth.users (name, password, enabled) VALUES ('{{ user.name }}', 'empty:', 'Y');
    END IF;
    DELETE FROM gs_auth.user_roles WHERE username = '{{user.name}}';
    {% for role_name in user.latest_roles %}INSERT INTO gs_auth.user_roles (username, rolename) VALUES ('{{ user.name }}', '{{ role_name }}');
    {% endfor %}
END$$;
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

