from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0003_populate_last_sent_default'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='phoneotp',
            name='otp_hash',
        ),
        migrations.AlterField(
            model_name='phoneotp',
            name='created_at',
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
        migrations.AlterField(
            model_name='phoneotp',
            name='last_sent_at',
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
    ]
