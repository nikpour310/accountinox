from django.db import migrations, models
import django.utils.timezone


def set_last_sent(apps, schema_editor):
    PhoneOTP = apps.get_model('accounts', 'PhoneOTP')
    now = django.utils.timezone.now()
    for obj in PhoneOTP.objects.all():
        if not obj.last_sent_at:
            obj.last_sent_at = obj.created_at or now
            obj.save()


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0002_phoneotp_fields'),
    ]

    operations = [
        migrations.RunPython(set_last_sent, reverse_code=migrations.RunPython.noop),
    ]
