# Replace the API Key and Shared Secret with the one given for your
# App by Shopify.
#
# To create an application, or find the API Key and Secret, visit:
# - for private Apps:
#     https://${YOUR_SHOP_NAME}.myshopify.com/admin/api
# - for partner Apps:
#     https://www.shopify.com/services/partners/api_clients
#
# You can ignore this file in git using the following command:
#   git update-index --assume-unchanged shopify_settings.py
import os

# APP URL
APP_DOMAINURL = 'https://www.exampleGDPRapp.com'  # !!!! IMPORTANT NO TRAILING '/' at the end of your domain

# API ACCESS
SHOPIFY_API_KEY = 'XXXXXXXXXXXXXXX'
SHOPIFY_API_SECRET = 'XXXXXXXXXXXXXX'

# See http://api.shopify.com/authentication.html for available scopes
# Set the permisssions your app will need.
SHOPIFY_API_SCOPE = ['read_customers', 'write_customers', 'write_script_tags', 'read_orders']


# Settings for APP recurring payments
APP_NAME = 'GDPR Compliance 360'
APP_PRICE = 19.99  # Price in USD (always 2 decimal places)
APP_TESTFLAG = True  # test flag to true will set the RecurringApplicationCharge to not actually charge the credit card
APP_RETURNURL = "https://www.exampleGDPRapp.com/activatecharge/"  # The URL the customer is sent to when accept/decline charge.
APP_TRIALDAYS = 2

# Email Service
ACTIVE_TRANSACTIONALEMAIL_SERVICE = 'SENDGRID'  #SWITCH THIS TO 'SENDGRID' OR 'AMAZON' depending on what you want to use
SENDGRID_API_KEY = 'XXXXXXXXXXXXXX'
aws_id = 'XXXXXXXXXXXXXX'
aws_secret ='XXXXXXXXXXXXXX'
