import psycopg2

def fix_database(dbname='odoo_driving_backedup', user='odoo', password='odoo', host='localhost'):
    conn = psycopg2.connect(dbname=dbname, user=user, password=password, host=host)
    cur = conn.cursor()
    
    # 1. Create missing relation tables for Many2many fields
    queries = [
        # Customer to Store relation
        '''CREATE TABLE IF NOT EXISTS havanoposdesk_customer_havanoposdesk_store_rel (
            havanoposdesk_customer_id INTEGER NOT NULL REFERENCES havanoposdesk_customer(id) ON DELETE CASCADE, 
            havanoposdesk_store_id INTEGER NOT NULL REFERENCES havanoposdesk_store(id) ON DELETE CASCADE
        );''',
        '''CREATE UNIQUE INDEX IF NOT EXISTS havanoposdesk_customer_havanoposdesk_store_rel_uniq 
            ON havanoposdesk_customer_havanoposdesk_store_rel(havanoposdesk_customer_id, havanoposdesk_store_id);''',
        '''CREATE INDEX IF NOT EXISTS havanoposdesk_customer_havanoposdesk_store_rel_customer_id_idx 
            ON havanoposdesk_customer_havanoposdesk_store_rel(havanoposdesk_customer_id);''',
        '''CREATE INDEX IF NOT EXISTS havanoposdesk_customer_havanoposdesk_store_rel_store_id_idx 
            ON havanoposdesk_customer_havanoposdesk_store_rel(havanoposdesk_store_id);''',
            
        # Category to Store relation
        '''CREATE TABLE IF NOT EXISTS havanoposdesk_category_havanoposdesk_store_rel (
            havanoposdesk_category_id INTEGER NOT NULL REFERENCES havanoposdesk_category(id) ON DELETE CASCADE, 
            havanoposdesk_store_id INTEGER NOT NULL REFERENCES havanoposdesk_store(id) ON DELETE CASCADE
        );''',
        '''CREATE UNIQUE INDEX IF NOT EXISTS havanoposdesk_category_havanoposdesk_store_rel_uniq 
            ON havanoposdesk_category_havanoposdesk_store_rel(havanoposdesk_category_id, havanoposdesk_store_id);''',
        '''CREATE INDEX IF NOT EXISTS havanoposdesk_category_havanoposdesk_store_rel_cat_id_idx 
            ON havanoposdesk_category_havanoposdesk_store_rel(havanoposdesk_category_id);''',
        '''CREATE INDEX IF NOT EXISTS havanoposdesk_category_havanoposdesk_store_rel_store_id_idx 
            ON havanoposdesk_category_havanoposdesk_store_rel(havanoposdesk_store_id);'''
    ]
    
    for q in queries:
        try:
            cur.execute(q)
        except Exception as e:
            print(f"Error executing query: {e}")
            conn.rollback()
        else:
            conn.commit()
            
    print("Many2many relation tables verified/created successfully.")
    
    # 2. Deactivate existing taxes to ensure they are inactive by default
    try:
        cur.execute("UPDATE havanoposdesk_tax SET active = FALSE WHERE active = TRUE;")
        conn.commit()
        print(f"Deactivated {cur.rowcount} active taxes successfully.")
    except Exception as e:
        print(f"Error deactivating taxes: {e}")
        conn.rollback()

    conn.close()
    print("Database fix completed.")

if __name__ == '__main__':
    # You can change the dbname if running on a different server
    fix_database()
