from celery import task
import datetime
import shopify
from backendmodules.auditlogger import DataEventLogger
from installer.models import ShopDeatz, InstallTracker
from .models import RemovalConfirmationCodes, RemovalQueue
from dashboard.models import ESPCredentials
import hashlib
import requests
from django.core.exceptions import ObjectDoesNotExist
from Crypto.Cipher import AES
import dateutil.parser
import sendgrid
from sendgrid.helpers.mail import *
import os
from django.conf import settings
import dateutil.parser
import pytz


# Support function used to create dataevent_ids
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


# This task runs periodically. once per  day @ 1am UTC
# Look for all data that was collected by the store within the prevous day
@task
def newly_regestered_data():
    #####################################################
    # New Data Collected (insert multiple rows @ once)
    ####################################################
    # Get a list of all shops
    ShopDeatzInst = ShopDeatz.objects.all()

    # Extract individual objects from object list, to get their urls and create a store session to send API calls
    for Store in ShopDeatzInst:
        shop_url = Store.shop_url
        auth_token = Store.auth_token

        # Create and activate store session to retrieve cutomer list
        session = shopify.Session(shop_url, auth_token)
        shopify.ShopifyResource.activate_session(session)

        current_datetime = datetime.datetime.now()

        # This cron runs at 1am and gets a list of customers who's details were updated between last_import_datetime and current_datetime
        start_datetime = Store.last_import_datetime.strftime("%Y-%m-%dT%H:%M:%S") + '-00:00' 
        end_datetime = current_datetime.strftime("%Y-%m-%dT%H:%M:%S") + '-00:00'  # format: 2014-04-25T16:15:47-04:00

        print start_datetime
        print end_datetime

        # Get Customer list
        # .find() works here because the updated_at_min param access the top-level endoint /admin/customers.json NOT /admin/customers/search.json 
        customer_list = shopify.Customer.find(updated_at_min=start_datetime, updated_at_max=end_datetime)  # Find with no params gets all (Returns a list)

        # Create AuditLog instance to insert customers
        AuditLogInst = DataEventLogger(shop_url)

        # Concatenate customers into multiple VALUE clauses to minimize insertion time and cpu load
        sql_query_values = ''
        total_counter = 0
        set_counter = 0
        for customer in customer_list:
            total_counter += 1
            set_counter += 1
            if (customer.id != '') and (customer.id != None):
                customer_id = customer.id
            else:
                customer_id = str(customer.id)

            # In Case this is an intial data creation
            if customer.created_at == customer.updated_at:
 
                # Convert ISO 8601 string date and time to python datetime object
                creation_datetime = dateutil.parser.parse(customer.created_at)

                # Convert datetime object back to UTC time (in case there is a timezon offset)
                date = creation_datetime.astimezone(pytz.utc)

                action = 'Data Collection'
                method = 'Data Collection Form'
                referringpage = ''
                comment = 'Personal details provided by data subject were collected and stored in the customer database.'

                customer_id = customer.id
                marketing_consent = customer.accepts_marketing
                status = 'Completed'
                if marketing_consent is True:
                    legal_basis = 'Preparing or Performing a Contract (Product Sales) and Consent (Granted for Marketing)'
                    purpose = 'Ecommerce - Processing Customer Purchases and Marketing'
                else:
                    legal_basis = 'Preparing or Performing a Contract (Product Sales)'
                    purpose = 'Ecommerce - Processing Customer Purchases'

                sql_query_value_line = "('%s', '%s', '%s', '%s', '%s', '%s', '%s', '%s', '%s'),"\
                            % (
                                 date,
                                 action,
                                 method,
                                 referringpage,
                                 comment,
                                 customer_id,
                                 purpose,
                                 status,
                                 legal_basis
                               )

            # Otherwise its a data update
            else:

                # Convert ISO 8601 string date and time to python datetime object
                creation_datetime = dateutil.parser.parse(customer.updated_at)

                # Convert datetime object back to UTC time (in case there is a timezon offset)
                date = creation_datetime.astimezone(pytz.utc)

                action = 'Data Rectification'
                method = 'Rectified via user account.'
                referringpage = ''
                comment = 'Data updated.'
                customer_id = customer.id
                marketing_consent = customer.accepts_marketing
                status = 'Completed'
                if marketing_consent is True:
                    legal_basis = 'Preparing or Performing a Contract (Product Sales) and Consent (Granted for Marketing)'
                    purpose = 'Ecommerce - Processing Customer Purchases and Marketing'
                else:
                    legal_basis = 'Preparing or Performing a Contract (Product Sales)'
                    purpose = 'Ecommerce - Processing Customer Purchases'

                sql_query_value_line = "('%s', '%s', '%s', '%s', '%s', '%s', '%s', '%s', '%s'),"\
                            % (
                                 date,
                                 action,
                                 method,
                                 referringpage,
                                 comment,
                                 customer_id,
                                 purpose,
                                 status,
                                 legal_basis
                               )
                
            sql_query_values = sql_query_values + sql_query_value_line

            # for every set of 150 values (customer inserts) call the insert_multiple_data_events() to process these sql inserts
            # or if we have reached the end of the customer list then just dump all the values you have left in sql_query_values
            if set_counter == 150 or total_counter >= len(customer_list):

                # Pop the last comma off the end of the insert string
                sql_query_values = sql_query_values[:-1]

                # Call insert_multiple_data_events() to insert the current set of values
                AuditLogInst.insert_multiple_data_events(sql_query_values)

                # reset set_counter and sql_query_values
                set_counter = 0
                sql_query_values = ''

        # Update last_import_datetime for this store
        Store.last_import_datetime = current_datetime
        Store.save()

    return 0


