'''
Created on Jan 28, 2018

@author: MK RAHAL
'''

import MySQLdb
import datetime
from shopify_scaffolding import settings

class processing_tools():

    def epoch_converter(self, epoch_date):
        self.timestamp = epoch_date
        # transform epoch to gregorian date using datetime, and format in SQL query appropriate style (YYYYMMDD)
        gregorian_date = datetime.datetime.fromtimestamp(self.timestamp).strftime('%Y%m%d')
        gregorian_date = int(gregorian_date)
        return gregorian_date

    def failed_log(self, sql_query):
        current_date = datetime.date.today().strftime("%B-%d-%Y")
        filename = settings.BASE_DIR + '/FailLogs/AuditLog_failure_.py' + current_date
        fail_log = open(filename, 'w+')
        fail_log.write(sql_query)
        fail_log.write("\n")
        fail_log.close()

    def execute_query(self, db_name, table_name, sql_query):
        # Open database connection
        db = MySQLdb.connect(host="127.0.0.1", user="gdpr-user", passwd="Z7ZEgSBipVcGQWNz7jvm2aY3eoqtdp96nKHK3a1cU3ugW3J60", db=db_name, port=3306)

        # prepare a cursor object using cursor() method
        cursor = db.cursor()

        for attempt in range(3):  # Number of times you want to retry
            try:
                # Execute the SQL command
                cursor.execute(sql_query)
                # Commit your changes in the database
                db.commit()
                # print "QUERY EXECUTION SUCCESS"
                break  # This break needs to happen so that the else bit does not happen (so that the else is skipped)

            except Exception:
                # Rollback in case there is any error
                db.rollback()
                # print "QUERY EXECUTION - FAILURE"
                pass
 
        else:
            print "\n"
            print "##################### SQL ERROR ##########################"
            print "Something went terribly wrong 3 attempts failed to write:"
            print sql_query
            print "In table: %s" % (table_name)
            print "\n"
            self.failed_log('FAILED TO EXECUTE SQL QUERY \n')
            self.failed_log(sql_query)
            cursor.close()
            raise  # All attempts failed

        return cursor


