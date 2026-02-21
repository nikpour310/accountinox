from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('shop', '0015_order_subtotal_amount_order_vat_amount_and_more'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='cartitem',
            name='customer_password',
        ),
        migrations.RemoveField(
            model_name='orderitem',
            name='customer_password',
        ),
    ]
