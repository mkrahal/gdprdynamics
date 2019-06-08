from django.shortcuts import render, redirect
import shopify
from django.template.loader import get_template 
from django.views.decorators.csrf import csrf_protect
from installer.decorators import shop_login_required
from django.conf import settings
from installer.models import ShopDeatz
from django.http import HttpResponseForbidden, HttpResponseBadRequest, HttpResponse
from django.core.exceptions import ObjectDoesNotExist
from .models import ShopCustomizations, TemplateDefaults, ShopSettings, ShopMarketingServices, ESPCredentials, AdvancedSettings
import requests  #requets with an 'S' at the end is the requests lib used to make http requests don't confuse with ur request parameter 
from backendmodules.auditlogger import DataEventLogger 
import datetime
import os
import csv
from io import BytesIO
from xhtml2pdf import pisa
from gdpr.models import RemovalQueue
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
import hashlib, base64, hmac, json
from django.http import QueryDict


# ############################################################################################################################################
# #  Support Functions
# ############################################################################################################################################


# We need  full shop URL to pass as arguement when rendering the EASDK initialization Javascript (templates/EASDK_JS.html)
def construct_shop_url():
    # Initalize Current Shop Object to extract shop domain and construct full_shop_url,
    try:
        current_shop = shopify.Shop.current()
    except Exception:
        current_shop = ''

    full_shop_url = 'https://' + current_shop.domain
    return full_shop_url


def write_log_csv(sqlresult, filelocation):
    with open(filelocation, 'w') as csvfile:
        fieldnames = ['Data Subject ID', 'Event Timestamp', 'Event Type', 'Processing Method', 'Description', 'Purpose', 'Legal Basis', 'Status']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        writer.writeheader()
        for row in sqlresult:
            writer.writerow({
                             'Data Subject ID': row[6] , 'Event Timestamp': row[1], 'Event Type': row[2],
                             'Processing Method': row[3], 'Description': row[5], 'Purpose': row[7], 'Legal Basis': row[9], 'Status': row[8]
                            })


def render_to_pdf(template_src, context_dict={}):
    template = get_template(template_src)
    html = template.render(context_dict)
    result = BytesIO()
    pdf = pisa.pisaDocument(BytesIO(html.encode("ISO-8859-1")), result)
    if not pdf.err:
        return HttpResponse(result.getvalue(), content_type='application/pdf')
    return None


