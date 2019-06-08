# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from django.shortcuts import render
from django.conf import settings
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
import geoip2.database
import shopify
from installer.models import ShopDeatz
from django.http import JsonResponse
import datetime
import re
from Crypto.Cipher import AES
from backendmodules.auditlogger import DataEventLogger
import boto3
from botocore.exceptions import ClientError
import os
from .models import RemovalConfirmationCodes, PopUpLanguageSupport
import string
import random
from django.core.exceptions import ObjectDoesNotExist
from .tasks import gdpr_removal
from dashboard.models import AdvancedSettings, ShopSettings
import unicodedata
#SENDGRID
import sendgrid
from sendgrid.helpers.mail import *


# Create your views here.
# ############################################################################################################################################
# #  Support Functions
# ############################################################################################################################################

def sql_sanitize(string_val):
    if isinstance(string_val, str):
        string_val = string_val.replace('/', '')
        string_val = string_val.replace('..', '')
        # create
        src_str = re.compile("create ", re.IGNORECASE)
        string_val = src_str.sub("", string_val)
        # insert
        src_str = re.compile("insert ", re.IGNORECASE)
        string_val = src_str.sub("", string_val)
        # update
        src_str = re.compile("update ", re.IGNORECASE)
        string_val = src_str.sub("", string_val)
        # drop
        src_str = re.compile("drop ", re.IGNORECASE)
        string_val = src_str.sub("", string_val)
        # select
        src_str = re.compile("select ", re.IGNORECASE)
        string_val = src_str.sub("", string_val)
        # delete
        src_str = re.compile("delete ", re.IGNORECASE)
        string_val = src_str.sub("", string_val)
        # alter
        src_str = re.compile("alter ", re.IGNORECASE)
        string_val = src_str.sub("", string_val)
        # show
        src_str = re.compile("show ", re.IGNORECASE)
        string_val = src_str.sub("", string_val)
        # load
        src_str = re.compile("load ", re.IGNORECASE)
        string_val = src_str.sub("", string_val)

        return string_val

    else:
        return string_val

def encrypt_ids(unenc_string):
    # Define your key and iv and create an instance of your cypher_suite using the key and iv
    crypto_key = 'XAkYgEDH18scLszwGGF1QJbm1Ao86T5Y'  # Must be 16 24 or 32 bytes long
    crypto_key = str(crypto_key)
    crypto_iv = '0f4s6shg6rSf6qER'  # Must be 16 bytes long
    crypto_iv = str(crypto_iv)
    cipher_suite = AES.new(str(crypto_key), AES.MODE_CBC, crypto_iv)

    # Check size of the string you want to encrypt because it must be a multiple of 16 chars in length
    # if it isnt then you need to add padding
    if len(unenc_string) % 16 != 0:
        padding_size = len(unenc_string) % 16
        # use $ for you padding because django usernames cannot contain $ (alphanumeric, _, @, +, . and - characters)
        # so you can easily do string.replace('$', '') later to get rid of the padding and keep only your unenc_string
        unenc_string = unenc_string + ('$' * (16 - padding_size))

    # Encrypt your unenc_string using your cypher_suite
    encrypted_id = cipher_suite.encrypt(unenc_string)
    # print "non hex = %r" % (encrypted_unenc_string)

    # You need to transform your encrypted cipher into 'hex'(normal letters ex. Dejf4er5sde) to be able to use it in django
    encrypted_id = encrypted_id.encode('hex')
    # print "hex = %r " % (encrypted_id.decode('hex'))

    # return your encrypted round_id and the size of padding that you add so it can be removed when we get the unenc_string back
    return encrypted_id 


