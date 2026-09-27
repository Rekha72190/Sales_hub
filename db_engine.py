import mysql.connector
from mysql.connector import pooling
import pandas as pd

# -------------------------------------------------------------
# 1. DATABASE CONFIGURATION & CONNECTION POOLING
# -------------------------------------------------------------
DB_CONFIG = {
    'host': '127.0.0.1',
    'user': 'root',
    'password': '123456789',
    'database': 'sales_hub_db',
    'port': 3306
}

db_pool = mysql.connector.pooling.MySQLConnectionPool(
    pool_name="sales_pool",
    pool_size=5,
    **DB_CONFIG
)

def get_connection():
    return db_pool.get_connection()

# -------------------------------------------------------------
# 2. AUTHENTICATION & ROLE CHECKS
# -------------------------------------------------------------
def authenticate_user(username, password):
    conn = get_connection()
    try:
        query = "SELECT user_id, username, role, branch_id FROM users WHERE username = %s AND password = %s;"
        df = pd.read_sql(query, conn, params=(str(username), str(password)))
        if not df.empty:
            return df.iloc[0].to_dict()
        return None
    finally:
        conn.close()

# -------------------------------------------------------------
# 3. FILTERED DASHBOARD PIPELINE
# -------------------------------------------------------------
def get_branches():
    conn = get_connection()
    try:
        return pd.read_sql("SELECT branch_id, branch_name FROM branches ORDER BY branch_name;", conn)
    finally:
        conn.close()

def get_products():
    conn = get_connection()
    try:
        df = pd.read_sql("SELECT DISTINCT product_name FROM customer_sales WHERE product_name IS NOT NULL AND product_name != '';", conn)
        return df['product_name'].tolist()
    finally:
        conn.close()

def fetch_filtered_sales(branch_id=None, product_name=None, start_date=None, end_date=None):
    conn = get_connection()
    try:
        query = """
            SELECT 
                cs.sale_id,
                b.branch_name,
                cs.date,
                cs.name AS customer_name,
                cs.mobile_number,
                cs.product_name,
                cs.gross_sales,
                COALESCE(SUM(ps.amount_paid), 0) AS received_amount,
                (cs.gross_sales - COALESCE(SUM(ps.amount_paid), 0)) AS pending_amount,
                cs.status
            FROM customer_sales cs
            LEFT JOIN branches b ON cs.branch_id = b.branch_id
            LEFT JOIN payment_splits ps ON cs.sale_id = ps.sale_id
            WHERE 1=1
        """
        params = []

        if branch_id and branch_id != 'All':
            query += " AND cs.branch_id = %s"
            params.append(int(branch_id))
            
        if product_name and product_name != 'All':
            query += " AND cs.product_name = %s"
            params.append(str(product_name))

        if start_date and end_date:
            query += " AND cs.date BETWEEN %s AND %s"
            params.extend([str(start_date), str(end_date)])

        query += " GROUP BY cs.sale_id, b.branch_name, cs.date, cs.name, cs.mobile_number, cs.product_name, cs.gross_sales, cs.status ORDER BY cs.sale_id DESC;"

        return pd.read_sql(query, conn, params=tuple(params) if params else None)
    finally:
        conn.close()

# -------------------------------------------------------------
# 4. DATA ENTRY & PAYMENT ALLOCATION
# -------------------------------------------------------------
def insert_new_sale(branch_id, date, name, mobile, product, gross_sales):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        query = """
            INSERT INTO customer_sales (branch_id, date, name, mobile_number, product_name, gross_sales, status)
            VALUES (%s, %s, %s, %s, %s, %s, 'Open');
        """
        cursor.execute(query, (int(branch_id), str(date), str(name), str(mobile), str(product), float(gross_sales)))
        conn.commit()
        return True, "New customer sale recorded successfully!"
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        cursor.close()
        conn.close()

