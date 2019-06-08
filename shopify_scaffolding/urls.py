from django.conf.urls import include, url
from django.contrib import admin

from installer.views import login, authenticate, finalize, logout, webhook, activateRecurringCharge
from dashboard.views import index, initial_setup, customize_popups, advanced_settings, mailchimpauth, faq, dp_activities, dp_edit, dp_create
from scripttags.views import scripttagsrc1
from gdpr.views import ipcheck, gdpr_request

urlpatterns = [
                #url(r'admin/', admin.site.urls),
                url(r'^$', login, name='shopify_app_login'),

                # Installer
                url(r'^authenticate/$', authenticate, name='shopify_app_authenticate'),
                url(r'^finalize/$', finalize, name='shopify_app_finalize'),
                url(r'^logout/$', logout, name='shopify_app_logout'),
                url(r'^webhook/$', webhook, name='shopify_app_webhook'),
                url(r'^activatecharge/$', activateRecurringCharge, name='activate_charge'),

                # Dashboard
                url(r'^$', index, name='root_path'),
                url(r'^home/$', index, name='root_path2'),
                url(r'^settings/$', initial_setup, name='root_settings'),
                url(r'^custpopup/$', customize_popups, name='root_customize'),
                url(r'^faq/$', faq, name='faq'),
                url(r'^advancedsettings/$', advanced_settings, name='root_advanced'),
                url(r'^dpactivities/$', dp_activities, name='root_activities'),
                url(r'^dpedit/$', dp_edit, name='root_edit'),
                url(r'^dpcreate/$', dp_create, name='root_create'),

                # Script Tags
                url(r'^scriptsrc1/$', scripttagsrc1, name='first_script_tag'),
                url(r'^ipcheck/$', ipcheck, name='ipcheck'),

                # Data Processing 
                url(r'^dataevent/$', gdpr_request, name='dataevent'),

                # ESP Integration Endpoints 
                url(r'^mailchimpauth/$', mailchimpauth, name='mailchimp_oAuth'),
                
              ]
