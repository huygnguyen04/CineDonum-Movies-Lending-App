# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('movies', '0024_auto_20250414_0813'),
    ]

    operations = [
        migrations.AddField(
            model_name='accessrequest',
            name='appeal_message',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='accessrequest',
            name='under_appeal',
            field=models.BooleanField(default=False),
        ),
    ] 