class DataEventLogger(processing_tools):

    def __init__(self, shopurl, event_id='', date='', action='', method='', referringpage='', comment=''):
        shopurl = shopurl.replace('.', '_')  # Shop URL used in tablenames can't have dots so replace with '_' 
        shopurl = shopurl.replace('-', '_')  # Shop URL used in tablenames can't have - so replace with '_'
        print  "#####################################################"
        print shopurl
        self.db = 'GDPR_Audit_Logs'
        self.shopurl = shopurl
        self.tablename = shopurl
        self.event_id = event_id  # Shop customer (in case of removal request put hash here and replace all previous entries of this username with hash)
        self.date = date  # Date and time when data processing event was triggered
        self.action = action  # Data processing action (Consented, Requested data copy, Requested data removal, Registered Personal Details)
        self.method = method  # Method that triggered the data processing action (click concent btn, regstrd on cart prchse, click remove btn)
        self.referringpage = referringpage
        self.comment = comment  # Result of data processing action ex. Data removed from DB & third parties or Requested data sent via email etc
        # print "initialisation complete"


    # Permenantly delete a table
    def drop_table(self):
        sql_query = "drop table '%s';" %(self.tablename)

        cursor_result = self.execute_query(self.db, self.tablename, sql_query)
        cursor_result.close()


    # Checks if table is exists, returns True if its exists, and False if it does not
    def check_table_exists(self):
        # Check if the table already exists if it doesn't then execute the query other don't do anything
        check_query = "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = '%s'" % (self.tablename)

        cursor_check_result = self.execute_query(self.db, self.tablename, check_query)
        if cursor_check_result.fetchone()[0] == 1:
            cursor_check_result.close()
            return True
        else:
            cursor_check_result.close()
            return False


    def create_shop_audit_table(self):
        sql_query1 = "CREATE TABLE %s (event_id int NOT NULL AUTO_INCREMENT, date  DATETIME, action VARCHAR(300) DEFAULT '-', " \
                        % (self.tablename)
        sql_query2 = "method VARCHAR(300) DEFAULT '-', referringpage VARCHAR(300) DEFAULT '-', comment VARCHAR(300) DEFAULT '-', "
        sql_query3 = "customer_id VARCHAR(300) DEFAULT '-', purpose VARCHAR(300) DEFAULT '-', status VARCHAR(300) DEFAULT '-', "
        sql_query4 = "legal_basis VARCHAR(300) DEFAULT '-', PRIMARY KEY(event_id));"
        sql_query_full = sql_query1 + sql_query2 + sql_query3 + sql_query4 
        print sql_query_full

        cursor_result = self.execute_query(self.db, self.tablename, sql_query_full)
        cursor_result.close()


    def insert_data_processing_event(self, current_datetime, action, method, referringpage, comment, customer_id, purpose, status, legal_basis):
        sql_query1 = "INSERT INTO %s " % (self.tablename)
        sql_query2 = "(date, action, method, referringpage, comment, customer_id, purpose, status, legal_basis) "
        sql_query3 = "VALUES ('%s', '%s', '%s', '%s', '%s', '%s', '%s', '%s', '%s')"\
                     % (
                         current_datetime,
                         action,
                         method,
                         referringpage,
                         comment,
                         customer_id,
                         purpose,
                         status,
                         legal_basis
                       )

        sql_query_full = sql_query1 + sql_query2 + sql_query3
        print sql_query_full
        cursor_result = self.execute_query(self.db, self.tablename, sql_query_full)
        cursor_result.close()

    def insert_multiple_data_events(self, values):
        sql_query1 = "INSERT INTO %s " % (self.tablename)
        sql_query2 = "(date, action, method, referringpage, comment, customer_id, purpose, status, legal_basis) VALUES "

        sql_query_full = sql_query1 + sql_query2 + values + ';'
        print sql_query_full
        cursor_result = self.execute_query(self.db, self.tablename, sql_query_full)
        cursor_result.close()

    # function to change the email into event_id once removal has been requested
    def update_event_id(self, event_id, email):
        sql_query = "UPDATE %s SET event_id = '%s' WHERE event_id = '%s' ;"\
                    % (self.tablename, event_id, email)

        print sql_query
        #cursor_result = self.execute_query(self.db, self.tablename, sql_query)
        #cursor_result.close()

    # function to edit a data event when user uses dp_edit.html
    def update_event(self, event_id, date, event_type, legal_basis, purpose, comment, status):
        sql_query = "UPDATE %s SET date='%s', action='%s', legal_basis='%s', purpose='%s', comment='%s', status='%s' WHERE event_id='%s' ;"\
                    % (self.tablename, date, event_type, legal_basis, purpose, comment, status, event_id,)

        print sql_query
        cursor_result = self.execute_query(self.db, self.tablename, sql_query)
        cursor_result.close()

    # function to change status once removal request has been sent to privacy@shopify.com
    def update_status(self, customer_id):
        sql_query = "UPDATE %s SET status = 'Completed' WHERE customer_id = '%s' AND status = 'Pending' ;"\
                    % (self.tablename, customer_id)

        print sql_query
        cursor_result = self.execute_query(self.db, self.tablename, sql_query)
        cursor_result.close()

    def get_hist_csv(self, startdate, enddate):
        # This SQL Query returns any row with matching dates as long as the dates in question are equal or between 'startdate' and 'enddate'
        # SQL date format is 'YYYY-MM-DD'
        sql_query = "SELECT * FROM %s  WHERE date BETWEEN '%s' AND '%s' ORDER BY date desc" % (self.tablename, startdate, enddate)

        cursor_result = self.execute_query(self.db, self.tablename, sql_query)
        history = cursor_result.fetchall()
        print sql_query
        #print history
        return history

    def get_single_event_details(self, event_id):
        # This SQL Query returns the row with the matching event_id
        # SQL date format is 'YYYY-MM-DD'
        sql_query = "SELECT * FROM %s  WHERE event_id='%s' " % (self.tablename, event_id)

        cursor_result = self.execute_query(self.db, self.tablename, sql_query)
        history = cursor_result.fetchone()
        print sql_query
        print history
        return history

    # Counts all data EVENTS loged into the DB
    def count_data_events(self):
        sql_query = "SELECT COUNT('event_id') FROM %s;"\
                    % (self.tablename)

        print sql_query
        cursor_result = self.execute_query(self.db, self.tablename, sql_query)
        db_entry_count = cursor_result.fetchone()[0]
        cursor_result.close()
        return db_entry_count


    # Get the date of the latest data EVENT logged in the DB
    def latest_data_event_date(self):
        sql_query = "SELECT MAX(date) FROM %s;"\
                    % (self.tablename)

        print sql_query
        cursor_result = self.execute_query(self.db, self.tablename, sql_query)
        db_entry_date = cursor_result.fetchone()[0]
        cursor_result.close()
        return db_entry_date


    # Counts only the number of customers added to the DB (not removal/access requests just customer added)
    def count_data_assets(self):
        sql_query = "SELECT COUNT('event_id') FROM %s WHERE action='Data Collection' OR action='Data Registration';"\
                    % (self.tablename)

        print sql_query
        cursor_result = self.execute_query(self.db, self.tablename, sql_query)
        db_entry_count = cursor_result.fetchone()[0]
        cursor_result.close()
        return db_entry_count

    # Count Access Requests
    def count_data_access(self):
        sql_query = "SELECT COUNT('event_id') FROM %s WHERE action='Data Access Request';"\
                    % (self.tablename)

        print sql_query
        cursor_result = self.execute_query(self.db, self.tablename, sql_query)
        db_entry_count = cursor_result.fetchone()[0]
        cursor_result.close()
        return db_entry_count

    # Count Removal Requests
    def count_data_removal(self):
        sql_query = "SELECT COUNT('event_id') FROM %s WHERE action='Data Removal Request';"\
                    % (self.tablename)

        print sql_query
        cursor_result = self.execute_query(self.db, self.tablename, sql_query)
        db_entry_count = cursor_result.fetchone()[0]
        cursor_result.close()
        return db_entry_count

    # Count Consent Granted
    def count_data_consent(self):
        sql_query = "SELECT COUNT('event_id') FROM %s WHERE action='Data Consent';"\
                    % (self.tablename)

        print sql_query
        cursor_result = self.execute_query(self.db, self.tablename, sql_query)
        db_entry_count = cursor_result.fetchone()[0]
        cursor_result.close()
        return db_entry_count

    # Count Data Rectification
    def count_data_rectification(self):
        sql_query = "SELECT COUNT('event_id') FROM %s WHERE action='Data Rectification';"\
                    % (self.tablename)

        print sql_query
        cursor_result = self.execute_query(self.db, self.tablename, sql_query)
        db_entry_count = cursor_result.fetchone()[0]
        cursor_result.close()
        return db_entry_count


    # Delete a Data Event
    def delete_event(self, event_id):
        sql_query = "DELETE FROM %s WHERE event_id='%s';"\
                    % (self.tablename, event_id)

        print sql_query
        cursor_result = self.execute_query(self.db, self.tablename, sql_query)
        db_entry_count = cursor_result.fetchone()[0]
        cursor_result.close()
        return db_entry_count


    # Get the date of the latest customer (data asset) addition (not inluding removal/access requestsi, just customers added)
    def latest_data_asset_date(self):
        sql_query = "SELECT MAX(date) FROM %s WHERE action='Data Collection' OR action='Data Registration';"\
                    % (self.tablename)

        print sql_query
        cursor_result = self.execute_query(self.db, self.tablename, sql_query)
        db_entry_date = cursor_result.fetchone()[0]
        cursor_result.close()
        return db_entry_date


    # Get the 4 most recent entries in your DB
    def most_recent_4(self):
        sql_query = "SELECT * FROM %s ORDER BY date desc LIMIT 4;"\
                    % (self.tablename)

        print sql_query
        cursor_result = self.execute_query(self.db, self.tablename, sql_query)
        most_recent = cursor_result.fetchall()
        print sql_query
        # print results
        return most_recent

    # Get Most recently created event by DPO 
    def get_new_added_event_details(self):
        sql_query = "SELECT * FROM %s WHERE method='DPO Event'  ORDER BY date desc LIMIT 1;"\
                    % (self.tablename)

        print sql_query
        cursor_result = self.execute_query(self.db, self.tablename, sql_query)
        most_recent = cursor_result.fetchone()
        print sql_query
        # print results
        return most_recent



"""
### TESTING
shop_url = 'tesddevstore.myshopify.com'

# Create shop audit table
AuditLogInst = DataEventLogger(shop_url)
#AuditLogInst.create_shop_audit_table()

# Insert Data Processing Event - Removal
event_id = 'Advqert6shtsrhv6351g'
date = datetime.datetime.utcnow()
action = 'Requested Data Removal'
method = 'Data Removal Icon and Form Submit'
referringpage = 'HTTPREFFERER'
comment = 'Data removed from database. Partners notified of user request.'
email = 'lawlessleopard@gmail.com'

AuditLogInst.insert_data_processing_event(event_id, date, action, method, referringpage, comment)

AuditLogInst.update_event_id(event_id, email)
"""
