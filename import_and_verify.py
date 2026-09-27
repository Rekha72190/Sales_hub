import os
import glob
import re
import logging
import mysql.connector
from mysql.connector import Error
import pandas as pd

# -------------------------------------------------------------
# 1. SETUP LOGGING
# -------------------------------------------------------------
LOG_FILE = "import_history.log"
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

def log_and_print(message, level="info"):
    print(message)
    if level == "info":
        logging.info(message)
    elif level == "warning":
        logging.warning(message)
    elif level == "error":
        logging.error(message)


# -------------------------------------------------------------
# 2. DATABASE CONFIGURATION
# -------------------------------------------------------------
DB_CONFIG = {
    'host': '127.0.0.1',
    'user': 'root',
    'password': '123456789',
    'database': 'sales_hub_db',
    'port': 3306
}

LOCAL_FOLDER_PATH = r"C:\project1\dataset"


# -------------------------------------------------------------
# 3. PRIORITY SORTING FOR SEQUENTIAL IMPORT
# -------------------------------------------------------------
def get_file_priority(file_path):
    """
    Enforces Strict Processing Sequence:
    1: branches.csv       (Base entity)
    2: users.csv          (Depends on branches)
    3: customer_sales.csv (Depends on branches)
    4: payment_splits.csv (Depends on customer_sales.sale_id)
    """
    file_name = os.path.basename(file_path).lower()
    
    if 'branch' in file_name and 'sale' not in file_name:
        return 1
    elif 'user' in file_name:
        return 2
    elif 'customer' in file_name or ('sale' in file_name and 'split' not in file_name and 'payment' not in file_name):
        return 3
    elif 'split' in file_name or 'payment' in file_name:
        return 4
    return 99


def clean_float_value(val):
    """Safely converts currency/string values to float."""
    if pd.isna(val) or val is None:
        return 0.0
    cleaned = re.sub(r'[^\d.-]', '', str(val))
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


# -------------------------------------------------------------
# 4. CSV PROCESSING WITH CONSTRAINT VALIDATION
# -------------------------------------------------------------
def process_csv_file(cursor, file_path):
    file_name = os.path.basename(file_path).lower()
    log_and_print(f"📄 Processing file: {os.path.basename(file_path)}")

    df = pd.read_csv(file_path)
    df.columns = df.columns.str.strip().str.lower()
    row_count = len(df)

    # 1. BRANCHES
    if 'branch' in file_name and 'sale' not in file_name:
        query = """
            INSERT INTO branches (branch_id, branch_name, branch_admin_name)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE 
                branch_name=VALUES(branch_name),
                branch_admin_name=VALUES(branch_admin_name);
        """
        records = []
        for _, row in df.iterrows():
            b_id = int(clean_float_value(row.get('branch_id', row.iloc[0])))
            b_name = str(row.get('branch_name', row.get('branch', row.iloc[1])))
            b_admin = str(row.get('branch_admin_name', row.get('admin_name', row.iloc[2] if len(row) > 2 else 'Admin')))
            records.append((b_id, b_name, b_admin))

        cursor.executemany(query, records)
        log_and_print(f"   ✅ Branches: Processed {row_count} CSV rows -> {cursor.rowcount} database rows affected.")

    # 2. USERS
    elif 'user' in file_name:
        query = """
            INSERT INTO users (username, password, branch_id, role, email)
            VALUES (%s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE role=VALUES(role);
        """
        records = []
        for _, row in df.iterrows():
            username = str(row.get('username', row.iloc[0]))
            password = str(row.get('password', row.iloc[1]))
            branch_val = row.get('branch_id', row.iloc[2] if len(row) > 2 else None)
            branch_id = None if pd.isna(branch_val) or str(branch_val).strip() == '' else int(clean_float_value(branch_val))
            role = str(row.get('role', row.iloc[3] if len(row) > 3 else 'Admin'))
            email = str(row.get('email', row.iloc[4] if len(row) > 4 else f"{username}@company.com"))
            records.append((username, password, branch_id, role, email))

        cursor.executemany(query, records)
        log_and_print(f"   ✅ Users: Processed {row_count} CSV rows -> {cursor.rowcount} database rows affected.")

    # 3. CUSTOMER SALES
    elif 'customer' in file_name or ('sale' in file_name and 'split' not in file_name and 'payment' not in file_name):
        query = """
            INSERT INTO customer_sales 
            (branch_id, date, name, mobile_number, product_name, gross_sales)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                name=VALUES(name),
                gross_sales=VALUES(gross_sales);
        """
        records = []
        for _, row in df.iterrows():
            b_id = int(clean_float_value(row.get('branch_id', row.iloc[0])))
            s_date = str(row.get('date', row.get('sale_date', row.iloc[1])))
            c_name = str(row.get('name', row.get('customer_name', row.iloc[2])))
            m_num = str(row.get('mobile_number', row.get('mobile', row.get('phone', row.iloc[3]))))
            p_name = str(row.get('product_name', row.get('product', row.iloc[4])))
            raw_sales = row.get('gross_sales', row.get('sales', row.get('amount', row.iloc[5] if len(row) > 5 else 0.0)))
            g_sales = clean_float_value(raw_sales)
            records.append((b_id, s_date, c_name, m_num, p_name, g_sales))

        cursor.executemany(query, records)
        log_and_print(f"   ✅ Customer Sales: Processed {row_count} CSV rows -> {cursor.rowcount} database rows affected.")

    # 4. PAYMENT SPLITS (With Pre-validation for Constraint Safety)
    elif 'split' in file_name or 'payment' in file_name:
        inserted_count = 0
        skipped_count = 0

        for _, row in df.iterrows():
            sale_id = int(clean_float_value(row.get('sale_id', row.iloc[0])))
            payment_date = str(row.get('payment_date', row.get('date', row.iloc[1])))
            amount_paid = clean_float_value(row.get('amount_paid', row.get('amount', row.iloc[2])))
            payment_method = str(row.get('payment_method', row.iloc[3]))

            # Check if Sale ID exists
            cursor.execute("SELECT gross_sales FROM customer_sales WHERE sale_id = %s;", (sale_id,))
            sale_res = cursor.fetchone()

            if not sale_res:
                log_and_print(f"   ⚠️ Skipping Payment (sale_id {sale_id}): Missing in customer_sales.", level="warning")
                skipped_count += 1
                continue

            gross_sales = float(sale_res[0])

            # Check existing payments balance
            cursor.execute("SELECT COALESCE(SUM(amount_paid), 0) FROM payment_splits WHERE sale_id = %s;", (sale_id,))
            already_paid = float(cursor.fetchone()[0])

            if (already_paid + amount_paid) > gross_sales:
                max_allowed = max(0.0, gross_sales - already_paid)
                log_and_print(f"   ⚠️ Skipping Payment (sale_id {sale_id}): Exceeds balance ({max_allowed:.2f} max allowed).", level="warning")
                skipped_count += 1
                continue

            insert_query = """
                INSERT INTO payment_splits (sale_id, payment_date, amount_paid, payment_method)
                VALUES (%s, %s, %s, %s);
            """
            cursor.execute(insert_query, (sale_id, payment_date, amount_paid, payment_method))
            inserted_count += 1

        log_and_print(f"   ✅ Payment Splits: Processed {row_count} CSV rows -> {inserted_count} inserted ({skipped_count} skipped).")


