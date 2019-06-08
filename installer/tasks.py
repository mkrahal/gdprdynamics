from celery import task
import datetime
import shopify
from installer.models import ShopDeatz, InstallTracker 
import datetime
from dashboard.models import ShopCustomizations, ShopSettings, ShopMarketingServices, ESPCredentials, AdvancedSettings

@task
def check_recurring_charge():
    ################################################################
    # Check all stores to see if recurring charge is still active
    ###############################################################
    # Get a list of all shops
    ShopDeatzInst = ShopDeatz.objects.all()

    removed_store_count = 0
    # Extract individual objects from object list, to get their urls and create a store session to send API calls
    for Store in ShopDeatzInst:
        shop_url = Store.shop_url
        auth_token = Store.auth_token

        # Create and activate store session to retrieve cutomer list
        session = shopify.Session(shop_url, auth_token)
        shopify.ShopifyResource.activate_session(session)

        # use the charge_id to find the correct RecurringApplicationCharge within the store's charges
        charge = shopify.RecurringApplicationCharge.find(charge_id)

        # if the charge.status is active then move on to next store in loop
        if charge.status == 'active':
            pass
        # otherwise, delete the store from the DB and then move to next store
        else:
            # Delete the store from ALL your app models except InstallTracker
            removed_store_count += 1

            Store.delete() # This line deletes the store from ShopDeatz model
            ShopCustInst = ShopCustomizations.objects.filter(shop_url=shop_url).delete()
            ShopSettingsInst = ShopSettings.objects.filter(shop_url=shop_url).delete()
            ShopMarketingServicesInst = ShopMarketingServices.objects.filter(shop_url=shop_url).delete()
            AdvancedSettingsInst = AdvancedSettings.objects.filter(shop_url=shop_url).delete()
            ESPInst = ESPCredentials.objects.filter(shop_url=shop_url).delete() 

            # Write uninstall date to InstallTracker model
            InstallTrackerInst = InstallTracker.objects.get(shop_url=shop_url)
            InstallTrackerInst.uninstall_date = datetime.date.today() 
            InstallTrackerInst.db_purge = 'pending'
            InstallTrackerInst.save()

    print 'Finished daily recurring charge check. Removed %i stores.' %(removed_store_count)
    return 0


@task
def purge_mysql_database():
    print '##############################################################################'
    print 'LIST OF STORES THAT HAVE UNINSTALLED MORE THAN 2 DAYS AGO. MYSQL DB SHOULD BE PURGED OF THESE TABLES:'
    shops_to_purge = InstallTrackerInst = InstallTracker.objects.filter(db_purge = 'pending')

    today = datetime.date.today()
    for shop in shops_to_purge:
        shop_url = shop.shop_url
        AuditLogInst = DataEventLogger(shop_url)
        time_elapsed = today - shop.uninstall_date
        # Check if it has been pending for more than 2 days and that it still exists in the DB (hasn't been removed by admin)
        if time_elapsed.days => 2 and AuditLogInst.check_table_exists():
            # Drop table from database
            #AuditLogInst.drop_table()
            print '%s mysql table needs to be removed.'
