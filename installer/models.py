# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models

# Create your models here.
class ShopDeatz(models.Model):
    shop_url = models.CharField(max_length=500)  # <shopname>.myshopify.com
    auth_token = models.CharField(max_length=500)  # token is used to issue commands on behalf of a shop
    initial_import = models.BooleanField(default=False)
    last_import_datetime = models.DateTimeField(default=None, null=True, blank=True)
    download_key = models.CharField(max_length=500)  # user unique  key for exporting GDPR logs
    charge_id = models.CharField(max_length=500)
    shop_name = models.CharField(max_length=500)
    total_exports = models.IntegerField(default=0)
    last_exportdatetime = models.DateTimeField(default=None, null=True, blank=True)
    last_partner_change_datetime = models.DateTimeField(default=None, null=True, blank=True) # code is in daboard.views.initial_setup()

    def __str__(self):
        return self.shop_url

class InstallTracker(models.Model):
    shop_url = models.CharField(max_length=500)  # <shopname>.myshopify.com
    auth_token = models.CharField(max_length=500)  # token is used to issue commands on behalf of a shop
    install_date = models.DateTimeField(default=None, null=True, blank=True) # Format: '%m/%d/%Y %H:%M:%S'
    uninstall_date = models.DateTimeField(default=None, null=True, blank=True) # Format: '%m/%d/%Y %H:%M:%S'
    db_purge = models.CharField(max_length=500, default='-')  # mysql DB purge flag. If this is set to pending installer.tasks.
    uninstaller_email = models.CharField(max_length=500, default='-')

    def __str__(self):
        return self.shop_url