# -------------------------------------------------------------
# 5. CROSSCHECK & AUDIT FUNCTION
# -------------------------------------------------------------
def run_post_import_crosscheck(conn):
    log_and_print("\n==================================================")
    log_and_print("      🔍 RUNNING POST-IMPORT CROSSCHECK AUDIT     ")
    log_and_print("==================================================")

    # Crosscheck 1: Row Counts Across Tables
    tables = ['branches', 'users', 'customer_sales', 'payment_splits']
    for table in tables:
        df_count = pd.read_sql(f"SELECT COUNT(*) as cnt FROM {table};", conn)
        log_and_print(f"   • Total records in '{table}': {df_count['cnt'].iloc[0]}")

    # Crosscheck 2: Sales Total Sum
    sales_sum = pd.read_sql("SELECT COALESCE(SUM(gross_sales), 0) as total FROM customer_sales;", conn)
    log_and_print(f"   • Total Revenue across customer_sales: ${sales_sum['total'].iloc[0]:,.2f}")

    # Crosscheck 3: Check Orphan Sales (Unmapped Branches)
    orphan_df = pd.read_sql("""
        SELECT cs.branch_id, COUNT(*) as count 
        FROM customer_sales cs 
        LEFT JOIN branches b ON cs.branch_id = b.branch_id 
        WHERE b.branch_id IS NULL 
        GROUP BY cs.branch_id;
    """, conn)
    
    if orphan_df.empty:
        log_and_print("   ✅ Referential Integrity: All sales match existing branches.")
    else:
        log_and_print(f"   ⚠️ Unmapped Branches Found in customer_sales:\n{orphan_df}", level="warning")


# -------------------------------------------------------------
# 6. MAIN EXECUTION PIPELINE
# -------------------------------------------------------------
def import_and_verify():
    log_and_print("==================================================")
    log_and_print("      STARTING SEQUENTIAL INGESTION RUN           ")
    log_and_print("==================================================")

    if not os.path.exists(LOCAL_FOLDER_PATH):
        log_and_print(f"❌ Path does not exist: {LOCAL_FOLDER_PATH}", level="error")
        return

    csv_files = glob.glob(os.path.join(LOCAL_FOLDER_PATH, "*.csv"))
    if not csv_files:
        log_and_print(f"⚠️ No CSV files found in: {LOCAL_FOLDER_PATH}", level="warning")
        return

    # Sort CSV files according to dependency hierarchy
    sorted_files = sorted(csv_files, key=get_file_priority)

    log_and_print(f"📁 Found {len(sorted_files)} CSV file(s). Enforced Order:")
    for idx, f in enumerate(sorted_files, start=1):
        log_and_print(f"   {idx}. {os.path.basename(f)}")
    log_and_print("--------------------------------------------------")

    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()

        for file_path in sorted_files:
            process_csv_file(cursor, file_path)
            conn.commit()

        # Run Audit / Validation
        run_post_import_crosscheck(conn)

        log_and_print("\n🎉 PROCESS FINISHED SUCCESSFULLY!")

    except Error as e:
        if 'conn' in locals() and conn.is_connected():
            conn.rollback()
        log_and_print(f"❌ MySQL Error: {e}", level="error")

    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals() and conn.is_connected():
            conn.close()


if __name__ == "__main__":
    import_and_verify()