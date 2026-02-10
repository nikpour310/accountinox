from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name='SiteSettings',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('site_name', models.CharField(default='Accountinox', max_length=150)),
                ('logo', models.ImageField(blank=True, null=True, upload_to='logos/')),
                ('primary_color', models.CharField(default='#1ABBC8', max_length=7)),
                ('secondary_color', models.CharField(default='#0468BD', max_length=7)),
                ('accent_color', models.CharField(default='#45E2CC', max_length=7)),
                ('tailwind_mode', models.CharField(choices=(('cdn', 'cdn'), ('local', 'local')), default='cdn', max_length=10)),
                ('enamad_html', models.TextField(blank=True, default='')),
                ('sms_provider', models.CharField(blank=True, default='console', max_length=100)),
                ('otp_enabled', models.BooleanField(default=True)),
                ('otp_for_sensitive', models.BooleanField(default=False)),
                ('otp_expiry_seconds', models.IntegerField(default=300)),
                ('otp_max_attempts', models.IntegerField(default=5)),
                ('otp_resend_cooldown', models.IntegerField(default=60)),
                ('payment_gateway', models.CharField(blank=True, default='zarinpal', max_length=50)),
                ('chat_mode', models.CharField(choices=(('ws', 'ws'), ('poll', 'poll')), default='poll', max_length=10)),
            ],
        ),
        migrations.CreateModel(
            name='GlobalFAQ',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('question', models.CharField(max_length=255)),
                ('answer', models.TextField()),
                ('ordering', models.IntegerField(default=0)),
            ],
            options={
                'ordering': ['ordering'],
            },
        ),
    ]