#######################################################################################################################
# This view is used for checking IP address, it works like an API and is queried by the JS script
# The URL end-point is ipcheck/
#######################################################################################################################
def ipcheck(request):

    shop_url = request.GET.get('shop', False)

    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')

    print ip

    IP_Database_loc = settings.BASE_DIR + '/ipdatabase/GeoLite2-City.mmdb'

    # This creates a Reader object. You should use the same object
    # across multiple requests as creation of it is expensive.
    reader = geoip2.database.Reader(IP_Database_loc)

    try:
        # Create Advanced Settings Instance to check for custom_consent_text
        AdvancedSettingsInst = AdvancedSettings.objects.get(shop_url=shop_url)
        
        # Replace "city" with the method corresponding to the database
        # that you are using, e.g., "country".
        response = reader.city(ip)

        # fetch the .country.name attribute
        country = response.country.name

    except Exception:
        country = 'unknown'

    # Block to check if ip filtering option has been deactivated in Advanced Settings
    # if ip filtering has been deactivated set country = 'ip_filtering_deactivated' else do nothing
    if AdvancedSettingsInst.ip_filtering_active == False:
        country = 'ip_filtering_deactivated'
    else:
        pass

    # print out final contents of country
    print country

    if country == 'Morocco':
        country = 'France'


    # Check if country is in EU country list
    eu_country_list = [
                       'Austria', 'Italy', 'Belgium', 'Latvia', 'Bulgaria', 'Lithuania', 'Croatia', 'Republic of Lithuania',
                       'Luxembourg', 'Cyprus', 'Malta', 'Czech Republic', 'Netherlands', 'Czechia',
                       'Denmark', 'Poland', 'Estonia', 'Portugal', 'Finland', 'Romania',
                       'France', 'Slovakia', 'Germany', 'Slovenia', 'Greece', 'Spain',
                       'Hungary', 'Sweden', 'Ireland', 'United Kingdom', 'ip_filtering_deactivated'
                      ]
    
    language_dict = {
                      'Austria': 'german', 'Italy': 'italian', 'Belgium': 'french', 'Latvia': 'english', 'Bulgaria': 'english', 
                      'Lithuania': 'english', 'Croatia': 'english', 'Republic of Lithuania': 'english', 'Luxembourg': 'french', 
                      'Cyprus': 'english', 'Malta': 'english', 'Czech Republic': 'english', 'Netherlands': 'english', 'Czechia': 'english',
                      'Denmark': 'english', 'Poland': 'english', 'Estonia': 'english', 'Portugal': 'english', 'Finland': 'english', 
                      'Romania': 'english', 'France': 'french', 'Slovakia': 'english', 'Germany': 'german', 'Slovenia': 'english', 
                      'Greece': 'english', 'Spain': 'spanish', 'Hungary': 'english', 'Sweden': 'english', 'Ireland': 'english', 
                      'United Kingdom': 'english', 'Morocco': 'english', 'ip_filtering_deactivated': 'english'
                    }


    if (country in eu_country_list) and (AdvancedSettingsInst.custom_consent_text == ''):
        # Create an instance of PopUpLanguageSupport to extract correct language based on language_dict keys/values 
        PopUpTextInst = PopUpLanguageSupport.objects.get(language=language_dict[country])

        # Setup  storage duration text based on data in dashboard.models.ShopSettings() 
        ShopSettingsInst = ShopSettings.objects.get(shop_url=shop_url)
        storage_duration = ShopSettingsInst.storage_duration

        if storage_duration > 0:
            duration_text = PopUpTextInst.duration_wrapper1 + ' ' + str(storage_duration) + ' ' + PopUpTextInst.duration_wrapper2
        else:
            duration_text = PopUpTextInst.duration_undetermined
        
        # Get store canonical name from ShopDeatz model
        ShopDeatzInst = ShopDeatz.objects.get(shop_url=shop_url)
        shop_name = ShopDeatzInst.shop_name

        # Create JSON response containing the corresponding language consent message
        countrytext = {
                        'eu_flag': 'True',
                        'store_name': shop_name,
                        'consent_line1': PopUpTextInst.consent_line1,
                        'consent_line2': PopUpTextInst.consent_line2,
                        'consent_line3a': PopUpTextInst.consent_line3a,
                        'consent_line3b': duration_text,
                        'consent_line3c': PopUpTextInst.consent_line3c,
                        'consent_line3d': PopUpTextInst.consent_line3d,
                        'consent_line3e': PopUpTextInst.consent_line3e,
                        'consent_line4a': PopUpTextInst.consent_line4a,
                        'consent_line4b': PopUpTextInst.consent_line4b,
                        'consent_line5': PopUpTextInst.consent_line5,
                        'consent_line6': PopUpTextInst.consent_line6,
                        'consent_line7': PopUpTextInst.consent_line7,
                        'datareq_line1': PopUpTextInst.datareq_line1,
                        'datareq_line2': PopUpTextInst.datareq_line2,
                        'datareq_line3': PopUpTextInst.datareq_line3,
                        'datareq_line4': PopUpTextInst.datareq_line4,
                        'datareq_line5': PopUpTextInst.datareq_line5,
                        'datareq_line6': PopUpTextInst.datareq_line6,
                        'partners_line1': PopUpTextInst.partners_line1,
                        'partners_line2': PopUpTextInst.partners_line2,
                        'partners_line3': PopUpTextInst.partners_line3,
                        'button_decline': PopUpTextInst.button_action_decline,
                        'button_wrongrequest': PopUpTextInst.button_action_wrongrequest,
                        'button_submit': PopUpTextInst.button_action_submit,
                        'country': country,
                        'tabtitle1': PopUpTextInst.tabtitle1,
                        'tabtitle2': PopUpTextInst.tabtitle2,
                        'tabtitle3': PopUpTextInst.tabtitle3,
                        'tabtitle4': PopUpTextInst.tabtitle4,
                       }
    
    elif (country in eu_country_list) and (AdvancedSettingsInst.custom_consent_text != ''):
        # Create an instance of PopUpLanguageSupport to extract correct language based on language_dict keys/values 
        PopUpTextInst = PopUpLanguageSupport.objects.get(language=language_dict[country])

        # Create JSON response containing the corresponding language consent message
        countrytext = {
                        'eu_flag': 'True',
                        'store_name': '',
                        'consent_line1': PopUpTextInst.consent_line1,
                        'consent_line2': AdvancedSettingsInst.custom_consent_text,
                        'consent_line3a': '',
                        'consent_line3b': '',
                        'consent_line3c': '',
                        'consent_line3d': '',
                        'consent_line3e': '',
                        'consent_line4a': "",
                        'consent_line4b': PopUpTextInst.consent_line4b,
                        'consent_line5': PopUpTextInst.consent_line5,
                        'consent_line6': PopUpTextInst.consent_line6,
                        'consent_line7': PopUpTextInst.consent_line7,
                        'datareq_line1': PopUpTextInst.datareq_line1,
                        'datareq_line2': PopUpTextInst.datareq_line2,
                        'datareq_line3': PopUpTextInst.datareq_line3,
                        'datareq_line4': PopUpTextInst.datareq_line4,
                        'datareq_line5': PopUpTextInst.datareq_line5,
                        'datareq_line6': PopUpTextInst.datareq_line6,
                        'partners_line1': PopUpTextInst.partners_line1,
                        'partners_line2': PopUpTextInst.partners_line2,
                        'partners_line3': PopUpTextInst.partners_line3,
                        'button_decline': PopUpTextInst.button_action_decline,
                        'button_wrongrequest': PopUpTextInst.button_action_wrongrequest,
                        'button_submit': PopUpTextInst.button_action_submit,
                        'country': country,
                       }

    # If country is not in the list then return eu_flag false so JS script can know not to dispay the pop-up
    else:
        countrytext = {'eu_flag': 'False'}

    # print JsonResponse(countrytext)

    # Transform your countrytext python dictionnary into a Json object and return it to the JS script that initiated the request for parsing
    return JsonResponse(countrytext)


