# -*- coding: utf-8 -*-
# Generated by Django 1.11.9 on 2018-03-26 20:55
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0009_auto_20180318_2022'),
    ]

    operations = [
        migrations.CreateModel(
            name='AdvancedSettings',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('shop_url', models.CharField(max_length=300)),
                ('custom_consent_text', models.CharField(default='', max_length=300)),
                ('unknown_marketing_list', models.CharField(default='-', max_length=500)),
            ],
        ),
    ]