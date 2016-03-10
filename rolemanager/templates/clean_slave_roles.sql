/* {{title}} */


/*******************************************************************************************/
/*****************   remove postgres user and role  ************************************/
/*******************************************************************************************/
\connect postgres

/*-----------------------------remove users ------------------------------------------------------*/
{% for user in removed_users %}
DROP ROLE IF EXISTS "{{ user.name }}";
{% endfor %}

{% for user in users %}
DROP ROLE IF EXISTS "{{ user.name }}";
{% endfor %}

/*-----------------------------remove roles ------------------------------------------------------*/
{% for role in removed_roles %}
DROP ROLE IF EXISTS "{{ role.name }}";
{% endfor %}

{% for role in roles %}
DROP ROLE IF EXISTS "{{ role.name }}";
{% endfor %}


/*******************************************************************************************/
/*****************   remove geoserver user and role*************************************/
/*******************************************************************************************/

\connect kmi

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