# This task will not be executed via Celery Schedual, instead it is executed asynchronously within the finalize() function
# Basically once the app finishes installing in finalize, we want to immediately let him continue on his way
# while we process imports in  the all in the background.
# We are  executing the import in the background asynchronously, so the code won't have to wait for this process to finsih before rendering 
# the finalize page
@task(name='initial_data_import')
def initial_data_import(shop_url, auth_token):
    ########################################################
    # Initial Customer Import (insert multiple rows @ once)
    #########################################################

    # Create and activate store session to retrieve cutomer list
    session = shopify.Session(shop_url, auth_token)
    shopify.ShopifyResource.activate_session(session)

    # Get Customer list
    customer_list = shopify.Customer.find()  # Find with no params gets all (Returns a list)

    # Create AuditLog instance to insert customers
    AuditLogInst = DataEventLogger(shop_url)
    
    print AuditLogInst.__dict__ 

    # Concatenate customers into multiple VALUE clauses to minimize insertion time and cpu load
    sql_query_values = ''
    total_counter = 0
    set_counter = 0
    for customer in customer_list:
        total_counter += 1
        set_counter += 1 
        if (customer.id != '') and (customer.id != None): 
            customer_id = customer.id
        else: 
            customer_id = str(customer.id)

        # Convert ISO 8601 string date and time to python datetime object
        creation_datetime = dateutil.parser.parse(customer.created_at)

        # Convert datetime object back to UTC time (in case there is a timezon offset)
        date = creation_datetime.astimezone(pytz.utc)

        action = 'Data Collection'
        method = 'Initial Data Import'
        referringpage = 'Data imported on GDPR App install'
        comment = 'Personal details provided by data subject were collected and stored in the customer database.'

        customer_id = customer.id
        marketing_consent = customer.accepts_marketing
        status = 'Completed'
        if marketing_consent is True:
            legal_basis = 'Preparing or Performing a Contract (Product Sales) and Consent (Granted for Marketing)'
            purpose = 'Ecommerce - Processing Customer Purchases and Marketing'
        else:
            legal_basis = 'Preparing or Performing a Contract (Product Sales)'
            purpose = 'Ecommerce - Processing Customer Purchases'

        sql_query_value_line = "('%s', '%s', '%s', '%s', '%s', '%s', '%s', '%s', '%s'),"\
                            % (
                                 date,
                                 action,
                                 method,
                                 referringpage,
                                 comment,
                                 customer_id,
                                 purpose,
                                 status,
                                 legal_basis
                               )


        sql_query_values = sql_query_values + sql_query_value_line

        # for every set of 150 values (customer inserts) call the insert_multiple_data_events() to process these sql inserts
        # or if we have reached the end of the customer list then just dump all the values you have left in sql_query_values
        if set_counter == 150 or total_counter >= len(customer_list):

            # Pop the last comma off the end of the insert string
            sql_query_values = sql_query_values[:-1]

            # Call insert_multiple_data_events() to insert the current set of values
            AuditLogInst.insert_multiple_data_events(sql_query_values)

            # reset set_counter and sql_query_values
            set_counter = 0
            sql_query_values = ''

    # Change initial_import flag in ShopDeatz to true and change time for last_import_datetime 
    Store = ShopDeatz.objects.get(shop_url=shop_url)
    Store.initial_import = True
    Store.last_import_datetime = datetime.datetime.now()
    Store.save()

    print "Inserted Initial Import Data to SQL for %s" % (shop_url)
    return 0


