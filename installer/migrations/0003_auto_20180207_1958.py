# -*- coding: utf-8 -*-
# Generated by Django 1.11.9 on 2018-02-07 19:58
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('installer', '0002_installtracker'),
    ]

    operations = [
        migrations.AlterField(
            model_name='installtracker',
            name='install_date',
            field=models.DateTimeField(default=None),
        ),
        migrations.AlterField(
            model_name='installtracker',
            name='uninstall_date',
            field=models.DateTimeField(default=None),
        ),
    ]