@csrf_protect
def index(request):
    ###########################################################################################################
    # Shop Request Validation and Authentication
    #########################################################################################################

    # Since, the URL for this view is requested from within the iframe, it is no longer requested by shopify, but rather by your webserver.
    # It is as if the user was on our website requesting pages directly so shopify cannot add arguements to the requests.
    # As such, the 'shop' item is no longer passed by shopify in the request
    # So to get shop_url, veriy the request's origin we need to do so using the HMAC that is passed in the first request comming from shopify
    # You should avoid using the shop_login decorator becaus that uses sessions meaning that if the user emptys his browser cookies or logs
    # in from a different computer then he will need to  re-install the app (restart 0auth flow) in order to recieve a new Session.

    # Get the Hmac from the request query
    login_hmac = str(request.GET.get('hmac', False))

    # Then build the request query string (in lexographical order) without the HMAC entry to pass to hmac_validator()
    # see example in shopifydev/info/hmac.py
    query_dictionary = dict(request.GET.iterlists())
    print query_dictionary
    query_string = ''
    for key in sorted(query_dictionary):
        if key == 'hmac':
            continue
        value = query_dictionary[key][0]  # because it comes back as a single item list
        value = value.replace('%3A', ':')
        value = value.replace('%2F', '/')
        value = value.replace('%', r'%26')
        value = value.replace('&', r'%25')
        value = value.replace('=', r'%3d')

        key = key.replace('%', r'%26')
        key = key.replace('&', r'%25')
        key = key.replace('=', r'%3d')

        query_string = query_string + key + '=' + value + '&'

    #remove the trailing '&'
    query_string = query_string[:-1]

    print 'hmac query string = %s' %(query_string)
    h = hmac.new(settings.SHOPIFY_API_SECRET, query_string, hashlib.sha256)
    calculated_hmac = (h.hexdigest())

    # HMAC VALUES MATCH
    if calculated_hmac == login_hmac:
        print 'hmac values match'
        shop_url = request.GET.get('shop', False)
        try:
            # Verify that shop_url exists in DB,
            ShopDeatzInst = ShopDeatz.objects.get(shop_url=str(shop_url))

        # This Exception will help to stop Apache from bugging out in cases where you are making DB and API calls using non existant stores
        # i.e, when the db.sql is reinitialized while a store still has the app installed but is not present in local DB
        except ObjectDoesNotExist:
            print 'Error: %s shop has app installed but is not present in the DB' %(shop_url)
            return redirect('https://www.shopify.com/login')

        # If the above authentication tests were passed then create a session for the user to authenticate any 
        # further requests he makes to our web server and drop the session cookie
        request.session['GDPRCOMPLIANCE360S'] = shop_url
        request.session['GDPRCOMPLIANCE360D'] = ShopDeatzInst.download_key
        request.session.modified = True
        pass

    #HMAC VALUES DO NOT MATCH
    else:
        print 'hmac DOES NOT MATCH'
        print 'checking if user can be authenticated via a valid session'

        # Step1 : Try  to get session tokens 
        try:
            shop_url = request.session['GDPRCOMPLIANCE360S'] 
            download_key = request.session['GDPRCOMPLIANCE360D'] 

            # Step2: Verify that shop_url exists in DB,
            try:
                ShopDeatzInst = ShopDeatz.objects.get(shop_url=str(shop_url))

            # This Exception will help to stop Apache from bugging out in cases where you are making DB and API calls using non existant stores
            # i.e, when the db.sql is reinitialized while a store still has the app installed but is not present in local DB
            except ObjectDoesNotExist:
                print 'Error: %s shop has app installed but is not present in the DB' %(shop_url)
                return redirect('https://www.shopify.com/login')

            # Step3: Verify that the download key of the user's second token matches the store of the user's first token
            if download_key == ShopDeatzInst.download_key:
                pass
            else:
                return redirect('https://www.shopify.com/login')

        except Exception:
            return redirect('https://www.shopify.com/login') 

    # If all of the above checks pass then activate your shopify session to make api calls
    session = shopify.Session(shop_url, ShopDeatzInst.auth_token)
    shopify.ShopifyResource.activate_session(session)

    ##########################################################################################################
    # View Code
    #########################################################################################################

    # Get Data Inventory stats for dashboard
    # STEP1: get all data from database, using Auditlogger

    # Get counts
    AuditLogInst = DataEventLogger(shop_url)
    processing_activities_total = AuditLogInst.count_data_events()
    total_customers = AuditLogInst.count_data_assets()
    total_access_requests = AuditLogInst.count_data_access()
    total_removal_requests = AuditLogInst.count_data_removal()
    #total_consent_granted = AuditLogInst.count_data_consent()
    total_rectification = AuditLogInst.count_data_rectification()

    removal_queue_count = len(RemovalQueue.objects.filter(shop_url=shop_url))

    processing_activities_completed = processing_activities_total - removal_queue_count

    known_marketing_partners_count = len(ShopMarketingServices.objects.get(shop_url=shop_url).known_services_list_quoted.split(','))

    unknown_marketing_partners = AdvancedSettings.objects.get(shop_url=shop_url).unknown_marketing_list.split(',')
    #print unknown_marketing_partners
    if ((unknown_marketing_partners[0] == '-' and (len(unknown_marketing_partners) == 1)) or
        (unknown_marketing_partners[0] == '"-"' and (len(unknown_marketing_partners) == 1))):

        unknown_marketing_partners_count = 0

    else:
        unknown_marketing_partners_count = len(unknown_marketing_partners)

    unknown_shipping_partners = ShopMarketingServices.objects.get(shop_url=shop_url).unknown_services_list.split(',')
    if ((unknown_shipping_partners[0] == '-' and (len(unknown_shipping_partners) == 1)) or
        (unknown_shipping_partners[0] == '"-"' and (len(unknown_shipping_partners) == 1))):

        unknown_shipping_partners_count = 0

    else:
        unknown_shipping_partners_count = len(unknown_shipping_partners)

    total_unknown_partners =  unknown_shipping_partners_count + unknown_marketing_partners_count
    total_partners = known_marketing_partners_count + total_unknown_partners

    # Get Dates (wrap in try/except in case they are empty i.e events havent occured yet)
    try:
        processing_activities_date = AuditLogInst.latest_data_event_date().strftime('%d %b %Y')
    except Exception:
        processing_activities_date = '-' 
    try:
        latest_customer_date = AuditLogInst.latest_data_asset_date().strftime('%d %b %Y')
    except Exception:
        latest_customer_date = '-'
    try:
        latest_partner_change = ShopDeatzInst.last_partner_change_datetime.strftime('%d %b %Y')
    except Exception:
        latest_partner_change = '-'
    try:
        latest_export_date = ShopDeatzInst.last_exportdatetime.strftime('%d %b %Y')
    except Exception:
        latest_export_date = '-'


    #print "processing activities total %i" %(processing_activities_total)
    #print 'removal queue %i' %(removal_queue_count)
    #print 'total customers %i' %(total_customers)
    #print 'known marketing %i' %(known_marketing_partners_count)
    #print 'unknown marketing %i' %(unknown_marketing_partners_count)
    #print 'unknown shipping %i' %(unknown_shipping_partners_count)

    # Get 4 Most recent Data Events
    most_recent_events = AuditLogInst.most_recent_4()
    #print most_recent_events
    try:
        most_recent_list = []
        for item in most_recent_events:
            most_recent_subdict = {}
            most_recent_subdict['eventid'] = item[0]
            most_recent_subdict['customerid'] = item[6]
            most_recent_subdict['eventtype'] = item[2]
            most_recent_subdict['date'] = item[1].strftime('%d %b %Y')
            most_recent_list.append(most_recent_subdict)
    except Exception:
        pass

    # Get ESP value for rendering in template
    ESPInst = ESPCredentials.objects.get(shop_url=shop_url)
    if ESPInst.configured_ESP == '-':
        email_service_integration = False
    else:
        email_service_integration = True

    # Get IP_filtering value for rendering in template
    AdvancedSettingsInst = AdvancedSettings.objects.get(shop_url=shop_url)

    # Setup Completion Score Calculation for Gauge
    gauge_score = 50
    if unknown_shipping_partners_count > 0:
        gauge_score = gauge_score + 25

    if email_service_integration == True:
        gauge_score = gauge_score + 25

    # STEP2 Check if data is submitted or if its just a simple page request
    # If this is a page request and not a <POST> then 'submitted' key will not be present in request.POST,
    # in this case just render the requested page
    if 'submitted' not in request.POST:

        # Get ESP value for rendering in template
        ESPInst = ESPCredentials.objects.get(shop_url=shop_url)
        if ESPInst.configured_ESP == '-':
            email_service_integration = False
        else:
            email_service_integration = True

        # Get IP_filtering value for rendering in template
        AdvancedSettingsInst = AdvancedSettings.objects.get(shop_url=shop_url)

        context = {
                    'SHOPIFY_API_KEY': settings.SHOPIFY_API_KEY,
                    'full_shop_url': construct_shop_url,
                    'active_home': 'ui-tertiary-navigation__link--is-active',
                    'ip_filter_status': AdvancedSettingsInst.ip_filtering_active,
                    'email_service_integration': email_service_integration,
                    'download_key': ShopDeatzInst.download_key,
                    'processing_total': processing_activities_total,
                    'processing_completed': processing_activities_completed,
                    'processing_date': processing_activities_date,
                    'data_assets_total': total_customers,
                    'data_assets_date': latest_customer_date,
                    'legal_entities_total': total_partners,
                    'legal_entities_completed': known_marketing_partners_count,
                    'legal_entities_date': latest_partner_change,
                    'dpo_activities_total': ShopDeatzInst.total_exports,
                    'dpo_activities_date': latest_export_date,
                    'most_recent_list': most_recent_list,
                    'total_access_requests':  total_access_requests,
                    'total_removal_requests':  total_removal_requests,
                    'total_rectification':  total_rectification,
                    'gauge_score': gauge_score,
                    'page_title': 'GDPR Overview',
                  }

        #print 'done'
        return render(request, 'dashboard/home.html', context)

    # Otherwise, this means the user is posting data (clcked the save button on dashboard), so continue with code execution to preocess data
    else:
        pass

    # At this point you can emit API calls directly without having to 'activate your session' because once th app is installed,
    # session activation is automatically done by the middleware
    export_type = request.POST.get('exporttype', False)
    captured_download_key = request.POST.get('dkey', False)
    current_date = datetime.date.today()
    start_date = request.POST.get('startdate', False)
    end_date = request.POST.get('enddate', False)
    export_format = request.POST.get('exportformat', False)

    #print request.POST

    # Verify that download key corresponds to shop_url in DB
    #print ShopDeatzInst.download_key
    #print captured_download_key 
    if ShopDeatzInst.download_key == captured_download_key:
        print 'keys match'
        pass
    else:
        context = {
                    'SHOPIFY_API_KEY': settings.SHOPIFY_API_KEY,
                    'full_shop_url': construct_shop_url,
                    'active_home': 'ui-tertiary-navigation__link--is-active',
                    'ip_filter_status': AdvancedSettingsInst.ip_filtering_active,
                    'email_service_integration': email_service_integration,
                    'download_key': ShopDeatzInst.download_key,
                    'processing_total': processing_activities_total,
                    'processing_completed': processing_activities_completed,
                    'processing_date': processing_activities_date,
                    'data_assets_total': total_customers,
                    'data_assets_date': latest_customer_date,
                    'legal_entities_total': total_partners,
                    'legal_entities_completed': known_marketing_partners_count,
                    'legal_entities_date': latest_partner_change,
                    'dpo_activities_total': ShopDeatzInst.total_exports,
                    'dpo_activities_date': latest_export_date,
                    'most_recent_list': most_recent_list,
                    'total_access_requests':  total_access_requests,
                    'total_removal_requests':  total_removal_requests,
                    'total_rectification':  total_rectification,
                    'gauge_score': gauge_score,
                    'page_title': 'GDPR Overview',
                  }

        return render(request, 'dashboard/home.html', context)

    # Get the shop name using api call shop name 
    # remember no need to activate a session here its all done via middleware
    shop_info = shopify.Shop.current()
    shop_name = shop_info.name

    if export_type == 'exportall' and export_format == 'CSV':
        # Construct file location and filename to save csv
        file_location = os.path.join(settings.BASE_DIR, 'exportfiledump/') + shop_name + '.csv'

        # Step1: get all data from database, using Auditlogger
        AuditLogInst = DataEventLogger(shop_url)
        result = AuditLogInst.get_hist_csv(datetime.date(2001, 1, 1), (current_date + datetime.timedelta(1)))
        # print result 

        # Step2: Write data out to csv
        write_log_csv(result, file_location)

        # Step3: Return file download 
        # Basically, when the <form> is submitted via button click, Django will return a file download, No need to re-render the template,
        # because it won't render a new page it will just make the 'Save As' pop-up dialog box open so the user can save the file
        csv_file = open(file_location, 'rb')
        response = HttpResponse(csv_file.read())
        response['Content-Type'] = 'text/csv'
        response['Content-Disposition'] = 'attachment; filename=%s_GDPR_Audit_Log.csv' %(shop_name)
        csv_file.close()
        os.remove(file_location)

        # Write export time in installer.models.ShopDeatz and increase export count by 1
        ShopDeatzInst.last_exportdatetime = datetime.datetime.now()
        ShopDeatzInst.total_exports = ShopDeatzInst.total_exports + 1
        ShopDeatzInst.save()

        # Return file download
        return response

    elif export_type == 'exportall' and export_format == 'PDF':
        # Step1: get all data from database, using Auditlogger
        AuditLogInst = DataEventLogger(shop_url)
        result = AuditLogInst.get_hist_csv(datetime.date(2001, 1, 1), (current_date + datetime.timedelta(1))) 
        # print result

        # Go through result dict and split up the email addresses if they are linger than 27 chars, because they overflow in xhtml2pdf
        # first convert tuple to list because tuples don't suport in place assignment 
        result = list(result)
        new_result = []
        for row in result:
            row = list(row)
            #print row
            #print row[6]

            if len(row[6]) > 27:
                #print len(row[0])
                splits = (len(row[6]) / 27)
                remainder = (len(row[6]) % 27)
                if remainder != 0:
                    splits = splits + 1

                new_customer_id = ''
                for split_index in range (1, (splits + 1)):
                    if split_index == splits:
                        new_customer_id = new_customer_id + row[6][((split_index-1) * 27):]
                    else:
                        new_customer_id = new_customer_id + row[6][((split_index-1) * 27):(split_index * 27)] + ' '
                    #print new_customer_id

                row[6] = new_customer_id

            new_result.append(row)

        #print new_result

        # Step2: Generate pdf from template
        context = { 
                    'shop_name': shop_name, 
                    'dataevent_list': new_result
                  }
        pdf = render_to_pdf('pdf_report_template.html', context) 

        # Step3: Return file download 
        # Basically, when the <form> is submitted via button click, Django will return a file download, No need to re-render the template,
        # because it won't render a new page it will just make the 'Save As' pop-up dialog box open so the user can save the file
        response = HttpResponse(pdf)
        response['Content-Type'] = 'application/pdf'
        response['Content-Disposition'] = 'attachment; filename=%s_GDPR_Audit_Log.pdf' %(shop_name)
        # removeoriginal file from db, file has been read to buffer memory (RAM), so ne need to keep it on disk anymore

        # Write export time in installer.models.ShopDeatz and increase export count by 1
        ShopDeatzInst.last_exportdatetime = datetime.datetime.now()
        ShopDeatzInst.total_exports = ShopDeatzInst.total_exports + 1
        ShopDeatzInst.save()

        # Return file download
        return response

    elif export_type == 'exporttimeperiod' and export_format == 'CSV':
        # Construct file location and filename to save csv
        file_location = os.path.join(settings.BASE_DIR, 'exportfiledump/') + shop_name + '.csv'

        # Step1: get all data from database, using Auditlogger
        AuditLogInst = DataEventLogger(shop_url)
        result = AuditLogInst.get_hist_csv(datetime.datetime.strptime(start_date, '%m/%d/%Y'), datetime.datetime.strptime(end_date, '%m/%d/%Y'))
        # print result

        # Step2: Write data out to csv
        write_log_csv(result, file_location)

        # Step3: Return file download 
        # Basically, when the <form> is submitted via button click, Django will return a file download, No need to re-render the template,
        # because it won't render a new page it will just make the 'Save As' pop-up dialog box open so the user can save the file
        csv_file = open(file_location, 'rb')
        response = HttpResponse(csv_file.read())
        response['Content-Type'] = 'text/csv'
        response['Content-Disposition'] = 'attachment; filename=%s_GDPR_Audit_Log.csv' %(shop_name)
        csv_file.close()
        os.remove(file_location)

        # Write export time in installer.models.ShopDeatz and increase export count by 1
        ShopDeatzInst.last_exportdatetime = datetime.datetime.now()
        ShopDeatzInst.total_exports = ShopDeatzInst.total_exports + 1
        ShopDeatzInst.save()

        # Return file download
        return response

    elif export_type == 'exporttimeperiod' and export_format == 'PDF':
        # Step1: get all data from database, using Auditlogger
        AuditLogInst = DataEventLogger(shop_url)
        result = AuditLogInst.get_hist_csv(datetime.datetime.strptime(start_date, '%m/%d/%Y'), datetime.datetime.strptime(end_date, '%m/%d/%Y'))
        # print result

        # Go through result dict and split up the email addresses if they are linger than 27 chars, because they overflow in xhtml2pdf
        # first convert tuple to list because tuples don't suport in place assignment 
        result = list(result)
        new_result = []
        for row in result:
            row = list(row)
            #print row
            #print row[6]

            if len(row[6]) > 27:
                #print len(row[6])
                splits = (len(row[6]) / 27)
                remainder = (len(row[6]) % 27)
                if remainder != 6:
                    splits = splits + 1

                new_customer_id = ''
                for split_index in range (1, (splits + 1)):
                    if split_index == splits:
                        new_customer_id = new_customer_id + row[6][((split_index-1) * 27):]
                    else:
                        new_customer_id = new_customer_id + row[6][((split_index-1) * 27):(split_index * 27)] + ' '
                    #print new_customer_id

                row[6] = new_customer_id

            new_result.append(row)

        #print new_result

        # Step2: Generate pdf from template
        context = {
                    'shop_name': shop_name,
                    'dataevent_list': new_result
                  }
        pdf = render_to_pdf('pdf_report_template.html', context)

        # Step3: Return file download 
        # Basically, when the <form> is submitted via button click, Django will return a file download, No need to re-render the template,
        # because it won't render a new page it will just make the 'Save As' pop-up dialog box open so the user can save the file
        response = HttpResponse(pdf)
        response['Content-Type'] = 'application/pdf'
        response['Content-Disposition'] = 'attachment; filename=%s_GDPR_Audit_Log.pdf' %(shop_name)
        # removeoriginal file from db, file has been read to buffer memory (RAM), so ne need to keep it on disk anymore

        # Write export time in installer.models.ShopDeatz and increase export count by 1
        ShopDeatzInst.last_exportdatetime = datetime.datetime.now()
        ShopDeatzInst.total_exports = ShopDeatzInst.total_exports + 1
        ShopDeatzInst.save()

        # Return file download
        return response

    # In Your context you must add SHOPIFY_API_KEY and shopOrigin, to render the EASDK initialization script
    # Note: shopOrigin is automaically added to your context variables via ContextProcessor (current_shop.domain)
    else:
        context = {
                    'SHOPIFY_API_KEY': settings.SHOPIFY_API_KEY,
                    'full_shop_url': construct_shop_url,
                    'active_home': 'ui-tertiary-navigation__link--is-active',
                    'ip_filter_status': AdvancedSettingsInst.ip_filtering_active,
                    'email_service_integration': email_service_integration,
                    'download_key': ShopDeatzInst.download_key,
                    'processing_total': processing_activities_total,
                    'processing_completed': processing_activities_completed,
                    'processing_date': processing_activities_date,
                    'data_assets_total': total_customers,
                    'data_assets_date': latest_customer_date,
                    'legal_entities_total': total_partners,
                    'legal_entities_completed': known_marketing_partners_count,
                    'legal_entities_date': latest_partner_change,
                    'dpo_activities_total': ShopDeatzInst.total_exports,
                    'dpo_activities_date': latest_export_date,
                    'most_recent_list': most_recent_list,
                    'total_access_requests':  total_access_requests,
                    'total_removal_requests':  total_removal_requests,
                    'total_rectification':  total_rectification,
                    'gauge_score': gauge_score,
                    'page_title': 'GDPR Overview',
                  }

        return render(request, 'dashboard/home.html', context)


