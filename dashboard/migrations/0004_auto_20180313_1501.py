# -*- coding: utf-8 -*-
# Generated by Django 1.11.9 on 2018-03-13 15:01
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0003_fontmap'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='fontmap',
            name='fonr_css_string',
        ),
        migrations.AddField(
            model_name='fontmap',
            name='font_css_string',
            field=models.CharField(default='', max_length=100),
            preserve_default=False,
        ),
    ]
