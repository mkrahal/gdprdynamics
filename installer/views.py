from django.shortcuts import render, redirect
from django.contrib import messages
from django.core.urlresolvers import reverse
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
import datetime
import shopify
from installer.models import ShopDeatz, InstallTracker
import hashlib, base64, hmac, json
from django.http import HttpResponseForbidden, HttpResponseBadRequest, HttpResponse
from django.core.exceptions import ObjectDoesNotExist
import dashboard
from dashboard.models import TemplateDefaults, ShopCustomizations, ShopSettings, ShopMarketingServices, ESPCredentials, AdvancedSettings
from backendmodules.auditlogger import DataEventLogger
from gdpr.tasks import initial_data_import 
import string
import random


# APP_NAME, APP_PRICE etc... are stored in shopify_settings.py and made available here via the 'from django.conf import settings' import line


def _return_address(request):
    return request.session.get('return_to') or reverse('root_path')


# Function to verify hmacs
def hmac_is_valid(body, secret, hmac_to_verify):
    hash = hmac.new(secret, body, hashlib.sha256)
    hmac_calculated = base64.b64encode(hash.digest())
    return hmac_calculated == hmac_to_verify


# This function activates the INITIAL INSTALLATION recurring charge from finalize() function
def activateRecurringCharge(request):
    print '==> activateRecurringCharge()'
    # Use the charge id that is passed in the GET request to create an instance of your store's data
    charge_id = request.GET.get('charge_id')

    # Create and activate session
    # Add try / Except statement here for double return_url call
    # On the second call ShopDeatz object will have been deleted and will return ObjectNotFound at that point just return the decline_page.html
    
    try:
        ShopDeatzInst = ShopDeatz.objects.get(charge_id=charge_id)
        shop_url = ShopDeatzInst.shop_url
        auth_token = ShopDeatzInst.auth_token
    except ObjectDoesNotExist:
        print 'rendering from except'
        # Return App Charge Declined Page
        shop_url = request.GET.get('shop', False)
        #full_shop_url = 'https://' + shop_url
        context = {
                    'SHOPIFY_API_KEY': settings.SHOPIFY_API_KEY,
                    #'shop_url': full_shop_url,
                    #'apps_link': (full_shop_url + '/admin/apps/')
                  }
        print context
        return render(request, 'installer/decline_page.html', context)

    session = shopify.Session(shop_url, ShopDeatzInst.auth_token)
    shopify.ShopifyResource.activate_session(session)

    print 'Activationg charge for %s' %(shop_url)
    # use the charge_id to find the correct RecurringApplicationCharge within the store's charges
    charge = shopify.RecurringApplicationCharge.find(charge_id)

    # Check the status of the application charge
    # if it is declined then remove the store from our DB to restrict access
    print "Current charge status = %s" %(charge.status)
    if charge.status != 'accepted' and charge.status != 'active':
        print 'Declined Deleting Shop from DB'
        ShopDeatzInst.delete()

        # Return App Charge Declined Page
        full_shop_url = 'https://' + shop_url
        context = {
                    'SHOPIFY_API_KEY': settings.SHOPIFY_API_KEY,
                    'shop_url': full_shop_url,
                    'apps_link': (full_shop_url + '/admin/apps/')
                  }
        print context
        return render(request, 'installer/decline_page.html', context)

    elif charge.status == 'active':
        # redirect to dashboard
        return dashboard.views.index(request)

    # Otherwise if merchant accepted then, activate the charge and finalize the installation 
    else:
        # Activate the charge
        charge.activate()
        final_status = charge.status
        print 'Final charge status %s' %(final_status)
        print 'Finalizing Installation'

        # #############################
        # Finish installation
        # #############################

        # Install Script Tag
        scripttag_return = createScriptTag()
        print scripttag_return

        # Create uinstall webhook (removed during testing phase)
        webhook_return = createUninstallWebHook()
        print webhook_return

        # ###############################
        # CREATE REQUIRED MODELS
        # ###############################
        # Note: Wrap all model creations in try/except statements to make check that you are not adding an entry that already exists
        # double entries bug out the entire code when doing lookups. No need to wrap the ShopDeatz, there is already a try/except check above 

        # Save the same info in models.InstallTracker
        # if an entry for the store exists then update the info of the entry
        try: 
            InstallTrackerInst = InstallTracker.objects.get(shop_url=shop_url)
            install_datetime = datetime.datetime.now()
            InstallTrackerInst.auth_token = auth_token
            InstallTrackerInst.install_date = install_datetime
            InstallTrackerInst.db_purge = '-' 
            InstallTrackerInst.save()
        # otherwise if no entry exists then create one
        except ObjectDoesNotExist:
            InstallTrackerInst = InstallTracker()
            install_datetime = datetime.datetime.now()
            InstallTrackerInst.shop_url = shop_url
            InstallTrackerInst.auth_token = auth_token
            InstallTrackerInst.install_date = install_datetime
            InstallTrackerInst.db_purge = '-' 
            InstallTrackerInst.save()
            print 'Install written in models.InstallTracker'

        # Create Customization Model entry for shop
        try:
            ShopCustomInst =  ShopCustomizations.objects.get(shop_url=shop_url)

        except ObjectDoesNotExist:
            DefaultTemplateInst = TemplateDefaults.objects.get(template_name='retro')
            ShopCustInst = ShopCustomizations()
            ShopCustInst.shop_url = shop_url
            ShopCustInst.active_template = DefaultTemplateInst.template_name
            ShopCustInst.background_color = DefaultTemplateInst.background_color
            ShopCustInst.text_color = DefaultTemplateInst.text_color
            ShopCustInst.secondary_text_color = DefaultTemplateInst.secondary_text_color
            ShopCustInst.active_tab_text_color = DefaultTemplateInst.active_tab_text_color
            ShopCustInst.accept_color = DefaultTemplateInst.accept_color
            ShopCustInst.decline_color = DefaultTemplateInst.decline_color
            ShopCustInst.font_type = DefaultTemplateInst.font_type
            ShopCustInst.font_size = DefaultTemplateInst.font_size
            ShopCustInst.time_delay= DefaultTemplateInst.time_delay
            ShopCustInst.save()

        # Create Shop Settings Model entry for shop
        try:
            ShopSettingsInst = ShopSettings.objects.get(shop_url=shop_url)

        except ObjectDoesNotExist:
            ShopSettingsInst = ShopSettings()
            ShopSettingsInst.shop_url = shop_url
            ShopSettingsInst.save()

        # Create Shop Marketing Services entry for shop
        try:
            ShopMarketingServicesInst = ShopMarketingServices.objects.get(shop_url=shop_url) 

        except ObjectDoesNotExist:
            ShopMarketingServicesInst = ShopMarketingServices()
            ShopMarketingServicesInst.shop_url = shop_url
            ShopMarketingServicesInst.save()
        
        # Create Shop Advanced Settings entry for shop
        try:
            AdvancedSettingsInst = AdvancedSettings.objects.get(shop_url=shop_url) 

        except ObjectDoesNotExist:
            AdvancedSettingsInst = AdvancedSettings()
            AdvancedSettingsInst.shop_url = shop_url
            AdvancedSettingsInst.save()

        # Create Email Service Provider entry in DB for shop
        try:
            ESPInst = ESPCredentials.objects.get(shop_url=shop_url) 

        except ObjectDoesNotExist:
            ESPInst = ESPCredentials()
            ESPInst.shop_url = shop_url
            ESPInst.save()

        #####################################################################
        # MYSQL SETUP
        #####################################################################
        # Check if table already exists in case of re-installs and abandonned upgrades. In these cases a table will already exist and there
        # is no need to re-create one or to launch initial_data_import, doing so would re-write the customers data or append the same data again
        AuditLogInst = DataEventLogger(shop_url)
        table_exists = AuditLogInst.check_table_exists()
        if table_exists == False:
            #####################################################
            # Create MYSQL table Audit Log (Do NOT wrap in try)
            #################################################### 

            AuditLogInst.create_shop_audit_table()
 
            #####################################################
            # Queue Asynchronous Initial Data Import    
            ####################################################
            # This calls the code that we wish to run asynchronously.
            # Basically once the app finishes installing in finalize, we want to immediately let him continue on his way, 
            # while we process imports in the all in the background. The function called below will be sent to the rabbitmq queue and 
            # will wait there for a worker to pick it up and execute the code in the background asynchronously. That we this finalize() 
            # won't have to wait for this process to finish before rendering the finalize page. We can render the user backend and allow 
            # the impot function to finish in its own time. Without locking the flow control.
            initial_data_import.delay(shop_url, auth_token)

        else:
            ShopDeatzInst.initial_import = True
            ShopDeatzInst.last_import_datetime = datetime.datetime.now()
            ShopDeatzInst.save()
            print '%s SQL table exists, table creation and initial_data_import have been skipped' %(shop_url)
            pass

    # You must pass 2 arguements to the EASDK JS, your app's api_key and the FULL path to the store that is installing the app.
    full_shop_url = 'https://' + shop_url
    context = {
                'SHOPIFY_API_KEY': settings.SHOPIFY_API_KEY,
                'shop_url': full_shop_url
          }

    print 'APP INSTALLATION SUCCESSFULLY TERMINATED'
    # Now render the emmbeded home.html template using the context above
    return render(request, 'dashboard/home.html', context)