@csrf_protect
def initial_setup(request):
    ###########################################################################################################
    # Shop Request Validation and Authentication
    #########################################################################################################

    # Since, the URL for this view is requested from within the iframe, it is no longer requested by shopify, but rather by your webserver.
    # It is as if the user was on our website requesting pages directly so shopify cannot add arguements to the requests.
    # As such, the 'shop' item is no longer passed by shopify in the request
    # So instead we will check for the session that we created in /index. If the user's browser has an active session for his store than let him
    # access this view. Otherwise block the request, and redirect the user to shopify login, where he can login to his store, and access the app
    # index page which will create a new session for him and then he can visit the page associated to this view using a valid django session
    try:
        # Step1: Check if the the user has valid session tokens
        shop_url = request.session['GDPRCOMPLIANCE360S']
        download_key = request.session['GDPRCOMPLIANCE360D']
    except Exception:
        return redirect('https://www.shopify.com/login')

    # Add switch to check if store exists in our registered store's DB. In case store does not exist in our DB, return HTTPBadRequest
    # if the store exists, it will make one further check to verify that the access token passed for the store corresponds to the one
    # we have in our DB. If it does it means that the request is legitimately comming from the store, if they don't match, then someone
    # could be attempting to forge fake sessionsi using the shop_url to access data (but he does not have the auth token)
    try:
        # Step2: Verify that shop_url from the session exists in DB,
        ShopDeatzInst = ShopDeatz.objects.get(shop_url=str(shop_url))

    # This Exception will help to stop Apache from bugging out in cases where you are making DB and API calls using non existant stores
    # i.e, when the db.sql is reinitialized while a store still has the app installed but is not present in local DB
    # or when no active session was found in the user's browser.
    except ObjectDoesNotExist:
        print 'Error: %s shop has app installed but is not present in the DB' %(shop_url)
        return redirect('https://www.shopify.com/login')

    # Step3 : Verify that the download key of the user's second session token matches that of the shop_url found in the user's first token
    if download_key == ShopDeatzInst.download_key:
        pass
    else:
        return redirect('https://www.shopify.com/login')

    # If all the above tests were passed, then activate your shopify session to make api calls
    session = shopify.Session(shop_url, ShopDeatzInst.auth_token)
    shopify.ShopifyResource.activate_session(session)

    ##########################################################################################################
    # View Code
    #########################################################################################################

    # If this is a page request and not a <POST> then 'submitted' key will not be present in request.POST, 
    # in this case just render the requested page
    if 'submitted' not in request.POST:

        # Get settings from the database to render them in template
        ShopSettingsInst = ShopSettings.objects.get(shop_url=shop_url)
        ShopMarketingInst = ShopMarketingServices.objects.get(shop_url=shop_url)

        # Try to auto-matically set the country if it is not set in the DB (still in default '-' value)
        try:
            if ShopSettingsInst.third_country ==  '-':
                # Get the current shop
                ShopInfo = shopify.Shop.current()
                ShopSettingsInst.third_country = ShopInfo.country_name
                ShopSettingsInst.save()
        except Exception:
            pass

        # Get ESP info from DB to render in template
        ESPInst = ESPCredentials.objects.get(shop_url=shop_url)

        # Check uknown_services_list if it contains default '-' then make its value None otherwise get its value from the DB
        if ShopMarketingInst.unknown_services_list == '-':
            ums_list = ''
        else:
            # Get the UMS_list string (no need to split it here, it will be split up in JavaScript onLoad script)
            ums_list = ShopMarketingInst.unknown_services_list

        context = {
                   'SHOPIFY_API_KEY': settings.SHOPIFY_API_KEY,
                   'full_shop_url': construct_shop_url,
                   'active_settings': 'ui-tertiary-navigation__link--is-active',
                   'cb_shipping': str(ShopSettingsInst.datapurpose_shipping),
                   'cb_payproc': str(ShopSettingsInst.datapurpose_payproc),
                   'cb_emarketing': str(ShopSettingsInst.datapurpose_emarketing),
                   'cb_retar': str(ShopSettingsInst.datapurpose_retar),
                   'storage_duration':str(ShopSettingsInst.storage_duration),
                   'data_sharing': ShopSettingsInst.data_sharing,
                   'third_country': ShopSettingsInst.third_country,
                   'KMS_list': ShopMarketingInst.known_services_list_quoted,
                   'UMS_list': ums_list,
                   'shop_url': shop_url,
                   'configured_ESP': ESPInst.configured_ESP,
                   'API_key': ESPInst.esp_API_key,
                   'page_title': 'Setup Wizard',
                  }

        return render(request, 'dashboard/setup_wizard.html', context)

    # Otherwise, this means the user is posting data (clcked the save button on dashboard), so continue with code execution to preocess data
    else:
        pass
    # At this point you can emit API calls directly without having to 'activate your session' because once th app is installed,
    # session activation is automatically done by the middleware

    #print request.POST

    # Capture Posted Data
    cb_shipping = request.POST.get('cb-shipping', False)
    cb_payproc = request.POST.get('cb-payproc', False)
    cb_emarketing = request.POST.get('cb-emarketing', False)
    cb_retar = request.POST.get('cb-retar', False)
    storage_duration = request.POST.get('storage-duration', False)
    data_sharing = request.POST.get('data-sharing', False)
    third_country = request.POST.get('country-code', False)
    omnisend = request.POST.get('omnisend', False)
    api_key = request.POST.get('api-key', False)
    unknown_partner1 = request.POST.get('item_name', False)

    # Split partners list comming from tags text box in setup wizard step 3
    final_uknownpartners_list = unknown_partner1.split(',')

    # check if final_partners_list is empty if so then make its value == to default '-' representing empty DB entries
    if (len(final_uknownpartners_list) == 0):
        final_uknownpartners_list.append('-')

    elif (len(final_uknownpartners_list) == 1 and final_uknownpartners_list[0] == ''):
        final_uknownpartners_list[0] = '-'

    else:
        pass

    #print final_uknownpartners_list
    UMS_quoted = '"' + '","'.join(final_uknownpartners_list) + '"'

    # KnownMarketingServices List Construct a list of the know marketing services to which the user has subscribed
    KMS_list = ['shopify', 'gdpr']  # Append to the default minimum partners list

    KMS_list.append(request.POST.get('cb-google', 'None'))  # add '-id' because thats how the id's are named in the html code
    KMS_list.append(request.POST.get('cb-facebook', 'None'))
    KMS_list.append(request.POST.get('cb-instagram', 'None'))
    KMS_list.append(request.POST.get('cb-youtube', 'None'))
    KMS_list.append(request.POST.get('cb-twitter', 'None'))
    KMS_list.append(request.POST.get('cb-amazon', 'None'))
    KMS_list.append(request.POST.get('cb-bing', 'None'))
    KMS_list.append(request.POST.get('cb-yahoo', 'None'))
    KMS_list.append(request.POST.get('cb-leadbolt', 'None'))
    KMS_list.append(request.POST.get('cb-inmobi', 'None'))
    KMS_list.append(request.POST.get('cb-mopub', 'None'))
    KMS_list.append(request.POST.get('cb-adroll', 'None'))

    # Filter the list to remove all None values (values where the check box passed no values a.k.a not selected services)
    new_kms_list = []
    for item in KMS_list:
        if (item != 'None'):
            new_kms_list.append(item)

    # Transform the list to a string of quoted chars for Javascript and a string of unquoted chars for django 
    # basically save the unquoted string in Django DB and pass the '' quoted string to Javascript for rendering
    # unquoted is used in scripttag.views for template rendering and DB MarketingService Details lookup
    KMS_quoted = '"' + '","'.join(new_kms_list) + '"'
    #KMS_unquoted = ','.join(new_kms_list)

    # Check if partners were changed this needs to be logged in installer.models.ShopDeatz.last_partner_change_datetime for rendering in dash
    ShopSettingsInst = ShopSettings.objects.get(shop_url=shop_url) 
    ShopMarketingInst = ShopMarketingServices.objects.get(shop_url=shop_url)
    if (KMS_quoted != ShopMarketingInst.known_services_list_quoted or 
            UMS_quoted != ShopMarketingInst.unknown_services_list):

        ShopDeatzInst.last_partner_change_datetime = datetime.datetime.now()
        ShopDeatzInst.save()

    else:
        pass

    # Save Settings Configuration in DB
    ShopSettingsInst.datapurpose_shipping = bool(cb_shipping)
    ShopSettingsInst.datapurpose_payproc = bool(cb_payproc)
    ShopSettingsInst.datapurpose_emarketing = bool(cb_emarketing)
    ShopSettingsInst.datapurpose_retar = bool(cb_retar)

    if storage_duration != False:
        ShopSettingsInst.storage_duration = int(storage_duration)
    if data_sharing != False:
        ShopSettingsInst.data_sharing = data_sharing
    if third_country != False:
        ShopSettingsInst.third_country = third_country

    ShopSettingsInst.save()

    ShopMarketingInst.known_services_list_quoted = KMS_quoted
    #ShopMarketingInst.known_services_list_unquoted = KMS_unquoted
    ShopMarketingInst.unknown_services_list = UMS_quoted
    ShopMarketingInst.save()

    # if omnisend is true, then switch configured ESP to omninisend 
    ESPInst = ESPCredentials.objects.get(shop_url=shop_url)
    if omnisend == 'True':
        ESPInst.configured_ESP = 'omnisend'
        ESPInst.esp_API_key = api_key 
        ESPInst.save()
    # This handles the case where api_key is modified without changeing Email Service Provider
    elif api_key != ESPInst.esp_API_key:
        ESPInst.esp_API_key = api_key 
        ESPInst.save()

    context = {}

    return HttpResponse('')


