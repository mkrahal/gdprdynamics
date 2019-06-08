# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.shortcuts import render
from installer.models import ShopDeatz
from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpResponseForbidden
from dashboard.models import ShopCustomizations, FontMap, ShopMarketingServices, KnownPartnersServiceDetails, ShopSettings, AdvancedSettings

# Create your views here.

# All this view needs to do is to return (render) the ScriptTag's source JS
def scripttagsrc1(request): 
    print 'scriptsrc.views()'

    # Get the name of the current shop
    # use request.GET['shop'] as shop_url is passed with the <GET> request
    try:
        shop_url = request.GET['shop']
        #access_token = request.GET['access_token']
    except Exception:
        shop_url = 'nostoreError'        # Block to handle Multivalue error
        #access_token = 'notokenError'    # Block to handle Multivalue error

    #print access_token
    # Add switch to check if store exists in our registered store's DB. In case store does not exist in our DB, return HTTPBadRequest
    # if the store exists, it will make one further check to verify that the access token passed for the store corresponds to the one
    # we have in our DB. If it does it means that the request is legitimately comming from the store, if they don't match, then someone
    # could be attempting to forge fake sessionsi using the shop_url to access data (but he does not have the auth token)
    try:
        # Verify that shop_url exists in DB,
        ShopDeatzInst = ShopDeatz.objects.get(shop_url=str(shop_url))
 
    # This Exception will help to stop Apache from bugging out in cases where you are making DB and API calls using non existant stores
    # i.e, when the db.sql is reinitialized while a store still has the app installed but is not present in local DB
    except ObjectDoesNotExist:
        print 'Error: %s shop has app installed but is not present in the DB' % (shop_url)
        return HttpResponseForbidden()

    ##########################################################################################################
    # View Code
    #########################################################################################################
 
    # Execute this code to return the JS only if the above two tests were passed

    # Create model instances to fetch styles from dashboard.models.ShopCustomizations to render templates
    ShopCustInst = ShopCustomizations.objects.get(shop_url=shop_url)
    FontMapInst = FontMap.objects.get(font_var_name=ShopCustInst.font_type)  # Create an instance of models.FontMap to lookup font css string
    
    # Convert sleep time to milliseconds, it needs to be passed in milli-seconds to JavaScript 
    time_delay_millisec = ShopCustInst.time_delay * 1000      

    # Create instance of ShopSettings to fetch settings and pass them for rendering
    ShopSettingsInst = ShopSettings.objects.get(shop_url=shop_url)

    # Create an instance of ShopMarketingServices model to fetch data from DB
    ShopMarketingInst = ShopMarketingServices.objects.get(shop_url=shop_url) 
    
    # Make a list of unknown partners for rendering
    unknownpartners_list = ShopMarketingInst.unknown_services_list.replace('"', '')
    unknownpartners_list = unknownpartners_list.split(',')
    # if the list of unknowns only contains the default value, then return an empty list so nothing is rendered when its looped in the template 
    if len(unknownpartners_list) == 1 and unknownpartners_list[0] == '-':
        unknownpartners_list = []

    # Make a dictionnary of partners key=> Partner Name, value=> Partner link (for rendering partners scroll bar)
    partners_dict = {}
    ShopPartnersList = ShopMarketingInst.known_services_list_quoted.replace('"', '')
    ShopPartnersList = ShopPartnersList.split(',')

    #print ShopPartnersList

    for partner_lookup_var in ShopPartnersList:
        #print partner_lookup_var
        # Lookup the partner and extract his details for rendering from the DB
        PartnerInst = KnownPartnersServiceDetails.objects.get(service_lookup_var=partner_lookup_var)
        partners_dict[PartnerInst.service_name] = PartnerInst.service_link

    # Create an instance of Advanced settigs to get extra marketing partners
    AdvancedSettingsInst = AdvancedSettings.objects.get(shop_url=shop_url)
    # Make a list of unknown partners for rendering
    unknownmarketing_list = AdvancedSettingsInst.unknown_marketing_list.replace('"', '')
    unknownmarketing_list = unknownmarketing_list.split(',')
    # if the list of unknowns only contains the default value, then return an empty list so nothing is rendered when its looped in the template 
    if len(unknownmarketing_list) == 1 and unknownmarketing_list[0] == '-':
        unknownmarketing_list = []


    context = {
               'background_color': ShopCustInst.background_color,
               'text_color': ShopCustInst.text_color,
               'secondary_text_color': ShopCustInst.secondary_text_color,
               'active_tab_text_color': ShopCustInst.active_tab_text_color,
               'accept_color': ShopCustInst.accept_color,
               'decline_color': ShopCustInst.decline_color,
               'font_type': FontMapInst.font_css_string,
               'font_link_name': FontMapInst.font_linkrel_name,
               'font_size': ShopCustInst.font_size,
               'behaviour': ShopCustInst.widget_behaviour,
               'time_delay': time_delay_millisec,
               'partners_dict': partners_dict,
               'unknownpartners_list': unknownpartners_list,
               'third_country': ShopSettingsInst.third_country,
               'shop_url': shop_url,
               'unknownmarketing_list': unknownmarketing_list,
              }

    # Switch to tell django which template to use when rendering
    #print "script returned"
    #print ShopCustInst.active_template

    # MY TESTINGSCRIPT TAGS IN JERRYS JERSEY STORE
    if (shop_url == 'jerrysjerseystore.myshopify.com') and (str(ShopCustInst.widget_behaviour).lower() == 'explicit'):
        return render(request, 'scripttag_src/JS_popup_template6min.html', context)

    elif (shop_url == 'jerrysjerseystore.myshopify.com') and str(ShopCustInst.widget_behaviour).lower() == 'default': 
        return render(request, 'scripttag_src/JS_popup_template5min.html', context)

    # CLIENT JS SCRIPT TAGS (PRODUCTION)
    elif (shop_url != 'jerrysjerseystore.myshopify.com') and (str(ShopCustInst.widget_behaviour).lower() == 'explicit'):
        #return render(request, 'scripttag_src/JS_popup_template6.html', context)
        return render(request, 'scripttag_src/JS_popup_template6min.html', context)

    else:
        #return render(request, 'scripttag_src/JS_popup_template5.html', context)
        return render(request, 'scripttag_src/JS_popup_template5min.html', context)