# Creates and registers Uninstall webhook for the app
def createUninstallWebHook():
    webhook = shopify.Webhook()
    webhook.topic = 'app/uninstalled'
    webhook.address = settings.APP_DOMAINURL + '/webhook/'
    webhook.save()
    return webhook


# Creates and registers initial scripttag
#  The source JS for this script tag should be returned (rendered) by the view function which 
# is mapped to the myshop.myshoify.com/scriptsrc/  URL
def createScriptTag():
    print '==> createScriptTag()'
    scripttag = shopify.ScriptTag()
    scripttag.event = 'onload'
    scripttag.src = settings.APP_DOMAINURL + '/scriptsrc1/'
    scripttag.save()
    return scripttag

# This is the view function for the url which is supposed to capture the webhooks POST triggered when app is uninstalled
# Webhook POST requests will have the information within the request body
# Note: If shopify sends a webhook POST and recieves a 500 response, it will continue re-firing  webhook POSTs until it recieves a 200 response
# Note2: Webhooks are delayed, they have been comming in on average 15 - 30mins after uninstall
@csrf_exempt  # Cant have csrf because we are capturing an external POST request which wont be cant be signed by our django's csrf
def webhook(request):
    print "webhook()"

    try:
        webhook_topic = request.META['HTTP_X_SHOPIFY_TOPIC']
        webhook_hmac = request.META['HTTP_X_SHOPIFY_HMAC_SHA256']
        webhook_data = json.loads(request.body)
        uninstalled_store_url = str(webhook_data[u'myshopify_domain'])
        ShopDeatzInst = ShopDeatz.objects.get(shop_url=uninstalled_store_url)

    except Exception, ObjectDoesNotExist:
        print 'Store not found in DB (already uninstalled)'
        return HttpResponse('')

    # Verify the HMAC.
    if not hmac_is_valid(request.body, settings.SHOPIFY_API_SECRET, webhook_hmac):
        print 'invalid WEBHOOK hmac'
        return HttpResponseForbidden()

    # Find the store's URL in returned webhook_data dictionnary corresponding key is 'myshopify_domain'
    #print 'The data from webhook is: '
    print webhook_data

    #print 'removing store %s' %(uninstalled_store_url)

    # Remove all entries from DB that correspond to store (this is in case multiple entries would have been made)
    ShopDeatzInst = ShopDeatz.objects.filter(shop_url=uninstalled_store_url).delete()
    ShopCustInst = ShopCustomizations.objects.filter(shop_url=uninstalled_store_url).delete()
    ShopSettingsInst = ShopSettings.objects.filter(shop_url=uninstalled_store_url).delete()
    ShopMarketingServicesInst = ShopMarketingServices.objects.filter(shop_url=uninstalled_store_url).delete()
    AdvancedSettingsInst = AdvancedSettings.objects.filter(shop_url=uninstalled_store_url).delete()
    ESPInst = ESPCredentials.objects.filter(shop_url=uninstalled_store_url).delete()

    print 'Removing shop %s' %(uninstalled_store_url)

    # Add uninstall date to models.InstallTracker
    try:
        uninstall_datetime = datetime.datetime.now()
        InstallTrackerInst = InstallTracker.objects.filter(shop_url=uninstalled_store_url, uninstall_date=None)
        SubInstance = InstallTrackerInst[0]
        SubInstance.uninstall_date = uninstall_datetime  # The [0] is used because filter returns a list of objects (get first one in list)
        SubInstance.uninstaller_email = webhook_data['customer_email']
        SubInstance.save()
        print 'Uninstall written in models.InstallTracker'

    except Exception:
        pass
    
    print 'APP UN-INSTALLATION SUCCESSFULLY TERMINATED'
    print '\n'
    # Return empty HTTP response
    return HttpResponse('')


