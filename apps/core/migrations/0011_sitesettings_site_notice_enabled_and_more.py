from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0010_sitesettings_terms_privacy_timestamps'),
    ]

    operations = [
        migrations.AddField(
            model_name='sitesettings',
            name='site_notice_enabled',
            field=models.BooleanField(
                default=False,
                help_text='در صورت فعال بودن، نوار اطلاعیه در تمام صفحات سایت نمایش داده می‌شود.',
                verbose_name='فعال‌سازی اطلاعیه سراسری',
            ),
        ),
        migrations.AddField(
            model_name='sitesettings',
            name='site_notice_text',
            field=models.CharField(
                blank=True,
                default='',
                help_text='متنی که در نوار قرمز بالای سایت نمایش داده می‌شود.',
                max_length=300,
                verbose_name='متن اطلاعیه سراسری',
            ),
        ),
    ]
