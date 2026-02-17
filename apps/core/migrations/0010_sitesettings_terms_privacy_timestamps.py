from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0009_add_terms_privacy'),
    ]

    operations = [
        migrations.AddField(
            model_name='sitesettings',
            name='terms_updated',
            field=models.DateTimeField(blank=True, null=True, verbose_name='تاریخ به\'روزرسانی شرایط'),
        ),
        migrations.AddField(
            model_name='sitesettings',
            name='privacy_updated',
            field=models.DateTimeField(blank=True, null=True, verbose_name='تاریخ به\'روزرسانی حریم خصوصی'),
        ),
    ]