def login(request):
    # If the Merchant is logged in to his store, then the store name will be automatically passed as a parameter to his GET request, when
    # he clicks to install app. If this is the case, the shopname.myshopify.com address will be available in the GET request URL.
    # The merchant's 'Shop URL' is what we will uuse to authenticate him.
    
    # So we try to capture the 'Shop URL' from GET method if it is available
    # And call the authenticate function
    if 'shop' in request.GET:
        return authenticate(request)

    # Otherwise redirect to shopify''s login page so the user can authenticate
    context = {}
    return redirect('https://www.shopify.com/login')


# This function get the 0auth token to ceate an authenticated session
# Then it runs all initial installation
# This is also where ScriptTags should be registered?
def finalize(request):
    print '==> finalize()'
    shop_url = request.GET['shop']

    # This block checks if it is the second redirect.
    # Basically, EASDK install process automaticall redirects to finalize() when it is done, so it effectively runs this function twice
    # which on the second run triggers the Exception bellow as the session expires.
    # To avoid this, we will check again if the store exists in our zDB if it does, don't run this code just redirect to the dashboard

    try:
        print 'trying to no re-install'
        print 'shop_url %s' %(shop_url)
        ShopDeatzInst = ShopDeatz.objects.get(shop_url=str(shop_url)) 
        # redirect to dashboard
        return dashboard.views.index(request)

    except ObjectDoesNotExist:
        print 'Not found installing'
        # Then continue to installation code
        pass


    # Create a Shopify Session for Merchant Shop using shop_url and access_token (0auth token)
    try:
        shopify_session = shopify.Session(shop_url)

        # This is where the shopify 0auth token is captured
        # request_token uses the 'hmac' arguement passed along in the GET to request a 0auth token
        auth_token = shopify_session.request_token(request.GET)

        request.session['shopify'] = {
                                        "shop_url": shop_url,
                                        "access_token": auth_token,
                                     }
    except Exception:
        messages.error(request, "Could not log in to Shopify store.")
        # In case the authentication did not work, send the merchant back to the manual Login Form
        return redirect(reverse(login))

    # Activate your shopify sessions so ou can make API calls
    shopify.ShopifyResource.activate_session(shopify_session)

    # Creates an object that contains all the shop info eqvalent to GET endpoint /admin/shop.json
    shop_info = shopify.Shop.current()

    # Create an instance of ShopDeatz Model and save shop_url and access_token for future use to when issuing commands on behalf of the store.
    ShopDeatzInst = ShopDeatz()
    ShopDeatzInst.shop_url = shop_url
    ShopDeatzInst.auth_token = auth_token
    ShopDeatzInst.download_key = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(139))
    ShopDeatzInst.shop_name = shop_info.name
    ShopDeatzInst.save() 

    messages.info(request, "Logged in to shopify store.")

    # redirect(_return_addres(request)) will send you back to the webapps root '/' url where the login
    response = redirect(_return_address(request))

    request.session.pop('return_to', None)

    # Now render the merchants embeddedi post install page (the finished.html template with <head>Emmbeded APP SDK JS</head>)
    # The template itself contains a JS redirect so it will render the template redirect to Shopify dashboard, and display rendered template
    # encapsulated in an iframe in ther shopify backend

    # You must pass 2 arguements to the EASDK JS, your app's api_key and the FULL path to the store that is installing the app.
    full_shop_url = 'https://' + shop_url
    context = {
                'SHOPIFY_API_KEY': settings.SHOPIFY_API_KEY,
                'shop_url': full_shop_url
          }
    
    print '\n'
    print 'STARTING APPLICATION CHARGE PROCESS' 
    
    ################################################## 
    # Create the application charge
    ################################################## 
    # Create recurring charge
    # if the user accepts the charge, 
    # if user declines the charge, his shop will be removed from the DB
    # He will then be redirected by the createRecurringCharge() function to the redirection url a.k.a dashboard home (cdn1.gdprinsider.ovh)
    # At this point shop behaviour will be normal, if the shop still exists in the DB (accepted the charge) then they will have access to dash
    # if the shop has been removed from DB (declined the charge) then they will be redirected to the shopify install webpage

    charge = shopify.RecurringApplicationCharge()
    charge.name = settings.APP_NAME
    charge.price = settings.APP_PRICE
    charge.test = settings.APP_TESTFLAG
    charge.return_url = settings.APP_RETURNURL
    # Check if shop has already installed app preivously in Install Tracker, if it has then do not offer Trial period 
    try:
        ShopInstallTracker = InstallTracker.objects.get(shop_url=shop_url)
        pass
    # Otherwise offer 2 days of trial
    except ObjectDoesNotExist:
        charge.trial_days = settings.APP_TRIALDAYS

    charge.save()

    print 'charge_id'
    print charge.__dict__
    ShopDeatzInst.charge_id = charge.id
    ShopDeatzInst.save()

    # redirect the user to the confirmation_url given in the charge.save() response where they will be prompted to accept or decline the charge
    # Once the user accepts / declines he will then be automatically redirected to charge.return_url (https://cdn1.gdprinsider.ovh/activatecharge)
    # where we have a view (activateRecurringCharge) listening for charges to activate
    return redirect(charge.confirmation_url)

