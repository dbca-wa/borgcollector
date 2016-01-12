\connect postgres

/* Create Postgres roles for each access group (if necessary), with empty membership */
{% for role in roles %}DO 
$$BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='{{ role }}') THEN
        CREATE ROLE "{{ role }}" WITH INHERIT;
    END IF;
END$$;
DELETE FROM pg_auth_members WHERE roleid=(SELECT oid FROM pg_roles p WHERE p.rolname='{{ role }}');
{% endfor %}

/* Create Postgres roles for each AD user (if necessary), wire them up to access groups */
{% for user in users %}DO 
$$BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='{{ user.name }}') THEN
        CREATE ROLE "{{ user.name }}" WITH LOGIN;
    END IF;
END$$;
{% for group in user.groups %}GRANT "{{ group }}" TO "{{ user.name }}";
{% endfor %}{% endfor %}

\connect kmi

/* Create GeoServer auth records for each access group (if necessary) */
{% for role in roles %}INSERT INTO gs_auth.roles (name, parent)
    SELECT '{{ role }}', NULL
    WHERE NOT EXISTS (SELECT 1 FROM gs_auth.roles WHERE name='{{ role }}');
{% endfor %}

DO
$$BEGIN
    IF NOT EXISTS (SELECT 1 FROM gs_auth.roles WHERE name='NO_ONE') THEN
        INSERT INTO gs_auth.roles (name, parent) VALUES ('NO_ONE',NULL);
    END IF;
END$$;

/* Delete existing user-role mappings */
DELETE FROM gs_auth.user_roles;


/* Create GeoServer auth records for each AD user (if necessary), wire them up to access groups */
{% for user in users %}UPDATE gs_auth.users SET password='empty:', enabled='Y' WHERE name='{{ user.name }}';
INSERT INTO gs_auth.users (name, password, enabled)
    SELECT '{{ user.name }}', 'empty:', 'Y' 
    WHERE NOT EXISTS (SELECT 1 FROM gs_auth.users WHERE name='{{ user.name }}');
{% for group in user.groups %}INSERT INTO gs_auth.user_roles (username, rolename) VALUES ('{{ user.name }}', '{{ group }}');
{% endfor %}
{% endfor %}

/* Manual override for GeoServer "admin" user */
INSERT INTO gs_auth.user_roles (username, rolename) VALUES ('admin', 'ADMIN');
