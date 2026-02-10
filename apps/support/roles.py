from django.contrib.auth.models import Group, Permission

ROLE_CONTENT_ADMIN = 'Content Admin'
ROLE_SUPPORT_AGENT = 'Support Agent'
ROLE_CRM_ADMIN = 'CRM Admin'
ROLE_OWNER = 'Owner'


ROLE_PERMISSION_MAP = {
    ROLE_CONTENT_ADMIN: {
        'blog.add_post',
        'blog.change_post',
        'blog.delete_post',
        'blog.view_post',
        'blog.add_postfaq',
        'blog.change_postfaq',
        'blog.delete_postfaq',
        'blog.view_postfaq',
    },
    ROLE_SUPPORT_AGENT: {
        'support.view_chatsession',
        'support.change_chatsession',
        'support.view_chatmessage',
        'support.add_chatmessage',
        'support.change_chatmessage',
        'support.view_supportpushsubscription',
        'support.add_supportpushsubscription',
        'support.change_supportpushsubscription',
        'support.view_supportoperatorpresence',
    },
    ROLE_CRM_ADMIN: {
        'support.view_supportcontact',
        'support.change_supportcontact',
        'support.can_export_support_contacts',
        'support.view_supportrating',
    },
}


def ensure_support_roles():
    """
    Create/refresh role groups and attach permissions.
    Returns a summary dict for logs/tests.
    """
    summary = {
        'groups': [],
        'missing_permissions': [],
    }

    permissions_by_key = {
        f'{perm.content_type.app_label}.{perm.codename}': perm
        for perm in Permission.objects.select_related('content_type').all()
    }

    for role_name, permission_keys in ROLE_PERMISSION_MAP.items():
        group, _ = Group.objects.get_or_create(name=role_name)
        resolved_permissions = []
        for key in sorted(permission_keys):
            perm = permissions_by_key.get(key)
            if perm is None:
                summary['missing_permissions'].append(key)
                continue
            resolved_permissions.append(perm)
        group.permissions.set(resolved_permissions)
        summary['groups'].append(group.name)

    owner_group, _ = Group.objects.get_or_create(name=ROLE_OWNER)
    owner_group.permissions.set(Permission.objects.all())
    summary['groups'].append(owner_group.name)
    return summary