def authenticate(request):
    print '==> authenticate()'
    # This handles the case where user is already logged in
    # basically says try to get the value corresponding to the key 'shop', if key shop does not exist return ''
    shop = request.GET.get('shop', False)
    print shop
    '''
    # In this case 'shop' key has not have been found in the GET dict, this means that the user probably connected via our login form,
    # This handles the case where the user logs in via our login form using POST method
    if shop == False:
        shop = request.POST.get('shop', False)
    '''

    try:
        ShopDeatzInst = ShopDeatz.objects.get(shop_url=str(shop))
        print ShopDeatzInst
        # redirect to dashboard
        return dashboard.views.index(request)

    except ObjectDoesNotExist:
        print 'shop not installed  running Oauth'
        # Then continue to installation code
        pass


    # Otherwise, if shop is not present in our DB then build permission url, and proceed with install

    # If shop value was located in either request.GET or request.POST dicts, then use the shop_url to generate a permissions URL and
    # redirect the merchant to the 'permissions URL' so he can click <accept install>
    if shop:
        scope = settings.SHOPIFY_API_SCOPE

        # Create redirect_uri (This is the White Listed URL in the Shopify Backend)
        redirect_uri = request.build_absolute_uri(reverse(finalize))

        # Use the create_permission_url() method from shopify module's Sessions Class to generate the URL to request permission to install from
        # the merchant as soon th user clicks <accept install> he will be redirected to the redirect_uri that was bundled in the permeission_url
        shopify.Session.setup(api_key=settings.SHOPIFY_API_KEY, secret=settings.SHOPIFY_API_SECRET)
        session = shopify.Session(shop.strip())
        permission_url = session.create_permission_url(scope, redirect_uri)

        print permission_url

        # Now redirect the Merchant to permission_url so he can click the <accept install> button
        # But instead of redirecting directly to the permission URL, since we are building an embedded application we have to
        # render a template and redirect the user through javascript. Otherwise the redirect would get rejected,
        # and the URL to which the user is redirected after the finalize() would be external (not embedded)
        return render(request, 'installer/embeded_install_redirect_JS.html', {'permission_url': permission_url})

    return redirect(_return_address(request))


def logout(request):
    print '==> logout()'
    request.session.pop('shopify', None)
    messages.info(request, "Successfully logged out.")

    return redirect(reverse(login))
