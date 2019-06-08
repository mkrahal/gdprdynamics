# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models

# Create your models here.
class RemovalConfirmationCodes(models.Model):
    removal_request_email = models.CharField(max_length=500)
    confirmation_code = models.CharField(max_length=500)

class PopUpLanguageSupport(models.Model):
    language = models.CharField(max_length=500) 
    consent_line1 = models.CharField(max_length=500) 
    consent_line2 = models.CharField(max_length=500)  
    consent_line3a = models.CharField(max_length=500)
    duration_wrapper1 = models.CharField(max_length=500)
    duration_wrapper2 = models.CharField(max_length=500)
    duration_undetermined = models.CharField(max_length=500)
    consent_line3c = models.CharField(max_length=500)
    consent_line3d = models.CharField(max_length=500)
    consent_line3e = models.CharField(max_length=500)
    consent_line4a = models.CharField(max_length=500)
    consent_line4b = models.CharField(max_length=500)
    consent_line5 = models.CharField(max_length=500)
    consent_line6 = models.CharField(max_length=500)
    consent_line7 = models.CharField(max_length=500)
    datareq_line1 = models.CharField(max_length=500)
    datareq_line2 = models.CharField(max_length=500)
    datareq_line3 = models.CharField(max_length=500)
    datareq_line4 = models.CharField(max_length=500)
    datareq_line5 = models.CharField(max_length=500)
    datareq_line6 = models.CharField(max_length=500)
    partners_line1 = models.CharField(max_length=500)
    partners_line2 = models.CharField(max_length=500)
    partners_line3 = models.CharField(max_length=500)
    button_action_decline = models.CharField(max_length=500)
    button_action_wrongrequest = models.CharField(max_length=500)
    button_action_submit = models.CharField(max_length=500)
    tabtitle1 = models.CharField(max_length=500)
    tabtitle2 = models.CharField(max_length=500)
    tabtitle3 = models.CharField(max_length=500)
    tabtitle4 = models.CharField(max_length=500)


class RemovalQueue(models.Model):
    shop_url = models.CharField(max_length=500)
    customer_id = models.CharField(max_length=500)
    last_order_id = models.CharField(max_length=500)
    last_order_date = models.DateTimeField()
    removal_request_date = models.DateTimeField()
    removal_request_email = models.CharField(max_length=500)