#######################################################################################################################
# This view runs asynchronously to enqueue data removal requests
#######################################################################################################################
@task
def gdpr_removal(removal_request_email, confirmation_code, shop_url, referringpage):

    # Check that email corresponds to confirmation code
    try:
        RemovalConfirmInst = RemovalConfirmationCodes.objects.get(removal_request_email=removal_request_email)
        if RemovalConfirmInst.confirmation_code == confirmation_code:
            print 'Removal confirmation codes match'
            # Remove the consumed confirmation code o avoid clashes in future deletions
            RemovalConfirmInst.delete()
            pass
        else:
            print 'Removal confirmation codes do NOT match'
            return 0
    # in case email cant be found in RemovalConfirmationCodes model, then don't return anything just end function execution
    except ObjectDoesNotExist:
        print 'No removal confirmation code entry for email %s' % (removal_request_email)
        return 0

    # ##################################################
    # Activate your session with shopify store
    # ##################################################
    # Get the Shop's 0auth token, that was stored in installer.models.ShopDeatz during installation
    ShopDeatzInst = ShopDeatz.objects.get(shop_url=shop_url)
    auth_token = ShopDeatzInst.auth_token

    # Create a session object using shop_url and 0auth_token
    session = shopify.Session(shop_url, auth_token)

    # Activate the Session
    shopify.ShopifyResource.activate_session(session)

    # ##################################################
    # Check for customers added between last customer
    # check and removal request
    # ##################################################
    # Check for new customers that were added between yesterday and request time (now) in the shop where the removal_request_email is registered
    current_datetime = datetime.datetime.now()

    # Get a list of customers who's details were updated between last_import_datetime and current_datetime 
    start_datetime = ShopDeatzInst.last_import_datetime.strftime("%Y-%m-%dT%H:%M:%S") + '-00:00'
    end_datetime = current_datetime.strftime("%Y-%m-%dT%H:%M:%S") + '-00:00'  # format: 2014-04-25T16:15:47-04:00

    # Get Customer list
    # .find() works here because the updated_at_min param access the top-level endoint /admin/customers.json NOT /admin/customers/search.json
    customer_list = shopify.Customer.find(updated_at_min=start_datetime, updated_at_max=end_datetime)  # Find with no params gets all (Returns a list)

    # Create AuditLog instance to insert customers
    AuditLogInst = DataEventLogger(shop_url)

    # Concatenate customers into multiple VALUE clauses to minimize insertion time and cpu load
    sql_query_values = ''
    total_counter = 0
    set_counter = 0
    for customer in customer_list:
        total_counter += 1
        set_counter += 1
        if (customer.id != '') and (customer.id != None): 
            customer_id = customer.id
        else:
            customer_id = str(customer.id)

        # In Case this is an intial data creation
        if customer.created_at == customer.updated_at:

            # Convert ISO 8601 string date and time to python datetime object
            creation_datetime = dateutil.parser.parse(customer.created_at)

            # Convert datetime object back to UTC time (in case there is a timezon offset)
            date = creation_datetime.astimezone(pytz.utc)

            action = 'Data Collection'
            method = 'Data Collection Form'
            referringpage = ''
            comment = 'Personal details provided by data subject were collected and stored in the customer database.'

            customer_id = customer.id
            marketing_consent = customer.accepts_marketing
            status = 'Completed'
            if marketing_consent is True:
                legal_basis = 'Preparing or Performing a Contract (Product Sales) and Consent (Granted for Marketing)'
                purpose = 'Ecommerce - Processing Customer Purchases and Marketing'
            else:
                legal_basis = 'Preparing or Performing a Contract (Product Sales)'
                purpose = 'Ecommerce - Processing Customer Purchases'

            sql_query_value_line = "('%s', '%s', '%s', '%s', '%s', '%s', '%s', '%s', '%s'),"\
                            % (
                                 date,
                                 action,
                                 method,
                                 referringpage,
                                 comment,
                                 customer_id,
                                 purpose,
                                 status,
                                 legal_basis
                               )
            
        # Otherwise its a data update
        else:
            # Convert ISO 8601 string date and time to python datetime object
            creation_datetime = dateutil.parser.parse(customer.updated_at)

            # Convert datetime object back to UTC time (in case there is a timezon offset)
            date = creation_datetime.astimezone(pytz.utc)

            action = 'Data Rectification'
            method = 'User Account'
            referringpage = ''
            comment = 'Data subject rectified personal details, subject records were updated to reflect changes.'

            customer_id = customer.id
            marketing_consent = customer.accepts_marketing
            status = 'Completed'
            if marketing_consent is True:
                legal_basis = 'Preparing or Performing a Contract (Product Sales) and Consent (Granted for Marketing)'
                purpose = 'Ecommerce - Processing Customer Purchases and Marketing'
            else:
                legal_basis = 'Preparing or Performing a Contract (Product Sales)'
                purpose = 'Ecommerce - Processing Customer Purchases'

            sql_query_value_line = "('%s', '%s', '%s', '%s', '%s', '%s', '%s', '%s', '%s'),"\
                            % (
                                 date,
                                 action,
                                 method,
                                 referringpage,
                                 comment,
                                 customer_id,
                                 purpose,
                                 status,
                                 legal_basis
                               )

        sql_query_values = sql_query_values + sql_query_value_line

        # for every set of 150 values (customer inserts) call the insert_multiple_data_events() to process these sql inserts
        # or if we have reached the end of the customer list then just dump all the values you have left in sql_query_values
        if set_counter == 150 or total_counter >= len(customer_list):

            # Pop the last comma off the end of the insert string
            sql_query_values = sql_query_values[:-1]

            # Call insert_multiple_data_events() to insert the current set of values
            AuditLogInst.insert_multiple_data_events(sql_query_values)

            # reset set_counter and sql_query_values
            set_counter = 0
            sql_query_values = ''

    # Update last_import_datetime
    ShopDeatzInst.last_import_datetime = current_datetime
    ShopDeatzInst.save()

    # #####################################################
    # Make your API CALLS to remove data from shopify store
    # #####################################################
    # First use email to locate the correct customer to remove (get his customer id from shopify store DB)
    # Note : .find() will not work on Customers for SEARCHING using params, 
    # Search queries are only available on the Customer resource as a separate .search() method
    # This is because to search, you need to access a different endpont not /admin/customers.json but rather /admin/customers/search.json
    search_query = 'email:' + str(removal_request_email)
    customer_list = shopify.Customer.search(q=search_query)  # This should return a list of customers

    # Now verify that the list of customers is greater than 0, meaning we found the customer 
    # then update the attributes of the customer and save
    if len(customer_list) > 0:
       pass
    else:
        print 'No matiching customers found in DB'
        return 0

    # Go through the list of customers and check if they have an order history
    for customer in customer_list:
        if (customer.last_order_id == None) and (customer.orders_count == 0):
            # If no history then delete the customer from the using the API
            customer_id = customer.id
            marketing_consent = customer.accepts_marketing
            customer.destroy()  #destroy replaces the REST-ful DELETE request

            # #######################################################
            # Log Data Removal in Audit Table (All times are in UTC)
            # ####################################################### 
            action = 'Data Removal Request Processed'
            method = 'Data Removed via Shopify API'
            comment = 'Data removal confirmed via email removal link. Data subject personal data removed from store database via Shopify API.'
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
            # Update Data Copy and Data Registration lines to remove email and replace with Removal_Dataevent_ID
            # AuditLogInst.update_event_id(dataevent_id, removal_request_email)

        else:
            # Queue the order in gdpr.models.RemovalQueue for processing by celery task below
            last_order = shopify.Order.find(customer.last_order_id)
            last_order_date = dateutil.parser.parse(last_order.created_at)

            RemovalQueueInst = RemovalQueue()
            RemovalQueueInst.shop_url = shop_url
            RemovalQueueInst.customer_id = customer.id
            RemovalQueueInst.last_order_id = customer.last_order_id
            RemovalQueueInst.last_order_date = last_order_date
            RemovalQueueInst.removal_request_date = current_datetime
            RemovalQueueInst.removal_request_email = removal_request_email
            RemovalQueueInst.save()

            # ########################################################
            # Log Queued Removal in Audit Table (All times are in UTC)
            # ########################################################
            customer_id = customer.id
            marketing_consent = customer.accepts_marketing
            action = 'Data Removal Request Queued'
            method = 'Removal Request Pending'
            comment = 'Data removal confirmed via email removal link. Subject data removal request is pending end of charge-back period.'
            status = 'Pending'
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

        print "FINISHED SHOPIFY ERASURE QUEUEING"

        # NOW START CUSTOMER REMOVAL FROM ESP

        # #########################################################
        # Make your API CALLS to remove data from ESPs
        # #########################################################
        # Check if they are using an ESP if yes get the emailing_service, esp_username, esp_API_key, esp_list_id

        # Make an object of the MarketingServices() details, by looking up the corresponding ShopDeatz.consent_form_id (foreign key)
        # Basically get the row corresponding to ShopDeatz.consent_form_id (foreign key), make it into an objects with 'row fields' as attributes
        ESPInst = ESPCredentials.objects.get(shop_url=shop_url)

        if ESPInst.configured_ESP == '-':
            pass  # If its blank this means that no service was set in admin dashboard, then dont do anything

        elif ESPInst.configured_ESP == 'mailchimp':
            #
            #Step1: Get API Login Credentials
            #
            api_key = ESPInst.esp_API_key
            list_endpoint = ESPInst.esp_api_endpoint_url + '/3.0/lists' 
            search_endpoint = ESPInst.esp_api_endpoint_url + '/3.0/search-members'

            #
            # Step2: Make API call to get list of subscriber lists
            #
            # Pass the the 'data' dict to access_token_uri using a POST request 
            response = requests.get(list_endpoint, auth=('MyAPP', api_key))  #USe any arbitrary username

            # Grab the JSON dictionary that is returned and extract access_token
            response_dict = response.json()  # Use the .json method to convert the {data:data} JSON dictionary returned into a Python dictionary

            # Get the list of lists, and loop through all lists extracting id numbers
            list_ids = []
            if len(response_dict['lists']) > 0:
                for email_list in response_dict['lists']:
                    list_ids.append(email_list['id'])

            # Means that there are no lists available on this account
            else:
                return 0

            #
            #Step3: Loop through all the lists looking fo user-email
            #
            lists_to_erase = []
            for id_num in list_ids:
                params = (('query', removal_request_email), ('list_id', id_num))
                response = requests.get(search_endpoint, params=params, auth=('MYAPP', api_key))
                response_dict = response.json()  # Use the .json method to convert the {data:data} JSON dictionary returned into a Python dictionary

                # if it finds exact matches in this list, then add this list id to lists_to_erase[]
                if (len(response_dict["exact_matches"]["members"]) > 0):
                    lists_to_erase.append(id_num)

            #
            #Step4: Remove useremail from all lists where it was located
            #
            for id_num in lists_to_erase:
                lowercase_email = removal_request_email.lower()
                email_bytes = lowercase_email.encode('utf-8')  # must convert string to bytes first before hashing
                email_hash_object = hashlib.md5(email_bytes)  # create hash object from byte string
                email_hash = email_hash_object.hexdigest()

                # Construct Removal Endpoint URL
                removal_endpoint = ESPInst.esp_api_endpoint_url + '/3.0/lists/' + id_num + '/members/' + email_hash

                # Send the Delete request
                response = requests.delete(removal_endpoint, auth=('MYAPP', api_key))

            print "FINISHED MAILCHIMP ERASURE"

            # #######################################################
            # Log MAIL LIST Removal in Audit Table (All times are in UTC)
            # ####################################################### 
            action = 'Data Removal Request Processed'
            method = 'Data Removed via MailChimp API'
            comment = 'Data removal confirmed via email removal link. Subject personal data removed from mailing list via MailChimp API.'
            status = 'Completed'
            customer_id = customer.id
            marketing_consent = customer.accepts_marketing
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

        elif ESPInst.configured_ESP == 'omnisend':
            # Not possible even updtating data leaves traces of old data
            # Need to wait for omnisend to open up their DELETE portion of the API (coming soon)
            pass

        # #######################################################
        # Send Email to Partners to request customer data removal
        # #######################################################
 
    return 0