@csrf_protect
def customize_popups(request):
    ###########################################################################################################
    # Shop Request Validation and Authentication
    #########################################################################################################

    # Since, the URL for this view is requested from within the iframe, it is no longer requested by shopify, but rather by your webserver.
    # It is as if the user was on our website requesting pages directly so shopify cannot add arguements to the requests.
    # As such, the 'shop' item is no longer passed by shopify in the request
    # So instead we will check for the session that we created in /index. If the user's browser has an active session for his store than let him
    # access this view. Otherwise block the request, and redirect the user to shopify login, where he can login to his store, and access the app
    # index page which will create a new session for him and then he can visit the page associated to this view using a valid django session
    try:
        # Step1: Check if the the user has valid session tokens
        shop_url = request.session['GDPRCOMPLIANCE360S']
        download_key = request.session['GDPRCOMPLIANCE360D']
    except Exception:
        return redirect('https://www.shopify.com/login')

    # Add switch to check if store exists in our registered store's DB. In case store does not exist in our DB, return HTTPBadRequest
    # if the store exists, it will make one further check to verify that the access token passed for the store corresponds to the one
    # we have in our DB. If it does it means that the request is legitimately comming from the store, if they don't match, then someone
    # could be attempting to forge fake sessionsi using the shop_url to access data (but he does not have the auth token)
    try:
        # Step2: Verify that shop_url from the session exists in DB,
        ShopDeatzInst = ShopDeatz.objects.get(shop_url=str(shop_url))

    # This Exception will help to stop Apache from bugging out in cases where you are making DB and API calls using non existant stores
    # i.e, when the db.sql is reinitialized while a store still has the app installed but is not present in local DB
    # or when no active session was found in the user's browser.
    except ObjectDoesNotExist:
        print 'Error: %s shop has app installed but is not present in the DB' %(shop_url)
        return redirect('https://www.shopify.com/login')

    # Step3 : Verify that the download key of the user's second session token matches that of the shop_url found in the user's first token
    if download_key == ShopDeatzInst.download_key:
        pass
    else:
        return redirect('https://www.shopify.com/login')

    # If all the above tests were passed, then activate your shopify session to make api calls
    session = shopify.Session(shop_url, ShopDeatzInst.auth_token)
    shopify.ShopifyResource.activate_session(session)
    ##########################################################################################################
    # View Code
    #########################################################################################################

    # At this point you can emit API calls directly without having to 'activate your session' because once the app is installed,
    # session activation is automatically done by the middleware

    # If this is a page request and not a <POST> then 'submitted' key will not be present in request.POST, 
    # in this case just get current styles from DB and render the requested page
    if 'submitted' not in request.POST:
        # Get current styes from DB and render them in context
        ShopCustInst = ShopCustomizations.objects.get(shop_url=shop_url)
        # Create variables for button focus when rendering template
        template_focus  = 'template_' + str(ShopCustInst.active_template).lower()
        font_focus  = 'font_' + str(ShopCustInst.font_type).lower()
        context = {
                   'SHOPIFY_API_KEY': settings.SHOPIFY_API_KEY,
                   'full_shop_url': construct_shop_url,
                   'active_customize': 'ui-tertiary-navigation__link--is-active',
                   'background_color': ShopCustInst.background_color,
                   'text_color': ShopCustInst.text_color,
                   'secondary_text_color': ShopCustInst.secondary_text_color,
                   'active_tab_text_color': ShopCustInst.active_tab_text_color,
                   'accept_color': ShopCustInst.accept_color,
                   'decline_color': ShopCustInst.decline_color,
                   'font_type': ShopCustInst.font_type,
                   'font_focus': font_focus,
                   'behaviour': ShopCustInst.widget_behaviour,
                   'time_delay': ShopCustInst.time_delay,
                   'page_title': 'Customize Privacy Center',
                  }

        return render(request, 'dashboard/custpop.html', context)

    # Otherwise, this means the user is posting data (clcked the save button on dashboard), so continue with code execution to preocess data
    else:
        pass

    # Capture Posted Data
    background_color = request.POST['hex-background-color']
    text_color = request.POST['hex-text-color']
    secondary_text_color = request.POST['hex-secondary-text-color']
    active_tab_text_color = request.POST['active-tab-text-color']
    accept_color = request.POST['hex-accept-color']
    decline_color = request.POST['hex-decline-color']
    font_type = request.POST['fonttype']
    time_delay = request.POST['time-delay']
    reset_flag = request.POST['reset-flag']
    behaviour = request.POST['iCheck']

    #print request.POST

    # if reset-flag is set to True, then get default-template values and pass them for DB writing
    if str(reset_flag) == 'True':
        DefaultsInst = TemplateDefaults.objects.get(template_name='retro')
        background_color = DefaultsInst.background_color
        text_color = DefaultsInst.text_color
        secondary_text_color = DefaultsInst.secondary_text_color
        active_tab_text_color = DefaultsInst.active_tab_text_color
        accept_color = DefaultsInst.accept_color
        decline_color = DefaultsInst.decline_color
        font_type = DefaultsInst.font_type
        time_delay = DefaultsInst.time_delay
        behaviour = DefaultsInst.widget_behaviour
    else:
        pass
    
    # Write data to DB
    ShopCustInst = ShopCustomizations.objects.get(shop_url=shop_url)
    ShopCustInst.background_color = background_color
    ShopCustInst.text_color = text_color
    ShopCustInst.secondary_text_color = secondary_text_color
    ShopCustInst.active_tab_text_color = active_tab_text_color
    ShopCustInst.accept_color = accept_color
    ShopCustInst.decline_color = decline_color
    ShopCustInst.font_type = font_type
    ShopCustInst.widget_behaviour = behaviour
    ShopCustInst.time_delay = int(time_delay)
    ShopCustInst.save()

    # Get Current settings for font to pass for rendering
    font_focus  = 'font_' + str(ShopCustInst.font_type).lower()

    # Put new customizations into context and re-load customizepop.html with new values
    context = {
                'SHOPIFY_API_KEY': settings.SHOPIFY_API_KEY,
                'full_shop_url': construct_shop_url,
                'active_customize': 'ui-tertiary-navigation__link--is-active',
                'background_color': background_color,
                'text_color': text_color,
                'accept_color': accept_color,
                'secondary_text_color': secondary_text_color,
                'active_tab_text_color': active_tab_text_color,
                'decline_color': decline_color,
                'font_type': font_type,
                'font_focus': font_focus,
                'behaviour': behaviour,
                'time_delay': time_delay,
                'page_title': 'Customize Privacy Center',
              }

    return render(request, 'dashboard/custpop.html', context)


