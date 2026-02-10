from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Profile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('phone', models.CharField(blank=True, max_length=32, null=True)),
                ('user', models.OneToOneField(on_delete=models.deletion.CASCADE, to='auth.user')),
            ],
        ),
        migrations.CreateModel(
            name='PhoneOTP',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('phone', models.CharField(max_length=32)),
                ('otp_hash', models.CharField(max_length=128)),
                ('created_at', models.DateTimeField()),
                ('attempts', models.IntegerField(default=0)),
            ],
        ),
    ]
