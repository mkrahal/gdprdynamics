# -*- coding: utf-8 -*-
# Generated by Django 1.11.9 on 2018-03-20 21:24
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('installer', '0005_installtracker_initial_import'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='installtracker',
            name='initial_import',
        ),
        migrations.AddField(
            model_name='shopdeatz',
            name='initial_import',
            field=models.BooleanField(default=False),
        ),
    ]