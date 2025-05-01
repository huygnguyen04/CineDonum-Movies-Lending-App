from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('movies', '0019_fix_profile_date_joined'),
    ]

    operations = [
        migrations.AlterField(
            model_name='profile',
            name='date_joined',
            field=models.DateField(auto_now_add=True, blank=True, null=True, help_text='Date the user joined the Community Library Association'),
        ),
    ] 