#######################################################################################################################
# Function to send email with confirmation code
#######################################################################################################################
def gdpr_removal_send_email(removal_request_email, shop_url, referringpage, country):
    request_date = datetime.date.today().strftime('%B %d %Y')

    # Create and Activate session for API calls
    ShopDeatzInst = ShopDeatz.objects.get(shop_url=shop_url)
    session = shopify.Session(shop_url, ShopDeatzInst.auth_token)
    shopify.ShopifyResource.activate_session(session)

    # Gets an object that contains all the shop info eqvalent to GET endpoint /admin/shop.json
    shop_info = shopify.Shop.current()
    
    # Make customer instance to check if customer email exists customer deatails (returns a list so use the first one)
    search_query = 'email:' + str(removal_request_email)
    CustomerInst = shopify.Customer.search(q=search_query)

    if len(CustomerInst) <= 0:
        # ##############################################################
        # Log INVALID Data Removal in Audit Table (All times are in UTC)
        # ##############################################################
        current_datetime = datetime.datetime.now()
        action = 'Invalid Data Removal Request'
        method = 'Data Removal Form'
        comment = 'Email does not correspond to any record in the database. No data removed.' 
        customer_id = 'Unregistered Customer'
        marketing_consent = '-'
        status = 'Completed'
        legal_basis = '-'
        purpose = '-'

        # Create AuditLog Instance 
        AuditLogInst = DataEventLogger(shop_url)

        # Add Data Removal Entry line
        AuditLogInst.insert_data_processing_event(current_datetime, action, method, referringpage, comment,\
                                                      customer_id, purpose, status, legal_basis)
        return 0

    else:
        pass

    # Generate 101 character random string confirmation code
    confirmation_code = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(101))

    # Check if removal_email exists in RemovalConfirmationCodes in the database for this user 
    # (because user might have clciked multiple times on the delete link by mistake which would generate new entries in the DB)
    # if it exists then just change the confirmation code, otherwise write a new entry for the user email
    try:
        ConfirmationCodesInst = RemovalConfirmationCodes.objects.get(removal_request_email=removal_request_email)
        ConfirmationCodesInst.confirmation_code = confirmation_code
        ConfirmationCodesInst.save()
    except ObjectDoesNotExist: 
        ConfirmationCodesInst = RemovalConfirmationCodes()
        ConfirmationCodesInst.confirmation_code = confirmation_code
        ConfirmationCodesInst.removal_request_email = removal_request_email
        ConfirmationCodesInst.save()
   
    removal_link = "https://cdn1.gdprinsider.ovh/dataevent/?" + "requesttype=confirmremoval" + "&shopurl=" + shop_url \
                     + "&email=" + removal_request_email + "&country=" + country + "&confirm=" + confirmation_code

    SENDER = str(shop_info.name) +  "<dataofficer@gdprdynamics.com>"
    
    # Replace recipient@example.com with a "To" address. If your account 
    RECIPIENT = str(removal_request_email)

    # If necessary, replace us-west-2 with the AWS Region you're using for Amazon SES.
    AWS_REGION = "eu-west-1" 

    # The email body for recipients with non-HTML email clients.
    BODY_TEXT = (
                 "Hi there,\r\n"
                 "In response to your subject data removal request received on %s, please click the following link to "
                 "complete your data removal process.\r\n"
                 "%s \r\n"
                 "Please note that your data will be purged from our store's system and that we will no longer have any trace of "
                 "your customer details and purchase history. As such, you will no longer be entitled to any refunds or product exchanges.\r\n"
                 "Thank you for your inquiry.\r\n"
                 "Regards,\r\n"
                 "%s"
                ) %(
                    request_date,
                    removal_link,
                    str(shop_info.name)
                   )

    # print BODY_TEXT

    ###############################################
    # The HTML body of the email.
    ###############################################
    # FRENCH EMAIL TEMPLATE
    if country == 'France':
        # The subject line for the email.
        SUBJECT = str(shop_info.name) + " - GDPR Demande de Suppression de Données"
        
        # Create French format request_date
        request_date = datetime.date.today().strftime('%d/%m/%Y')

        # Get  content of html template
        template_relative_location = 'templates/emailtemplates/data_del_FR.html'
        filelocation = os.path.join(settings.BASE_DIR, template_relative_location)
        BODY_HTML = ""
        for line in open(filelocation):
            new_line = unicode(line.decode("utf-8"))
            new_line = new_line.rstrip('\n')
            # print new_line
            BODY_HTML = BODY_HTML + new_line
    
    # ALL OTHER (ENGLISH EMAIL TEMPLATE)
    else:
        # The subject line for the email.
        SUBJECT = str(shop_info.name) + " - GDPR Data Removal Request"

        # Get content of html template
        template_relative_location = 'templates/emailtemplates/data_del.html' 
        filelocation = os.path.join(settings.BASE_DIR, template_relative_location)
        BODY_HTML = ""
        for line in open(filelocation):
            new_line = line.rstrip('\n')
            # print new_line
            BODY_HTML = BODY_HTML + new_line

    # Replace content
    BODY_HTML = BODY_HTML.replace('#STORENAME#', str(shop_info.name))
    BODY_HTML = BODY_HTML.replace('#REQUESTDATE#', request_date)
    BODY_HTML = BODY_HTML.replace('#DATAREMOVELINK#', removal_link)
    
    # print '\n'
    # print '#####################################################################'
    # print BODY_HTML

    # The character encoding for the email.
    CHARSET = "UTF-8"

    ###########################################################
    # EMAIL SENDING CODE BLOCK
    ###########################################################
    # Try to send the email.
    try:
        # Select the email sending service to use SendGrid or Amazon depending on value of settings.ACTIVE_TRANSACTIONALEMAIL_SERVICE
        if settings.ACTIVE_TRANSACTIONALEMAIL_SERVICE == 'AMAZON':
            # Create a new SES resource and specify a region.
            client = boto3.client(
                                  'ses',
                                  region_name=AWS_REGION,
                                  aws_access_key_id=settings.aws_id,
                                  aws_secret_access_key=settings.aws_secret
                                 )

            #Provide the contents of the email.
            response = client.send_email(
                Destination={
                    'ToAddresses': [
                        RECIPIENT,
                    ],
                },
                Message={
                    'Body': {
                        'Html': {
                            'Charset': CHARSET,
                            'Data': BODY_HTML,
                        },
                        'Text': {
                            'Charset': CHARSET,
                            'Data': BODY_TEXT,
                        },
                    },
                    'Subject': {
                        'Charset': CHARSET,
                        'Data': SUBJECT,
                    },
                },
                Source=SENDER,
                # If you are not using a configuration set, comment or delete the
                # following line
                #ConfigurationSetName=CONFIGURATION_SET,
            )

        elif settings.ACTIVE_TRANSACTIONALEMAIL_SERVICE == 'SENDGRID':
            sg = sendgrid.SendGridAPIClient(apikey=settings.SENDGRID_API_KEY)
            from_email = Email(email="dataofficer@transactional.gdprdynamics.com", name=str(shop_info.name))
            to_email = Email(RECIPIENT)
            subject = SUBJECT
            content = Content("text/html", BODY_HTML)
            mail = Mail(from_email, subject, to_email, content)
            response = sg.client.mail.send.post(request_body=mail.get())
            print(response.status_code)
            print(response.body)
            print(response.headers)

    # Display an error if something goes wrong. 
    except ClientError as e:
        print ("ERROR - Failed to send email to %s") %(RECIPIENT)
        print(e.response.status_code)
    else:
        print("Email sent! Message ID:")
        print(response.status_code)
    
        # #######################################################
        # Log Data Removal in Audit Table (All times are in UTC)
        # #######################################################
        current_datetime = datetime.datetime.now()
        action = 'Data Removal Request'
        method = 'Data Removal Form'
        comment = 'Confirmation link sent via email to the address on record.'
        customer_id = CustomerInst[0].id
        marketing_consent = CustomerInst[0].accepts_marketing
        status = 'Completed'
        if marketing_consent is True:
            legal_basis = 'Preparing or Performing a Contract (Product Sales) and Consent (Granted for Marketing)'
            purpose = 'Ecommerce - Processing Customer Purchases and Marketing'
        else:
            legal_basis = 'Preparing or Performing a Contract (Product Sales)'
            purpose = 'Ecommerce - Processing Customer Purchases'

        # Create AuditLog Instance 
        AuditLogInst = DataEventLogger(shop_url)

        # Add Data Removal Entry line
        AuditLogInst.insert_data_processing_event(current_datetime, action, method, referringpage, comment,\
                                                      customer_id, purpose, status, legal_basis)

    return 0


