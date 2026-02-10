from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0002_alter_sitesettings_options_sitesettings_sms_enabled_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='sitesettings',
            name='brand_wordmark_fa',
            field=models.CharField(blank=True, default='اکانتینوکس', max_length=150),
        ),
    ]
