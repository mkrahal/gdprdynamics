# -*- coding: utf-8 -*-
# Generated by Django 1.11.9 on 2018-03-30 22:49
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('installer', '0009_shopdeatz_charge_id'),
    ]

    operations = [
        migrations.AddField(
            model_name='installtracker',
            name='db_purge',
            field=models.CharField(default='-', max_length=500),
        ),
    ]