import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0011_sitesettings_site_notice_enabled_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name='sitesettings',
            name='privacy_updated',
            field=models.DateTimeField(blank=True, null=True, verbose_name='تاریخ به\u200cروزرسانی حریم خصوصی'),
        ),
        migrations.AlterField(
            model_name='sitesettings',
            name='terms_updated',
            field=models.DateTimeField(blank=True, null=True, verbose_name='تاریخ به\u200cروزرسانی شرایط'),
        ),
        migrations.CreateModel(
            name='SiteBackup',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('file_name', models.CharField(max_length=255, unique=True, verbose_name='نام فایل بکاپ')),
                ('size_bytes', models.BigIntegerField(default=0, verbose_name='حجم بکاپ (بایت)')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='تاریخ ساخت')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='site_backups', to=settings.AUTH_USER_MODEL, verbose_name='ایجاد شده توسط')),
            ],
            options={
                'verbose_name': 'بکاپ سایت',
                'verbose_name_plural': 'بکاپ‌های سایت',
                'ordering': ['-created_at'],
            },
        ),
    ]
