# Generated by Django 4.2.14 on 2024-08-03 12:03

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rest', '0002_job_profile'),
    ]

    operations = [
        migrations.AlterField(
            model_name='user',
            name='rt_expire',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