@csrf_protect
def faq(request):
    ###########################################################################################################
    # Shop Request Validation and Authentication
    #########################################################################################################

    # Since, the URL for this view is requested from within the iframe, it is no longer requested by shopify, but rather by your webserver.
    # It is as if the user was on our website requesting pages directly so shopify cannot add arguements to the requests.
    # As such, the 'shop' item is no longer passed by shopify in the request
    # So instead we will check for the session that we created in /index. If the user's browser has an active session for his store than let him
    # access this view. Otherwise block the request, and redirect the user to shopify login, where he can login to his store, and access the app
    # index page which will create a new session for him and then he can visit the page associated to this view using a valid django session
    try:
        # Step1: Check if the the user has valid session tokens
        shop_url = request.session['GDPRCOMPLIANCE360S']
        download_key = request.session['GDPRCOMPLIANCE360D']
    except Exception:
        return redirect('https://www.shopify.com/login')

    # Add switch to check if store exists in our registered store's DB. In case store does not exist in our DB, return HTTPBadRequest
    # if the store exists, it will make one further check to verify that the access token passed for the store corresponds to the one
    # we have in our DB. If it does it means that the request is legitimately comming from the store, if they don't match, then someone
    # could be attempting to forge fake sessionsi using the shop_url to access data (but he does not have the auth token)
    try:
        # Step2: Verify that shop_url from the session exists in DB,
        ShopDeatzInst = ShopDeatz.objects.get(shop_url=str(shop_url))

    # This Exception will help to stop Apache from bugging out in cases where you are making DB and API calls using non existant stores
    # i.e, when the db.sql is reinitialized while a store still has the app installed but is not present in local DB
    # or when no active session was found in the user's browser.
    except ObjectDoesNotExist:
        print 'Error: %s shop has app installed but is not present in the DB' %(shop_url)
        return redirect('https://www.shopify.com/login')

    # Step3 : Verify that the download key of the user's second session token matches that of the shop_url found in the user's first token
    if download_key == ShopDeatzInst.download_key:
        pass
    else:
        return redirect('https://www.shopify.com/login')

    # If all the above tests were passed, then activate your shopify session to make api calls
    session = shopify.Session(shop_url, ShopDeatzInst.auth_token)
    shopify.ShopifyResource.activate_session(session)


    ##########################################################################################################
    # View Code
    #########################################################################################################

    # If this is a page request and not a <POST> then 'submitted' key will not be present in request.POST, 
    # in this case just render the requested page
    if 'submitted' not in request.POST: 

        context = {
                    'SHOPIFY_API_KEY': settings.SHOPIFY_API_KEY,
                    'full_shop_url': construct_shop_url,
                    'page_title': 'Frequently Asked Questions',
                  }

        return render(request, 'dashboard/faq.html', context)

    # Otherwise, this means the user is posting data (clcked the save button on dashboard), so continue with code execution to preocess data
    else:
        pass

    # At this point you can emit API calls directly without having to 'activate your session' because once th app is installed,
    # session activation is automatically done by the middleware

    # In Your context you must add SHOPIFY_API_KEY and shopOrigin, to render the EASDK initialization script
    # Note: shopOrigin is automaically added to your context variables via ContextProcessor (current_shop.domain)
    context = {
                'SHOPIFY_API_KEY': settings.SHOPIFY_API_KEY,
                'full_shop_url': construct_shop_url,
                'page_title': 'Frequently Asked Questions',
              }

    return render(request, 'dashboard/faq.html', context)