def get_recent_sales(limit=10):
    """Fetches recently inserted sales records to display output tables."""
    conn = get_connection()
    try:
        query = """
            SELECT cs.sale_id, b.branch_name, cs.date, cs.name, cs.mobile_number, cs.product_name, cs.gross_sales, cs.status 
            FROM customer_sales cs
            LEFT JOIN branches b ON cs.branch_id = b.branch_id
            ORDER BY cs.sale_id DESC LIMIT %s;
        """
        return pd.read_sql(query, conn, params=(int(limit),))
    finally:
        conn.close()

def get_active_pending_sales(branch_id=None):
    """Returns open sales that have an outstanding balance > 0."""
    conn = get_connection()
    try:
        query = """
            SELECT 
                cs.sale_id,
                cs.name AS customer_name,
                cs.product_name,
                cs.gross_sales,
                (cs.gross_sales - COALESCE(SUM(ps.amount_paid), 0)) AS pending_balance
            FROM customer_sales cs
            LEFT JOIN payment_splits ps ON cs.sale_id = ps.sale_id
            WHERE 1=1
        """
        params = []
        if branch_id and branch_id != 'All':
            query += " AND cs.branch_id = %s"
            params.append(int(branch_id))

        query += " GROUP BY cs.sale_id, cs.name, cs.product_name, cs.gross_sales HAVING pending_balance > 0 ORDER BY cs.sale_id DESC;"
        
        return pd.read_sql(query, conn, params=tuple(params) if params else None)
    finally:
        conn.close()

def insert_payment_split(sale_id, payment_date, amount_paid, payment_method):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        # Check balance
        cursor.execute("""
            SELECT (cs.gross_sales - COALESCE(SUM(ps.amount_paid), 0)) AS balance
            FROM customer_sales cs
            LEFT JOIN payment_splits ps ON cs.sale_id = ps.sale_id
            WHERE cs.sale_id = %s
            GROUP BY cs.sale_id, cs.gross_sales;
        """, (int(sale_id),))
        res = cursor.fetchone()
        
        if not res:
            return False, "Sale ID not found."
            
        remaining_balance = float(res[0])
        amount_paid = float(amount_paid)

        if amount_paid > remaining_balance + 0.01:  # Small float tolerance
            return False, f"Payment amount (₹{amount_paid:,.2f}) exceeds pending balance (₹{remaining_balance:,.2f})."

        # Record payment
        insert_query = """
            INSERT INTO payment_splits (sale_id, payment_date, amount_paid, payment_method)
            VALUES (%s, %s, %s, %s);
        """
        cursor.execute(insert_query, (int(sale_id), str(payment_date), amount_paid, str(payment_method)))

        # Update status if fully paid
        if (remaining_balance - amount_paid) <= 0.01:
            cursor.execute("UPDATE customer_sales SET status = 'Closed' WHERE sale_id = %s;", (int(sale_id),))

        conn.commit()
        return True, "Payment split recorded successfully!"
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        cursor.close()
        conn.close()

def get_recent_payment_splits(limit=10):
    """Fetches recent payment splits safely without relying on a specific ID column name."""
    conn = get_connection()
    try:
        query = """
            SELECT 
                ps.sale_id, 
                cs.name AS customer_name, 
                ps.payment_date, 
                ps.amount_paid, 
                ps.payment_method
            FROM payment_splits ps
            JOIN customer_sales cs ON ps.sale_id = cs.sale_id
            ORDER BY ps.payment_date DESC, ps.sale_id DESC 
            LIMIT %s;
        """
        return pd.read_sql(query, conn, params=(int(limit),))
    finally:
        conn.close()

