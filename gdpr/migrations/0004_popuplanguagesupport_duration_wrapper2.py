# -*- coding: utf-8 -*-
# Generated by Django 1.11.9 on 2018-03-27 19:43
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('gdpr', '0003_auto_20180327_1940'),
    ]

    operations = [
        migrations.AddField(
            model_name='popuplanguagesupport',
            name='duration_wrapper2',
            field=models.CharField(default='', max_length=500),
            preserve_default=False,
        ),
    ]