@csrf_protect
def advanced_settings(request):
    ###########################################################################################################
    # Shop Request Validation and Authentication
    #########################################################################################################

    # Since, the URL for this view is requested from within the iframe, it is no longer requested by shopify, but rather by your webserver.
    # It is as if the user was on our website requesting pages directly so shopify cannot add arguements to the requests.
    # As such, the 'shop' item is no longer passed by shopify in the request
    # So instead we will check for the session that we created in /index. If the user's browser has an active session for his store than let him
    # access this view. Otherwise block the request, and redirect the user to shopify login, where he can login to his store, and access the app
    # index page which will create a new session for him and then he can visit the page associated to this view using a valid django session
    try:
        # Step1: Check if the the user has valid session tokens
        shop_url = request.session['GDPRCOMPLIANCE360S']
        download_key = request.session['GDPRCOMPLIANCE360D']
    except Exception:
        return redirect('https://www.shopify.com/login')

    # Add switch to check if store exists in our registered store's DB. In case store does not exist in our DB, return HTTPBadRequest
    # if the store exists, it will make one further check to verify that the access token passed for the store corresponds to the one
    # we have in our DB. If it does it means that the request is legitimately comming from the store, if they don't match, then someone
    # could be attempting to forge fake sessionsi using the shop_url to access data (but he does not have the auth token)
    try:
        # Step2: Verify that shop_url from the session exists in DB,
        ShopDeatzInst = ShopDeatz.objects.get(shop_url=str(shop_url))

    # This Exception will help to stop Apache from bugging out in cases where you are making DB and API calls using non existant stores
    # i.e, when the db.sql is reinitialized while a store still has the app installed but is not present in local DB
    # or when no active session was found in the user's browser.
    except ObjectDoesNotExist:
        print 'Error: %s shop has app installed but is not present in the DB' %(shop_url)
        return redirect('https://www.shopify.com/login')

    # Step3 : Verify that the download key of the user's second session token matches that of the shop_url found in the user's first token
    if download_key == ShopDeatzInst.download_key:
        pass
    else:
        return redirect('https://www.shopify.com/login')

    # If all the above tests were passed, then activate your shopify session to make api calls
    session = shopify.Session(shop_url, ShopDeatzInst.auth_token)
    shopify.ShopifyResource.activate_session(session)
    

    ##########################################################################################################
    # View Code
    #########################################################################################################

    # At this point you can emit API calls directly without having to 'activate your session' because once the app is installed,
    # session activation is automatically done by the middleware

    # If this is a page request and not a <POST> then 'submitted' key will not be present in request.POST, 
    # in this case just render the requested page
    
    # Get settings from the database to render them in template
    ShopSettingsInst = ShopSettings.objects.get(shop_url=shop_url)
    ShopMarketingInst = ShopMarketingServices.objects.get(shop_url=shop_url)

    # Try to auto-matically set the country if it is not set in the DB (still in default '-' value)
    try:
        if ShopSettingsInst.third_country ==  '-':
            # Get the current shop
            ShopInfo = shopify.Shop.current()
            ShopSettingsInst.third_country = ShopInfo.country_name
            ShopSettingsInst.save()
    except Exception:
        pass

    # Get ESP info from DB to render in template
    ESPInst = ESPCredentials.objects.get(shop_url=shop_url)

    # Check uknown_services_list if it contains default '-' then make its value None otherwise get its value from the DB
    if ShopMarketingInst.unknown_services_list == '-':
        ums_list = ''
    else:
        # Get the UMS_list string (no need to split it here, it will be split up in JavaScript onLoad script)
        ums_list = ShopMarketingInst.unknown_services_list

    # Get div id to scroll to in focus on page load, if none is passed then sroll to the top div a.k.a Collection Purpose 
    scroll_to_div = request.GET.get('scrolltodiv', 'pagetopref')

    if 'submitted' not in request.POST:
        AdvancedSettingsInst = AdvancedSettings.objects.get(shop_url=shop_url)
        context = {
                   'SHOPIFY_API_KEY': settings.SHOPIFY_API_KEY,
                   'full_shop_url': construct_shop_url,
                   'active_advanced': 'ui-tertiary-navigation__link--is-active',
                   'UMS_list_mrktng': AdvancedSettingsInst.unknown_marketing_list.replace('"', '').replace(' ', ''),
                   'custom_consent_text': AdvancedSettingsInst.custom_consent_text,
                   'ip_filtering_status': 'checked' if str(AdvancedSettingsInst.ip_filtering_active) == 'True' else '',
                   'cb_shipping': 'checked' if str(ShopSettingsInst.datapurpose_shipping) == 'True' else '',
                   'cb_payproc': 'checked' if str(ShopSettingsInst.datapurpose_payproc) == 'True' else '',
                   'cb_emarketing': 'checked' if str(ShopSettingsInst.datapurpose_emarketing) == 'True' else '',
                   'cb_retar': 'checked' if str(ShopSettingsInst.datapurpose_retar) == 'True' else '',
                   'cb_google': 'checked' if '"cb-google"' in ShopMarketingInst.known_services_list_quoted else '',
                   'cb_facebook':'checked' if '"cb-facebook"' in ShopMarketingInst.known_services_list_quoted else '',
                   'cb_instagram': 'checked' if '"cb-instagram"' in ShopMarketingInst.known_services_list_quoted else '',
                   'cb_youtube': 'checked' if '"cb-youtube"' in ShopMarketingInst.known_services_list_quoted else '',
                   'cb_twitter': 'checked' if '"cb-twitter"' in ShopMarketingInst.known_services_list_quoted else '',
                   'cb_amazon': 'checked' if '"cb-amazon"' in ShopMarketingInst.known_services_list_quoted else '',
                   'cb_bing': 'checked' if '"cb-bing"' in ShopMarketingInst.known_services_list_quoted else '',
                   'cb_yahoo': 'checked' if '"cb-yahoo"' in ShopMarketingInst.known_services_list_quoted else '',
                   'cb_leadbolt': 'checked' if '"cb-leadbolt"' in ShopMarketingInst.known_services_list_quoted else '',
                   'cb_inmobi': 'checked' if '"cb-inmobi"' in ShopMarketingInst.known_services_list_quoted else '',
                   'cb_mopub': 'checked' if '"cb-mopub"' in ShopMarketingInst.known_services_list_quoted else '',
                   'cb_adroll': 'checked' if '"cb-adroll"' in ShopMarketingInst.known_services_list_quoted else '',
                   'storage_duration':str(ShopSettingsInst.storage_duration),
                   'data_sharing': ShopSettingsInst.data_sharing,
                   'third_country': ShopSettingsInst.third_country,
                   'UMS_list': ums_list.replace('"', '').replace(' ', ''),
                   'shop_url': shop_url,
                   'configured_ESP': ESPInst.configured_ESP,
                   'API_key': ESPInst.esp_API_key,
                   'scrolltodiv': scroll_to_div,
                   'page_title': 'Advanced Settings',
                  }

        return render(request, 'dashboard/advancedsettings.html', context)

    # Otherwise, this means the user is posting data (clcked the save button on dashboard), so continue with code execution to preocess data
    else:
        pass

    # At this point you can emit API calls directly without having to 'activate your session' because once th app is installed,
    # session activation is automatically done by the middleware 
    # Capture Posted Data
    custom_consent_text = request.POST.get('collection-purpose', False)
    unknown_partner1_mrktng = request.POST.get('item_name_mrktng', False)
    ip_filtering_status = request.POST.get('ipfilter', False) 
    cb_shipping = request.POST.get('cb-shipping', False)
    cb_payproc = request.POST.get('cb-payproc', False)
    cb_emarketing = request.POST.get('cb-emarketing', False)
    cb_retar = request.POST.get('cb-retar', False)
    storage_duration = request.POST.get('storage-duration', False)
    data_sharing = request.POST.get('data-sharing', False)
    third_country = request.POST.get('country-code', False)
    omnisend = request.POST.get('omnisend', False)
    api_key = request.POST.get('api-key', False)
    unknown_partner1 = request.POST.get('item_name', False)
   
    #print request.POST

    # Check that data storage duration is a number
    try:
        int(storage_duration)
    except Exception:
        storage_duration = '0'

    # Unknown (Shipping) Partners
    final_uknownpartners_list =  unknown_partner1.split(',')

    # check if final_partners_list is empty if so then make its value == to default '-' representing empty DB entries
    if (len(final_uknownpartners_list) == 0):
        final_uknownpartners_list.append('-')

    elif (len(final_uknownpartners_list) == 1 and final_uknownpartners_list[0] == ''):
        final_uknownpartners_list[0] = '-'

    else:
        pass

    #print final_uknownpartners_list
    UMS_quoted = '"' + '","'.join(final_uknownpartners_list) + '"'

    # KnownMarketingServices List Construct a list of the know marketing services to which the user has subscribed
    KMS_list = ['shopify', 'gdpr']  # Append to the default minimum partners list

    KMS_list.append(request.POST.get('cb-google', 'None'))  # add '-id' because thats how the id's are named in the html code
    KMS_list.append(request.POST.get('cb-facebook', 'None'))
    KMS_list.append(request.POST.get('cb-instagram', 'None'))
    KMS_list.append(request.POST.get('cb-youtube', 'None'))
    KMS_list.append(request.POST.get('cb-twitter', 'None'))
    KMS_list.append(request.POST.get('cb-amazon', 'None'))
    KMS_list.append(request.POST.get('cb-bing', 'None'))
    KMS_list.append(request.POST.get('cb-yahoo', 'None'))
    KMS_list.append(request.POST.get('cb-leadbolt', 'None'))
    KMS_list.append(request.POST.get('cb-inmobi', 'None'))
    KMS_list.append(request.POST.get('cb-mopub', 'None'))
    KMS_list.append(request.POST.get('cb-adroll', 'None'))
    
    # Filter the list to remove all None values (values where the check box passed no values a.k.a not selected services)
    new_kms_list = []
    for item in KMS_list:
        if (item != 'None'):
            new_kms_list.append(item)

    # Transform the list to a string of quoted chars for Javascript and a string of unquoted chars for django 
    # basically save the unquoted string in Django DB and pass the '' quoted string to Javascript for rendering
    # unquoted is used in scripttag.views for template rendering and DB MarketingService Details lookup
    KMS_quoted = '"' + '","'.join(new_kms_list) + '"'
    #KMS_unquoted = ','.join(new_kms_list)

    # Check if partners were changed this needs to be logged in installer.models.ShopDeatz.last_partner_change_datetime for rendering in dash
    ShopSettingsInst = ShopSettings.objects.get(shop_url=shop_url) 
    ShopMarketingInst = ShopMarketingServices.objects.get(shop_url=shop_url)
    if (KMS_quoted != ShopMarketingInst.known_services_list_quoted or 
            UMS_quoted != ShopMarketingInst.unknown_services_list):

        ShopDeatzInst.last_partner_change_datetime = datetime.datetime.now()
        ShopDeatzInst.save()

    else:
        pass

    # Save Settings Configuration in DB
    ShopSettingsInst.datapurpose_shipping = bool(cb_shipping)
    ShopSettingsInst.datapurpose_payproc = bool(cb_payproc)
    ShopSettingsInst.datapurpose_emarketing = bool(cb_emarketing)
    ShopSettingsInst.datapurpose_retar = bool(cb_retar)

    if storage_duration != False:
        ShopSettingsInst.storage_duration = int(storage_duration)
    if data_sharing != False:
        ShopSettingsInst.data_sharing = data_sharing
    if third_country != False:
        ShopSettingsInst.third_country = third_country

    ShopSettingsInst.save()

    ShopMarketingInst.known_services_list_quoted = KMS_quoted
    #ShopMarketingInst.known_services_list_unquoted = KMS_unquoted
    ShopMarketingInst.unknown_services_list = UMS_quoted
    ShopMarketingInst.save()

    # if omnisend is true, then switch configured ESP to omninisend 
    ESPInst = ESPCredentials.objects.get(shop_url=shop_url)
    if omnisend == 'True':
        ESPInst.configured_ESP = 'omnisend'
        ESPInst.esp_API_key = api_key 
        ESPInst.save()
    # This handles the case where api_key is modified without changeing Email Service Provider
    elif api_key != ESPInst.esp_API_key:
        ESPInst.esp_API_key = api_key 
        ESPInst.save()

    # Convert ip_filtering_status to boolean 
    if ip_filtering_status != 'True':
        ip_filtering_status = False
    else:
        ip_filtering_status = True

    # Unknown (Marketing) Partners
    final_uknownpartners_list = unknown_partner1_mrktng.split(',')

    # check if final_partners_list is empty if so then make its value == to default '-' representing empty DB entries
    if len(final_uknownpartners_list) == 0:
        final_uknownpartners_list.append('-')

    #print final_uknownpartners_list (Marketing)
    UMS_quoted_mrktng = '"' + '","'.join(final_uknownpartners_list) + '"'

    AdvancedSettingsInst = AdvancedSettings.objects.get(shop_url=shop_url)
    AdvancedSettingsInst.custom_consent_text = custom_consent_text
    AdvancedSettingsInst.unknown_marketing_list = UMS_quoted_mrktng
    AdvancedSettingsInst.ip_filtering_active = ip_filtering_status
    AdvancedSettingsInst.save()

    context = {
                   'SHOPIFY_API_KEY': settings.SHOPIFY_API_KEY,
                   'full_shop_url': construct_shop_url,
                   'active_advanced': 'ui-tertiary-navigation__link--is-active',
                   'UMS_list_mrktng': AdvancedSettingsInst.unknown_marketing_list.replace('"', '').replace(' ', ''),
                   'custom_consent_text': AdvancedSettingsInst.custom_consent_text,
                   'ip_filtering_status': 'checked' if str(AdvancedSettingsInst.ip_filtering_active) == 'True' else '',
                   'cb_shipping': 'checked' if str(ShopSettingsInst.datapurpose_shipping) == 'True' else '',
                   'cb_payproc': 'checked' if str(ShopSettingsInst.datapurpose_payproc) == 'True' else '',
                   'cb_emarketing': 'checked' if str(ShopSettingsInst.datapurpose_emarketing) == 'True' else '',
                   'cb_retar': 'checked' if str(ShopSettingsInst.datapurpose_retar) == 'True' else '',
                   'cb_google': 'checked' if '"cb-google"' in ShopMarketingInst.known_services_list_quoted else '',
                   'cb_facebook':'checked' if '"cb-facebook"' in ShopMarketingInst.known_services_list_quoted else '',
                   'cb_instagram': 'checked' if '"cb-instagram"' in ShopMarketingInst.known_services_list_quoted else '',
                   'cb_youtube': 'checked' if '"cb-youtube"' in ShopMarketingInst.known_services_list_quoted else '',
                   'cb_twitter': 'checked' if '"cb-twitter"' in ShopMarketingInst.known_services_list_quoted else '',
                   'cb_amazon': 'checked' if '"cb-amazon"' in ShopMarketingInst.known_services_list_quoted else '',
                   'cb_bing': 'checked' if '"cb-bing"' in ShopMarketingInst.known_services_list_quoted else '',
                   'cb_yahoo': 'checked' if '"cb-yahoo"' in ShopMarketingInst.known_services_list_quoted else '',
                   'cb_leadbolt': 'checked' if '"cb-leadbolt"' in ShopMarketingInst.known_services_list_quoted else '',
                   'cb_inmobi': 'checked' if '"cb-inmobi"' in ShopMarketingInst.known_services_list_quoted else '',
                   'cb_mopub': 'checked' if '"cb-mopub"' in ShopMarketingInst.known_services_list_quoted else '',
                   'cb_adroll': 'checked' if '"cb-adroll"' in ShopMarketingInst.known_services_list_quoted else '',
                   'storage_duration':str(ShopSettingsInst.storage_duration),
                   'data_sharing': ShopSettingsInst.data_sharing,
                   'third_country': ShopSettingsInst.third_country,
                   'UMS_list': ums_list.replace('"', '').replace(' ', ''),
                   'shop_url': shop_url,
                   'configured_ESP': ESPInst.configured_ESP,
                   'API_key': ESPInst.esp_API_key,
                   'scrolltodiv': scroll_to_div,
                   'page_title': 'Advanced Settings',
                  }
    return render(request, 'dashboard/advancedsettings.html', context)