# -------------------------------------------------------------
# 5. PRE-CONFIGURED 20 SQL ANALYTICAL QUERIES
# -------------------------------------------------------------
ANALYTICAL_QUERIES = {
    "1. All Customer Sales": "SELECT * FROM customer_sales;",
    "2. All Branches": "SELECT * FROM branches;",
    "3. All Payment Splits": "SELECT * FROM payment_splits;",
    "4. All Sales with Status = 'Open'": "SELECT * FROM customer_sales WHERE status = 'Open';",
    "5. Sales Belonging to Chennai Branch": "SELECT cs.* FROM customer_sales cs JOIN branches b ON cs.branch_id = b.branch_id WHERE b.branch_name = 'Chennai';",
    "6. Total Gross Sales Across All Branches": "SELECT SUM(gross_sales) AS total_gross_sales FROM customer_sales;",
    "7. Total Received Amount Across All Sales": "SELECT SUM(amount_paid) AS total_received FROM payment_splits;",
    "8. Total Pending Amount Across All Sales": "SELECT (SUM(cs.gross_sales) - COALESCE(SUM(ps.amount_paid), 0)) AS total_pending FROM customer_sales cs LEFT JOIN payment_splits ps ON cs.sale_id = ps.sale_id;",
    "9. Total Number of Sales per Branch": "SELECT b.branch_name, COUNT(cs.sale_id) AS total_sales FROM branches b LEFT JOIN customer_sales cs ON b.branch_id = cs.branch_id GROUP BY b.branch_name;",
    "10. Average Gross Sales Amount": "SELECT AVG(gross_sales) AS avg_gross_sales FROM customer_sales;",
    "11. Sales Details Along with Branch Name": "SELECT cs.sale_id, b.branch_name, cs.name, cs.product_name, cs.gross_sales FROM customer_sales cs JOIN branches b ON cs.branch_id = b.branch_id;",
    "12. Sales Details Along with Total Payment Received": "SELECT cs.sale_id, cs.name, cs.gross_sales, COALESCE(SUM(ps.amount_paid), 0) AS total_paid FROM customer_sales cs LEFT JOIN payment_splits ps ON cs.sale_id = ps.sale_id GROUP BY cs.sale_id, cs.name, cs.gross_sales;",
    "13. Branch-Wise Total Gross Sales": "SELECT b.branch_name, SUM(cs.gross_sales) AS branch_gross_sales FROM branches b JOIN customer_sales cs ON b.branch_id = cs.branch_id GROUP BY b.branch_name;",
    "14. Sales Along with Payment Method Used": "SELECT cs.sale_id, cs.name, ps.payment_method, ps.amount_paid FROM customer_sales cs JOIN payment_splits ps ON cs.sale_id = ps.sale_id;",
    "15. Sales Along with Branch Admin Name": "SELECT cs.sale_id, cs.name, b.branch_name, b.branch_admin_name FROM customer_sales cs JOIN branches b ON cs.branch_id = b.branch_id;",
    "16. Sales Where Pending Amount > 5000": "SELECT cs.sale_id, cs.name, cs.gross_sales, (cs.gross_sales - COALESCE(SUM(ps.amount_paid), 0)) AS pending FROM customer_sales cs LEFT JOIN payment_splits ps ON cs.sale_id = ps.sale_id GROUP BY cs.sale_id, cs.name, cs.gross_sales HAVING pending > 5000;",
    "17. Top 3 Highest Gross Sales": "SELECT * FROM customer_sales ORDER BY gross_sales DESC LIMIT 3;",
    "18. Branch with Highest Total Gross Sales": "SELECT b.branch_name, SUM(cs.gross_sales) AS total_gross FROM branches b JOIN customer_sales cs ON b.branch_id = cs.branch_id GROUP BY b.branch_name ORDER BY total_gross DESC LIMIT 1;",
    "19. Monthly Sales Summary": "SELECT DATE_FORMAT(date, '%Y-%m') AS sale_month, COUNT(sale_id) AS total_sales, SUM(gross_sales) AS monthly_gross FROM customer_sales GROUP BY sale_month ORDER BY sale_month DESC;",
    "20. Payment Method-Wise Total Collection": "SELECT payment_method, SUM(amount_paid) AS total_collected FROM payment_splits GROUP BY payment_method;"
}

def run_custom_query(query_str):
    conn = get_connection()
    try:
        return pd.read_sql(query_str, conn)
    finally:
        conn.close()