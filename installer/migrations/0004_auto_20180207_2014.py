# -*- coding: utf-8 -*-
# Generated by Django 1.11.9 on 2018-02-07 20:14
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('installer', '0003_auto_20180207_1958'),
    ]

    operations = [
        migrations.AlterField(
            model_name='installtracker',
            name='install_date',
            field=models.DateTimeField(blank=True, default=None, null=True),
        ),
        migrations.AlterField(
            model_name='installtracker',
            name='uninstall_date',
            field=models.DateTimeField(blank=True, default=None, null=True),
        ),
    ]