# #################################################################################################################################
# EMAIL SERVICE PROVIDER OAUTH REGISTRATIONS
# #################################################################################################################################

# MAILCHIMP
# User merchant clicks MailChimp Login button in backend, he is prompted to enter their username and password to approve your application.
# The merchant is then redirected back to your redirect_uri (which points to the function below) as a GET requests with the code parameter.
# We capture the 'code' parameter passed via GET, and make a POST request to access_token_uri, which return an access_token and
# completes the official OAuth2 flow.We save that access token in dahsboard.models for later use when we want to use the api in gdpr/views
def mailchimpauth(request):

    access_token_uri = 'https://login.mailchimp.com/oauth2/token'
    metadata_uri = 'https://login.mailchimp.com/oauth2/metadata'

    client_id = '890417748037'
    client_secret = '62923e7965c52bd7a0a02ab7a3c721fd92f006644c09910a75'
    redirect_uri = 'https://cdn1.gdprinsider.ovh/mailchimpauth/'

    # Capture the value of code and state (which contains the shop_url)
    code = request.GET['code']
    shop_url = request.GET['state']  # This is rendered into the <login with MailChimp> button rendered in the GettingStarted.html template

    # Collect all the data you need to pass to access_token_uri to get your oauth token, in a dictionary called data
    data = {
            'grant_type': 'authorization_code',
            'client_id': client_id,
            'client_secret': client_secret,
            'redirect_uri': redirect_uri,  # Pass url that you setup in your MailChimp App Registration (no need for encoding it)
            'code': code
           }

    # Pass the the 'data' dict to access_token_uri using a POST request
    response = requests.post(access_token_uri, data=data)

    # Grab the JSON dictionary that is returned and extract access_token
    response_dict = response.json()  # Use the .json method to convert the {data:data} JSON dictionary returned into a Python dictionary
    access_token = response_dict['access_token']  # This is your OAuth token that you need to store for future use
    # print response.text

    # Now you need to make a RESTful request using an OAuth2 client to the metadata url, to obtain dc, login_url, and api_endpoint
    # No parameters are needed here its an empty GET request. The header is the where your access_token goes for this one
    headers = {
              'User-Agent': 'oauth2-app',
              'Host': 'login.mailchimp.com',
              'Accept': 'application/json',
              'Authorization': ('OAuth ' + access_token),  # Idiosyncracy, access_token needs to be preceeded by 'OAuth ' (with space)
             }
    
    # Send a get request with your headers created above as arguement, mailchimp will return a JSON dictionary
    response = requests.get(metadata_uri, headers=headers)
    # print response.text
    response_dict = response.json()  # Use the .json method to convert the {data:data} JSON dictionary returned into a Python dictionary
    data_center = response_dict['dc']
    api_endpoint = response_dict['api_endpoint']  # This is the endpoint to which you will be making your API calls in gdpr/views.py

    # print data_center, login_url, api_endpoint,

    # Save access_token to dashboard.models.MarketingServices DB
    ESPInst = ESPCredentials.objects.get(shop_url=shop_url)
    ESPInst.esp_username = 'GDPRComplianceApp'  # facultatif, can be anything
    ESPInst.esp_data_center = data_center
    ESPInst.esp_API_key = access_token
    ESPInst.esp_api_endpoint_url = api_endpoint
    ESPInst.configured_ESP = 'mailchimp'
    ESPInst.save()
    print "Done Registering ESP"

    # Send back to home view
    return redirect('https://cdn1.gdprinsider.ovh/')


@csrf_protect
def dp_activities(request):
    ###########################################################################################################
    # Shop Request Validation and Authentication
    #########################################################################################################

    # Since, the URL for this view is requested from within the iframe, it is no longer requested by shopify, but rather by your webserver.
    # It is as if the user was on our website requesting pages directly so shopify cannot add arguements to the requests.
    # As such, the 'shop' item is no longer passed by shopify in the request
    # So instead we will check for the session that we created in /index. If the user's browser has an active session for his store than let him
    # access this view. Otherwise block the request, and redirect the user to shopify login, where he can login to his store, and access the app
    # index page which will create a new session for him and then he can visit the page associated to this view using a valid django session
    try:
        # Step1: Check if the the user has valid session tokens
        shop_url = request.session['GDPRCOMPLIANCE360S']
        download_key = request.session['GDPRCOMPLIANCE360D']
    except Exception:
        return redirect('https://www.shopify.com/login')

    # Add switch to check if store exists in our registered store's DB. In case store does not exist in our DB, return HTTPBadRequest
    # if the store exists, it will make one further check to verify that the access token passed for the store corresponds to the one
    # we have in our DB. If it does it means that the request is legitimately comming from the store, if they don't match, then someone
    # could be attempting to forge fake sessionsi using the shop_url to access data (but he does not have the auth token)
    try:
        # Step2: Verify that shop_url from the session exists in DB,
        ShopDeatzInst = ShopDeatz.objects.get(shop_url=str(shop_url))

    # This Exception will help to stop Apache from bugging out in cases where you are making DB and API calls using non existant stores
    # i.e, when the db.sql is reinitialized while a store still has the app installed but is not present in local DB
    # or when no active session was found in the user's browser.
    except ObjectDoesNotExist:
        print 'Error: %s shop has app installed but is not present in the DB' %(shop_url)
        return redirect('https://www.shopify.com/login')

    # Step3 : Verify that the download key of the user's second session token matches that of the shop_url found in the user's first token
    if download_key == ShopDeatzInst.download_key:
        pass
    else:
        return redirect('https://www.shopify.com/login')

    # If all the above tests were passed, then activate your shopify session to make api calls
    session = shopify.Session(shop_url, ShopDeatzInst.auth_token)
    shopify.ShopifyResource.activate_session(session)

    ##########################################################################################################
    # View Code
    #########################################################################################################

    # At this point you can emit API calls directly without having to 'activate your session' because once the app is installed,
    # session activation is automatically done by the middleware

    # Capture data passed in URL (GET) if any
    download_key = request.GET.get('dkey', False)
    event_id = request.GET.get('delevent', False)
    page = request.GET.get('page', False)

    if download_key == ShopDeatzInst.download_key:
        try:
            AuditLogInst = DataEventLogger(shop_url)
            AuditLogInst.delete_event(event_id)
        except Exception:
            print 'Error while deleting event in dp_activities()'
            pass
    else:
        pass

    current_date = datetime.date.today()

    # Step1: get all data from database, using Auditlogger
    AuditLogInst = DataEventLogger(shop_url)
    result_list = AuditLogInst.get_hist_csv(datetime.date(2001, 1, 1), (current_date + datetime.timedelta(1)))
    # print result

    # Setup Pagination
    paginator = Paginator(result_list, 10) # Show 10 Results per page

    try:
        if page == False:
            page = 1
            result = paginator.page(1)
        else:
            result = paginator.page(page)
    except PageNotAnInteger:
        # If page is not an integer, deliver first page.
        result = paginator.page(1)
    except EmptyPage:
        # If page is out of range (e.g. 9999), deliver last page of results.
        result = paginator.page(paginator.num_pages)

    #print result

    context = {
                'SHOPIFY_API_KEY': settings.SHOPIFY_API_KEY,
                'full_shop_url': construct_shop_url,
                'download_key': ShopDeatzInst.download_key,
                'data_processing_activity_log': result,
                'page': page,
                'page_title': 'GDPR Audit Log',
              }

    return render(request, 'dashboard/dp_activities.html', context)


