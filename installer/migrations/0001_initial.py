# -*- coding: utf-8 -*-
# Generated by Django 1.11.9 on 2018-01-28 03:49
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='ShopDeatz',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('shop_url', models.CharField(max_length=500)),
                ('auth_token', models.CharField(max_length=500)),
            ],
        ),
    ]
