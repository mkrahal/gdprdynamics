# -*- coding: utf-8 -*-
# Generated by Django 1.11.9 on 2018-04-15 14:59
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('gdpr', '0004_popuplanguagesupport_duration_wrapper2'),
    ]

    operations = [
        migrations.AddField(
            model_name='popuplanguagesupport',
            name='button_action_decline',
            field=models.CharField(default='', max_length=500),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='popuplanguagesupport',
            name='button_action_submit',
            field=models.CharField(default='', max_length=500),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='popuplanguagesupport',
            name='button_action_wrongrequest',
            field=models.CharField(default='', max_length=500),
            preserve_default=False,
        ),
    ]