@csrf_protect
def dp_edit(request):
    ###########################################################################################################
    # Shop Request Validation and Authentication
    #########################################################################################################

    # Since, the URL for this view is requested from within the iframe, it is no longer requested by shopify, but rather by your webserver.
    # It is as if the user was on our website requesting pages directly so shopify cannot add arguements to the requests.
    # As such, the 'shop' item is no longer passed by shopify in the request
    # So instead we will check for the session that we created in /index. If the user's browser has an active session for his store than let him
    # access this view. Otherwise block the request, and redirect the user to shopify login, where he can login to his store, and access the app
    # index page which will create a new session for him and then he can visit the page associated to this view using a valid django session
    try:
        # Step1: Check if the the user has valid session tokens
        shop_url = request.session['GDPRCOMPLIANCE360S']
        download_key = request.session['GDPRCOMPLIANCE360D']
    except Exception:
        return redirect('https://www.shopify.com/login')

    # Add switch to check if store exists in our registered store's DB. In case store does not exist in our DB, return HTTPBadRequest
    # if the store exists, it will make one further check to verify that the access token passed for the store corresponds to the one
    # we have in our DB. If it does it means that the request is legitimately comming from the store, if they don't match, then someone
    # could be attempting to forge fake sessionsi using the shop_url to access data (but he does not have the auth token)
    try:
        # Step2: Verify that shop_url from the session exists in DB,
        ShopDeatzInst = ShopDeatz.objects.get(shop_url=str(shop_url))

    # This Exception will help to stop Apache from bugging out in cases where you are making DB and API calls using non existant stores
    # i.e, when the db.sql is reinitialized while a store still has the app installed but is not present in local DB
    # or when no active session was found in the user's browser.
    except ObjectDoesNotExist:
        print 'Error: %s shop has app installed but is not present in the DB' %(shop_url)
        return redirect('https://www.shopify.com/login')

    # Step3 : Verify that the download key of the user's second session token matches that of the shop_url found in the user's first token
    if download_key == ShopDeatzInst.download_key:
        pass
    else:
        return redirect('https://www.shopify.com/login')

    # If all the above tests were passed, then activate your shopify session to make api calls
    session = shopify.Session(shop_url, ShopDeatzInst.auth_token)
    shopify.ShopifyResource.activate_session(session)    

    ##########################################################################################################
    # View Code
    #########################################################################################################
    # If this is a page request and not a <POST> then 'submitted' key will not be present in request.POST, 
    # in this case just render the requested page
    if 'submitted' not in request.POST: 
        # Try to capture data passed in URL (GET) if any
        download_key = request.GET.get('dkey', False)
        event_id = request.GET.get('getdetails', False)

        if (download_key == ShopDeatzInst.download_key) and (event_id != False):
            try:
                AuditLogInst = DataEventLogger(shop_url)
                data_event_details = AuditLogInst.get_single_event_details(event_id)
            except Exception:
                print 'Error while getting single event_id details in dp_edit()'
                pass
        else:
            data_event_details = []
            context = {
                    'SHOPIFY_API_KEY': settings.SHOPIFY_API_KEY,
                    'full_shop_url': construct_shop_url,
                    'page_title': 'Edit GDPR Data Activity',
                    'eventdeatz': data_event_details,
                    'page_title': 'Edit GDPR Data Activity',
                  }

            return render(request, 'dashboard/dpo_edit.html', context)

        if len(data_event_details) > 0:
            # Tuples are immutable so to change the date format in place you first have to convert the tuple to a list
            # We change the date format here to a string that matches the format used by DatePicker in our html
            data_event_details = list(data_event_details)
            data_event_details[1] = data_event_details[1].strftime('%m/%d/%Y')
        else:
            pass

        context = {
                    'SHOPIFY_API_KEY': settings.SHOPIFY_API_KEY,
                    'full_shop_url': construct_shop_url,
                    'page_title': 'Edit GDPR Data Activity',
                    'eventdeatz': data_event_details,
                    'page_title': 'Edit GDPR Data Activity',
                  }

        return render(request, 'dashboard/dpo_edit.html', context)

    # Otherwise, this means the user is posting data (clcked the save button on dashboard), so continue with code execution to preocess data
    else:
        pass

    # Capture data passed in via POST
    event_id = request.POST.get('event_id', False)
    customer_id = request.POST.get('customer_id', False)
    date = request.POST.get('date', False)
    event_type = request.POST.get('event_type', False)
    legal_basis = request.POST.get('legal_basis', False)
    purpose = request.POST.get('purpose', False)
    description = request.POST.get('comment', False)
    status = request.POST.get('iCheck', False)

    print status


    if (status != "Pending") and (status != "Completed"):
        status = '-'
    else:
        pass

    # Convert date to MySQl format to update the record 
    date = datetime.datetime.strptime(date, '%m/%d/%Y')

    # Update the event in database, using Auditlogger.update_event
    AuditLogInst = DataEventLogger(shop_url)
    AuditLogInst.update_event(event_id, date, event_type, legal_basis, purpose, description, status)

    # Write modification time in installer.models.ShopDeatz and increase DPO Actions count by 1 
    # Export Count is wrongly named in reality it tracks down DPO actions
    ShopDeatzInst.last_exportdatetime = datetime.datetime.now()
    ShopDeatzInst.total_exports = ShopDeatzInst.total_exports + 1
    ShopDeatzInst.save()

    # Retrieve newly inserted modifications and re-render template
    data_event_details = AuditLogInst.get_single_event_details(event_id)
    # print data_event_details

    if len(data_event_details) > 0:
        # Tuples are immutable so to change the date format in place you first have to convert the tuple to a list
        # We change the date format here to a string that matches the format used by DatePicker in our html
        data_event_details = list(data_event_details)
        data_event_details[1] = data_event_details[1].strftime('%m/%d/%Y')
    else:
        pass

    context = {
                'SHOPIFY_API_KEY': settings.SHOPIFY_API_KEY,
                'full_shop_url': construct_shop_url,
                'eventdeatz': data_event_details,
                'page_title': 'Edit GDPR Data Activity',
              }

    return render(request, 'dashboard/dpo_edit.html', context)


@csrf_protect
def dp_create(request):
    ###########################################################################################################
    # Shop Request Validation and Authentication
    #########################################################################################################

    # Since, the URL for this view is requested from within the iframe, it is no longer requested by shopify, but rather by your webserver.
    # It is as if the user was on our website requesting pages directly so shopify cannot add arguements to the requests.
    # As such, the 'shop' item is no longer passed by shopify in the request
    # So instead we will check for the session that we created in /index. If the user's browser has an active session for his store than let him
    # access this view. Otherwise block the request, and redirect the user to shopify login, where he can login to his store, and access the app
    # index page which will create a new session for him and then he can visit the page associated to this view using a valid django session
    try:
        # Step1: Check if the the user has valid session tokens
        shop_url = request.session['GDPRCOMPLIANCE360S']
        download_key = request.session['GDPRCOMPLIANCE360D']
    except Exception:
        return redirect('https://www.shopify.com/login')

    # Add switch to check if store exists in our registered store's DB. In case store does not exist in our DB, return HTTPBadRequest
    # if the store exists, it will make one further check to verify that the access token passed for the store corresponds to the one
    # we have in our DB. If it does it means that the request is legitimately comming from the store, if they don't match, then someone
    # could be attempting to forge fake sessionsi using the shop_url to access data (but he does not have the auth token)
    try:
        # Step2: Verify that shop_url from the session exists in DB,
        ShopDeatzInst = ShopDeatz.objects.get(shop_url=str(shop_url))

    # This Exception will help to stop Apache from bugging out in cases where you are making DB and API calls using non existant stores
    # i.e, when the db.sql is reinitialized while a store still has the app installed but is not present in local DB
    # or when no active session was found in the user's browser.
    except ObjectDoesNotExist:
        print 'Error: %s shop has app installed but is not present in the DB' %(shop_url)
        return redirect('https://www.shopify.com/login')

    # Step3 : Verify that the download key of the user's second session token matches that of the shop_url found in the user's first token
    if download_key == ShopDeatzInst.download_key:
        pass
    else:
        return redirect('https://www.shopify.com/login')

    # If all the above tests were passed, then activate your shopify session to make api calls
    session = shopify.Session(shop_url, ShopDeatzInst.auth_token)
    shopify.ShopifyResource.activate_session(session)    

    ##########################################################################################################
    # View Code
    #########################################################################################################
    # If this is a page request and not a <POST> then 'submitted' key will not be present in request.POST, 
    # in this case just render the requested page
    if 'submitted' not in request.POST: 
 
        context = {
                    'SHOPIFY_API_KEY': settings.SHOPIFY_API_KEY,
                    'full_shop_url': construct_shop_url,
                    'page_title': 'Add GDPR Data Activity',
                  }

        return render(request, 'dashboard/dpo_create.html', context)

    # Otherwise, this means the user is posting data (clcked the save button on dashboard), so continue with code execution to preocess data
    else:
        pass

    # Capture data passed in via POST
    event_id = request.POST.get('event_id', False)
    customer_id = request.POST.get('customer_id', False)
    date = request.POST.get('date', False)
    event_type = request.POST.get('event_type', False)
    legal_basis = request.POST.get('legal_basis', False)
    purpose = request.POST.get('purpose', False)
    description = request.POST.get('comment', False)
    status = request.POST.get('iCheck', False)

    #print status

    if (status != "Pending") and (status != "Completed"):
        status = '-'
    else:
        pass

    # Convert date to MySQl format to update the record 
    date = datetime.datetime.strptime(date, '%m/%d/%Y')

    # Update the event in database, using Auditlogger.update_event
    AuditLogInst = DataEventLogger(shop_url)
    AuditLogInst.insert_data_processing_event(date, event_type, 'DPO Event', '-', description,\
                                                      customer_id, purpose, status, legal_basis)

    # Write creation time in installer.models.ShopDeatz and increase DPO Actions count by 1 
    # Export Count is wrongly named in reality it tracks down DPO actions
    ShopDeatzInst.last_exportdatetime = datetime.datetime.now()
    ShopDeatzInst.total_exports = ShopDeatzInst.total_exports + 1
    ShopDeatzInst.save()

    # Retrieve newly created modifications and re-render template
    data_event_details = AuditLogInst.get_new_added_event_details()
    # print data_event_details

    if len(data_event_details) > 0:
        # Tuples are immutable so to change the date format in place you first have to convert the tuple to a list
        # We change the date format here to a string that matches the format used by DatePicker in our html
        data_event_details = list(data_event_details)
        data_event_details[1] = data_event_details[1].strftime('%m/%d/%Y')
    else:
        pass

    context = {
                'SHOPIFY_API_KEY': settings.SHOPIFY_API_KEY,
                'full_shop_url': construct_shop_url,
                'eventdeatz': data_event_details,
                'page_title': 'Add GDPR Data Activity',
              }

    return render(request, 'dashboard/dpo_create.html', context)

