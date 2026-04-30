from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('myapp', '0015_order_cancellation_reason'),
    ]

    operations = [
        migrations.AddField(
            model_name='advertisement',
            name='stock_quantity',
            field=models.PositiveIntegerField(default=0),
        ),
    ]
