from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0008_sitesettings_order_email_footer_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='sitesettings',
            name='terms_html',
            field=models.TextField(blank=True, default='', help_text='متن شرایط و قوانین سایت — HTML مجاز است', verbose_name='متن شرایط و قوانین (HTML)'),
        ),
        migrations.AddField(
            model_name='sitesettings',
            name='privacy_html',
            field=models.TextField(blank=True, default='', help_text='متن سیاست حریم خصوصی — HTML مجاز است', verbose_name='متن سیاست حریم خصوصی (HTML)'),
        ),
    ]
