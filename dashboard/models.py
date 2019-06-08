# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models

# Create your models here.
class TemplateDefaults(models.Model):
    template_name = models.CharField(max_length=100)
    background_color = models.CharField(max_length=100)
    text_color = models.CharField(max_length=100)
    secondary_text_color = models.CharField(max_length=100)
    active_tab_text_color = models.CharField(max_length=100)
    accept_color = models.CharField(max_length=100)
    decline_color = models.CharField(max_length=100)
    font_type = models.CharField(max_length=100)
    font_size =  models.CharField(max_length=100)  # 'small', 'normal', 'large'
    time_delay = models.IntegerField(default=0)
    widget_behaviour = models.CharField(max_length=100, default='Default')

    def __str__(self):
        return self.template_name


class FontMap(models.Model):
    font_var_name = models.CharField(max_length=100)
    font_linkrel_name = models.CharField(max_length=100)
    font_css_string =  models.CharField(max_length=100)
 

class ShopCustomizations(models.Model):
    shop_url = models.CharField(max_length=300)
    active_template = models.CharField(max_length=100)
    background_color = models.CharField(max_length=100)
    text_color = models.CharField(max_length=100)
    secondary_text_color = models.CharField(max_length=100)
    active_tab_text_color = models.CharField(max_length=100)
    accept_color = models.CharField(max_length=100)
    decline_color = models.CharField(max_length=100)
    font_type = models.CharField(max_length=100)
    font_size =  models.CharField(max_length=100)  # 'small', 'normal', 'large'
    time_delay = models.IntegerField(default=0)
    widget_behaviour = models.CharField(max_length=100, default='Default')

class ShopSettings(models.Model):
    shop_url = models.CharField(max_length=300)
    datapurpose_shipping = models.BooleanField(default=True)
    datapurpose_payproc = models.BooleanField(default=True)
    datapurpose_emarketing = models.BooleanField(default=True)
    datapurpose_retar = models.BooleanField(default=True)
    storage_duration = models.IntegerField(default=0)
    data_sharing = models.CharField(max_length=100, default='-')
    third_country = models.CharField(max_length=100, default='-')
    esp = models.CharField(max_length=100, default='-')
    subscriber_list_id = models.CharField(max_length=500, default='-')

class ShopMarketingServices(models.Model):
    shop_url = models.CharField(max_length=300)
    # comma seperated list of check mark, marketing services the one below is for JS use ONLY
    known_services_list_quoted = models.CharField(max_length=500, default='"shopify","gdpr"')

    # comma seperated list of third entities services (a.k.a shipping) for DJANGO use
    unknown_services_list =  models.CharField(max_length=500, default='-')
    # comma seperated list of check mark, marketing services the one below is for DJANGO use
    known_services_list_unquoted = models.CharField(max_length=500, default='shopify,gdpr')


# This will be called PartnerServiceDetails because it includes Shopify, GDPR APP, MailChimp and marketing services
class KnownPartnersServiceDetails(models.Model):
    service_lookup_var = models.CharField(max_length=100)
    service_name = models.CharField(max_length=100)
    service_link = models.CharField(max_length=500, default='-')


class ESPCredentials(models.Model):
    shop_url = models.CharField(max_length=300)
    esp_username = models.CharField(max_length=500, default='-')
    esp_API_key = models.CharField(max_length=500, default='-') 
    esp_api_endpoint_url = models.CharField(max_length=500, default='-') 
    esp_data_center = models.CharField(max_length=500, default='-') 
    configured_ESP = models.CharField(max_length=500, default='-') 

class AdvancedSettings(models.Model):
    shop_url = models.CharField(max_length=300)
    custom_consent_text = models.CharField(max_length=300, default='')
    unknown_marketing_list =  models.CharField(max_length=500, default='-') # put advanced settings services here seperated by a comma se we
    ip_filtering_active = models.BooleanField(default=True)
 