#######################################################################################################################
# This task runs once per day to processe data removal requests in gdpr.models.RemovalQueue 
#######################################################################################################################
@task
def removal_queue_processing():

    print 'started task'

    current_datetime = datetime.datetime.now()

    # Create an instance of RemovalQueue and loop through all entries in the queue
    RemovalQueue_list = RemovalQueue.objects.all()

    for RemovalQueue_entry in RemovalQueue_list:
        print RemovalQueue_entry 

        # Get the Shop's 0auth token, that was stored in installer.models.ShopDeatz during installation
        ShopDeatzInst = ShopDeatz.objects.get(shop_url=RemovalQueue_entry.shop_url)
        auth_token = ShopDeatzInst.auth_token

        # Create a session object using shop_url and 0auth_token
        session = shopify.Session(RemovalQueue_entry.shop_url, auth_token)

        # Activate the Session
        shopify.ShopifyResource.activate_session(session)

        # STEP1. Create an instance of the customer by looking him up using his ID
        customer = shopify.Customer.find(RemovalQueue_entry.customer_id)

        # STEP1. Check if last_order_id has not changed
        print customer.last_order_id
        print RemovalQueue_entry.last_order_id
        if str(customer.last_order_id) == RemovalQueue_entry.last_order_id:
            print "last order ids match"
            pass

        # In case the customer has initiated a new order in between his removal request date and now, then re-set his last_order_date to 
        # account for the new chargeback period
        else:
            print "orders don't match"
            last_order = shopify.Order.find(customer.last_order_id)
            last_order_date = dateutil.parser.parse(last_order.created_at)

            # This will update all entries corresponding to the the customer_id and shop url. This is used in case the customer would have
            # submitted multiple removal queries
            RemovalQueue.objects.filter(customer_id=RemovalQueue_entry.customer_id, shop_url=RemovalQueue_entry.shop_url).update(last_order_id = customer.last_order_id)
            RemovalQueue.objects.filter(customer_id=RemovalQueue_entry.customer_id, shop_url=RemovalQueue_entry.shop_url).update(last_order_date = last_order_date)
            continue

        ################################################################################################
        # Shopify Removal Processing
        ###############################################################################################
        # The Rest of this code will not execute unless the if statement above is successfully passed

        # Charge Back Period (defined in number of days, should be set to 181 days)
        chargeback_period = 6

        # calculate how many days have passed since last order
        days_since_last_order = current_datetime - RemovalQueue_entry.last_order_date.replace(tzinfo=None)
        print 'days since last order'
        print days_since_last_order

        # if less than 181 days don't do anything move to the next removal entry in the queue
        if days_since_last_order < datetime.timedelta(chargeback_period):
            print "ChargeBack period hasn't been terminated for customer_id %s" %(str(RemovalQueue_entry.customer_id))
            continue

        elif days_since_last_order >= datetime.timedelta(chargeback_period):
            print "ChargeBack period terminated sending removal email to Shopify Privacy Team"

            # ##############################################################
            # Use Sendgrid to send removal request to privacy@shopify.com
            # ##############################################################

            # Get Shop Owner's email Address for CC'ing him in the email
            ShopInfo = shopify.Shop.current()
            owner_email = ShopInfo.email
            owner_name = ShopInfo.shop_owner
            shop_name = ShopInfo.name
            shop_id = ShopInfo.id

            template_relative_location = 'templates/emailtemplates/data_removal.html'
            filelocation = os.path.join(settings.BASE_DIR, template_relative_location)
            BODY_HTML = ""
            for line in open(filelocation):
                new_line = line.rstrip('\n')
                BODY_HTML = BODY_HTML + new_line

            # replace content of template
            BODY_HTML = BODY_HTML.replace('#SHOPNAME#', str(shop_name))
            BODY_HTML = BODY_HTML.replace('#SHOPID#', str(shop_id))
            BODY_HTML = BODY_HTML.replace('#CUSTOMERID#', str(RemovalQueue_entry.customer_id))
            BODY_HTML = BODY_HTML.replace('#LASTORDERID#', str(RemovalQueue_entry.last_order_id))
            BODY_HTML = BODY_HTML.replace('#DOLO#', RemovalQueue_entry.last_order_date.strftime("%d %B %Y"))
            BODY_HTML = BODY_HTML.replace('#EOCBP#', ((RemovalQueue_entry.last_order_date + datetime.timedelta(180)).strftime("%d %B %Y")))
            BODY_HTML = BODY_HTML.replace('#DOGDPR#', RemovalQueue_entry.removal_request_date.strftime("%d %B %Y"))
            BODY_HTML = BODY_HTML.replace('#STOREOWNER#', str(owner_name))

            # The character encoding for the email.
            CHARSET = "UTF-8"

            # SendGrid Code Block
            RECIPIENT = 'gdprdynamics@gmail.com'  # This should be changed to the email of the Shopify Privacy Team
            SUBJECT = str(shop_name) + " - GDPR Data Removal Request" 

            #from_email = Email(email="dataofficer@transactional.gdprdynamics.com", name=shop_name)
            #subject = SUBJECT
            #to_email = Email(RECIPIENT)
            #content = Content("text/html", BODY_HTML) 
            #mail = Mail(from_email, subject, to_email, content)
            #mail.personalizations[0].add_to(Email(RECIPIENT))  # This should be the Shopify Privacy team privacy@shopify.com
            #mail.personalizations[0].add_cc(Email(owner_email))  ## CC store owner

            print "owner email %s" %(owner_email)

            sg = sendgrid.SendGridAPIClient(apikey=settings.SENDGRID_API_KEY)
            from_email = Email(email="dataofficer@transactional.gdprdynamics.com", name=str(shop_name))
            to_email = Email(RECIPIENT)
            subject = SUBJECT
            content = Content("text/html", BODY_HTML)
            mail = Mail(from_email, subject, to_email, content)
            mail.personalizations[0].add_cc(Email(owner_email))

            response = sg.client.mail.send.post(request_body=mail.get())
            print(response.status_code)
            print(response.body)
            print(response.headers)

            # ######################################################
            # Change Status of 'PENDING' Removal in Audit Table
            # ######################################################

            # Create AuditLog Instance
            AuditLogInst = DataEventLogger(RemovalQueue_entry.shop_url)

            # Update Status
            AuditLogInst.update_status(RemovalQueue_entry.customer_id)

            # #######################################################
            # Log Data Removal in Audit Table (All times are in UTC)
            # #######################################################

            customer_id = customer.id
            marketing_consent = customer.accepts_marketing
            action = 'Data Removal Request Processed'
            method = 'Removal Request Transmitted to Processor'
            comment = 'Charge-back period terminated, data removal request sent to the Data Processor (Shopfy) via email (privacy@shopify.com) for erasure.'
            referringpage = '-'
            status = 'Completed'
            if marketing_consent is True:
                legal_basis = 'Preparing or Performing a Contract (Product Sales) and Consent (Granted for Marketing)'
                purpose = 'Ecommerce - Processing Customer Purchases and Marketing'
            else:
                legal_basis = 'Preparing or Performing a Contract (Product Sales)'
                purpose = 'Ecommerce - Processing Customer Purchases'

            # Add Data Removal Entry line
            AuditLogInst.insert_data_processing_event(current_datetime, action, method, referringpage, comment,\
                                                      customer_id, purpose, status, legal_basis)

            # ##############################################################
            # Remove the customer's removal request from the removal queue
            # ###############################################################
            RemovalQueue.objects.filter(customer_id=RemovalQueue_entry.customer_id, shop_url=RemovalQueue_entry.shop_url).delete() 

        else:
            print "Somethong went wrong in gdpr.tasks.removal_queue_processing"

    print "Removal Queue Processing Terminated SUCCESSFULLY"
    return 0