#######################################################################################################################
# Function to send the user a copy of his data via email
#######################################################################################################################
def gdpr_copy(copy_request_email, shop_url, referringpage, country):

    request_date = datetime.date.today().strftime('%B %d %Y')

    # Create and Activate session for API calls
    ShopDeatzInst = ShopDeatz.objects.get(shop_url=shop_url)
    session = shopify.Session(shop_url, ShopDeatzInst.auth_token)
    shopify.ShopifyResource.activate_session(session)

    # Gets an object that contains all the shop info eqvalent to GET endpoint /admin/shop.json
    shop_info = shopify.Shop.current()

    # Make customer instance to extract customer deatails (returns a list so use the first one)
    # .find() will not work on Customers using params, Search queries are only available on the Customer resource as a separate .search() method
    # This is because to search, you need to access a different endpont not /admin/customers.json but rather /admin/customers/search.json
    search_query = 'email:' + str(copy_request_email)
    CustomerInst = shopify.Customer.search(q=search_query)

    if len(CustomerInst) <= 0:
        # ##############################################################
        # Log INVALID Data Access in Audit Table (All times are in UTC)
        # ##############################################################
        current_datetime = datetime.datetime.now()
        action = 'Invalid Data Access Request'
        method = 'Data Access Form'
        comment = 'Email does not correspond to any record in the database. No data transmitted.'
        customer_id = 'Unregistered Customer'
        marketing_consent = '-'
        status = 'Completed'
        legal_basis = '-'
        purpose = '-'

        # Create AuditLog Instance 
        AuditLogInst = DataEventLogger(shop_url)

        # Add Data Removal Entry line
        AuditLogInst.insert_data_processing_event(current_datetime, action, method, referringpage, comment,\
                                                      customer_id, purpose, status, legal_basis)
        return 0

    else:
        pass

    SENDER = str(shop_info.name) +  "<dataofficer@gdprdynamics.com>"

    # Replace recipient@example.com with a "To" address. If your account 
    RECIPIENT = str(copy_request_email)

    # If necessary, replace us-west-2 with the AWS Region you're using for Amazon SES.
    AWS_REGION = "eu-west-1" 

    # The email body for recipients with non-HTML email clients.
    BODY_TEXT = ("Hi there,\r\n"
                 "In response to your subject data access request received on %s, "
                 "please find below the requested copy of your personal data.\r\n"
                 '---------------------------------------------\r\n'
                 'Email: %s\r\n'
                 'First Name: %s\r\n'
                 'Last Name: %s\r\n'
                 'Phone: %s\r\n'
                 'Company: %s\r\n'
                 'Address: %s\r\n'
                 'Address: %s\r\n'
                 'City: %s\r\n'
                 'Province: %s\r\n'
                 'Country: %s\r\n' 
                 '---------------------------------------------\r\n'
                 "As per European General Data Protection Regulation, you may rectify this data at any time by "
                 "loging in to your shop account. Alternatively, you can request data removal by clicking the data "
                 "icon at the bottom of the store's pages.\r\n"
                 "Thank you for your inquiry.\r\n"
                 "Regards,\r\n"
                 "%s"

                ) %(
                    request_date,
                    str(CustomerInst[0].email),
                    str(CustomerInst[0].first_name),
                    str(CustomerInst[0].last_name),
                    str(CustomerInst[0].phone),
                    str(CustomerInst[0].addresses[0].company),
                    str(CustomerInst[0].addresses[0].address1),
                    str(CustomerInst[0].addresses[0].address2),
                    str(CustomerInst[0].addresses[0].city),
                    str(CustomerInst[0].addresses[0].province),
                    str(CustomerInst[0].addresses[0].country),
                    str(shop_info.name)
                   )

    # print BODY_TEXT
    #############################################
    # The HTML body of the email.
    #############################################

    # FRENCH EMAIL TEMPLATE
    if country == 'France':
        # The subject line for the email.
        SUBJECT = str(shop_info.name) + " - GDPR Demande de Copie de Données"

        # Create French format request_date
        request_date = datetime.date.today().strftime('%d/%m/%Y')

        # Get  content of html template
        template_relative_location = 'templates/emailtemplates/data_copy_FR.html'
        filelocation = os.path.join(settings.BASE_DIR, template_relative_location)
        BODY_HTML = ""
        for line in open(filelocation):
            new_line = unicode(line.decode("utf-8"))
            new_line = new_line.rstrip('\n')
            # print unicodedata.normalize('NFKD', new_line).encode('utf-8','ignore')
            BODY_HTML = BODY_HTML + new_line

    # ALL OTHERS (ENGLISH EMAIL TEMPLATE)
    else:
        # The subject line for the email.
        SUBJECT = str(shop_info.name) + " - GDPR Data Access Request"

        template_relative_location = 'templates/emailtemplates/data_copy.html'
        filelocation = os.path.join(settings.BASE_DIR, template_relative_location)
        BODY_HTML = ""
        for line in open(filelocation):
            new_line = line.rstrip('\n')
            BODY_HTML = BODY_HTML + new_line

    # replace content of template
    BODY_HTML = BODY_HTML.replace('#STORENAME#', str(shop_info.name))
    BODY_HTML = BODY_HTML.replace('#REQUESTDATE#', request_date)
    BODY_HTML = BODY_HTML.replace('#EMAIL#', str(CustomerInst[0].email))
    BODY_HTML = BODY_HTML.replace('#FNAME#', str(CustomerInst[0].first_name))
    BODY_HTML = BODY_HTML.replace('#LNAME#', str(CustomerInst[0].last_name))
    BODY_HTML = BODY_HTML.replace('#PHONE#', str(CustomerInst[0].phone))
    BODY_HTML = BODY_HTML.replace('#COMPANY#', str(CustomerInst[0].addresses[0].company))
    BODY_HTML = BODY_HTML.replace('#ADDRESS1#', str(CustomerInst[0].addresses[0].address1))
    BODY_HTML = BODY_HTML.replace('#ADDRESS2#', str(CustomerInst[0].addresses[0].address2))
    BODY_HTML = BODY_HTML.replace('#CITY#', str(CustomerInst[0].addresses[0].city))
    BODY_HTML = BODY_HTML.replace('#PROVINCE#', str(CustomerInst[0].addresses[0].province))
    BODY_HTML = BODY_HTML.replace('#COUNTRY#', str(CustomerInst[0].addresses[0].country))
    BODY_HTML = BODY_HTML.replace('#ZIP#', str(CustomerInst[0].addresses[0].zip))

    # print '\n'
    # print '#####################################################################'
    # print BODY_HTML

    # The character encoding for the email.
    CHARSET = "UTF-8"


    ###########################################################
    # EMAIL SENDING CODE BLOCK
    ###########################################################
    # Try to send the email.
    try:
        # Select the email sending service to use SendGrid or Amazon depending on value of settings.ACTIVE_TRANSACTIONALEMAIL_SERVICE
        if settings.ACTIVE_TRANSACTIONALEMAIL_SERVICE == 'AMAZON':
            # Create a new SES resource and specify a region.
            client = boto3.client(
                                  'ses',
                                  region_name=AWS_REGION,
                                  aws_access_key_id=settings.aws_id,
                                  aws_secret_access_key=settings.aws_secret
                                 )

            #Provide the contents of the email.
            response = client.send_email(
                Destination={
                    'ToAddresses': [
                        RECIPIENT,
                    ],
                },
                Message={
                    'Body': {
                        'Html': {
                            'Charset': CHARSET,
                            'Data': BODY_HTML,
                        },
                        'Text': {
                            'Charset': CHARSET,
                            'Data': BODY_TEXT,
                        },
                    },
                    'Subject': {
                        'Charset': CHARSET,
                        'Data': SUBJECT,
                    },
                },
                Source=SENDER,
                # If you are not using a configuration set, comment or delete the
                # following line
                #ConfigurationSetName=CONFIGURATION_SET,
            )

        elif settings.ACTIVE_TRANSACTIONALEMAIL_SERVICE == 'SENDGRID':
            sg = sendgrid.SendGridAPIClient(apikey=settings.SENDGRID_API_KEY)
            from_email = Email(email="dataofficer@transactional.gdprdynamics.com", name=str(shop_info.name))
            to_email = Email(RECIPIENT)
            subject = SUBJECT
            content = Content("text/html", BODY_HTML)
            mail = Mail(from_email, subject, to_email, content)
            response = sg.client.mail.send.post(request_body=mail.get())
            print(response.status_code)
            print(response.body)
            print(response.headers)
    
    # Display an error if something goes wrong. 
    except ClientError as e:
        print ("ERROR - Failed to send email to %s") %(RECIPIENT)
        print(e.response.status_code)
    else:
        print("Email sent! Message ID:"),
        print(response.status_code)

        # #######################################################
        # Log Data Access in Audit Table (All times are in UTC)
        # #######################################################
        current_datetime = datetime.datetime.now()
        action = 'Data Access Request'
        method = 'Data Access Form'
        comment = 'Requested data transmitted via email to the address on record.'
        customer_id = CustomerInst[0].id
        marketing_consent = CustomerInst[0].accepts_marketing
        status = 'Completed'
        if marketing_consent is True:
            legal_basis = 'Preparing or Performing a Contract (Product Sales) and Consent (Granted for Marketing)'
            purpose = 'Ecommerce - Processing Customer Purchases and Marketing'
        else:
            legal_basis = 'Preparing or Performing a Contract (Product Sales)'
            purpose = 'Ecommerce - Processing Customer Purchases'

        # Create AuditLog Instance 
        AuditLogInst = DataEventLogger(shop_url)

        # Add Data Removal Entry line
        AuditLogInst.insert_data_processing_event(current_datetime, action, method, referringpage, comment,\
                                                      customer_id, purpose, status, legal_basis)
        return 0

