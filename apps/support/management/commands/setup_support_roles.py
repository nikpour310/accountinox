from django.core.management.base import BaseCommand

from apps.support.roles import ensure_support_roles


class Command(BaseCommand):
    help = 'Create/update role groups for Content Admin, Support Agent, CRM Admin, Owner.'

    def handle(self, *args, **options):
        summary = ensure_support_roles()
        groups = ', '.join(sorted(set(summary['groups'])))
        self.stdout.write(self.style.SUCCESS(f'Roles synced: {groups}'))
        missing = summary.get('missing_permissions') or []
        if missing:
            self.stdout.write(
                self.style.WARNING(
                    'Missing permissions (skipped): ' + ', '.join(sorted(set(missing)))
                )
            )
