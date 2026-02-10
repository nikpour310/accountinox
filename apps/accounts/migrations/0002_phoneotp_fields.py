from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='phoneotp',
            name='otp_hmac',
            field=models.CharField(blank=True, max_length=256, null=True),
        ),
        migrations.AddField(
            model_name='phoneotp',
            name='last_sent_at',
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
        migrations.AddField(
            model_name='phoneotp',
            name='locked_until',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='phoneotp',
            name='phone',
            field=models.CharField(max_length=32, unique=True),
        ),
    ]