#######################################################################################################################
# Function Add Consent Granted to DB
#######################################################################################################################
def gdpr_consent(shop_url, referringpage):
    # Create a unique encrypted ID for this removal to write in Audit Log and address2 line
    removal_id_str = datetime.datetime.now().strftime('%B-%d-%Y %H:%M:%S') + 'consent'
    dataevent_id = encrypt_ids(removal_id_str)

    # #######################################################
    # Log Data Removal in Audit Table (All times are in UTC)
    # #######################################################
    current_datetime = datetime.datetime.now() 
    action = 'Data Consent'
    method = 'Consent Form "Accept Button"'
    comment = 'Data subject granted consent to data collection for the purpose of marketing.'
    status = 'Completed'
    legal_basis = 'Preparing or Performing a Contract (Product Sales) and Consent (Granted for Marketing)'
    purpose = 'Ecommerce - Processing Customer Purchases and Marketing'
    customer_id= 'Unregistered Customer'

    # Create AuditLog Instance 
    AuditLogInst = DataEventLogger(shop_url)
    # Add Consent Granted Entry line
    AuditLogInst.insert_data_processing_event(current_datetime, action, method, referringpage, comment,\
                                                customer_id, purpose, status, legal_basis)

#######################################################################################################################
# Data request dispatcher calls either gdpr_removal() or gdpr_copy()
#######################################################################################################################
@csrf_exempt
def gdpr_request(request):
    print 'GDPR REQUEST Endpoint Function'
    # Get the email address associated to the customer who want to be removed
    # And URL of the shop where the request came from
    request_type = request.POST.get('requesttype', False)
    email = sql_sanitize(request.POST.get('email', False))
    shop_url = sql_sanitize(request.POST.get('shopurl', False))
    referringpage = sql_sanitize(request.META.get('HTTP_REFERER', '-'))
    country = sql_sanitize(request.POST.get('country', False))

    print request.POST

    # If requesttype is not in POST then check in GET, in case we are dealing with a removal confirmation email 
    if request_type == False:
        request_type = sql_sanitize(request.GET.get('requesttype', False))
        confirmation_code = sql_sanitize(request.GET.get('confirm', False))
        email = sql_sanitize(request.GET.get('email', False))
        shop_url = sql_sanitize(request.GET.get('shopurl', False))
        country = sql_sanitize(request.GET.get('country', False))

    # Make sure that the shop exists in our DB before doin any further work
    try:
        ShopDeatzInst = ShopDeatz.objects.get(shop_url=shop_url)
    except ObjectDoesNotExist:
        return HttpResponse('')

    print request_type, email, shop_url

    if (request_type == 'reqdel') and (email != False):
        #try:
        print 'removal request sending email...'
        gdpr_removal_send_email(email, shop_url, referringpage, country) 
        #except Exception:
        #print 'Error Occured While Processing GDPR Remove Request'
 
    elif (request_type == 'reqcopy') and (email != False):
        #try:
        print 'copy request processing...'
        gdpr_copy(email, shop_url, referringpage, country)
        #except Exception:
        #print 'Error Occured While Processing GDPR Remove Request'

    elif (request_type == 'consentaccept'):
        print 'consent request processing...'
        gdpr_consent(shop_url, referringpage)

    elif (request_type == 'confirmremoval'):
        print 'removal request confirmation processing...'
        # remove subject's data and return removal confirmation page based on country 
        if country == 'France':
            gdpr_removal.delay(email, confirmation_code, shop_url, referringpage)
            return render(request, 'emailtemplates/removalconfirmation_FR.html', {})
        else:
            gdpr_removal.delay(email, confirmation_code, shop_url, referringpage)
            return render(request, 'emailtemplates/removalconfirmation.html', {})
    else:
        print 'Invalid Data Request - gdpr/views.py => gdpr_request() function'

    return HttpResponse('')


