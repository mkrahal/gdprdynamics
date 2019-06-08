# -*- coding: utf-8 -*-
# Generated by Django 1.11.9 on 2018-04-17 19:41
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('gdpr', '0005_auto_20180415_1459'),
    ]

    operations = [
        migrations.CreateModel(
            name='RemovalQueue',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('shop_url', models.CharField(max_length=500)),
                ('customer_id', models.CharField(max_length=500)),
                ('last_order_id', models.CharField(max_length=500)),
                ('last_order_date', models.CharField(max_length=500)),
                ('removal_request_date', models.CharField(max_length=500)),
                ('removal_request_email', models.CharField(max_length=500)),
            ],
        ),
    ]
