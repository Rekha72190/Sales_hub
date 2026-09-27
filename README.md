# Sales_hub
The Sales Intelligence Hub is a branch-based financial management and tracking system built to manage sales records, payment splits, and pending collections across multiple business branches.

# 📊 Sales Hub Analytics & Management System

An end-to-end multi-tenant Sales Management and Financial Tracking application built using **Streamlit**, **Python**, and **MySQL**. The system supports role-based access control (Super Admin vs. Branch Managers), flexible payment split logging, real-time KPI dashboards, and an embedded SQL query runner.

---

## 🚀 Key Features

- **🔐 Authentication & Role-Based Access Control (RBAC)**
  - **Super Admin**: Access to cross-branch aggregated metrics and full branch filtering.
  - **Branch Manager**: Restricted view scoped strictly to their assigned branch.

- **📈 Interactive Financial Dashboard**
  - Real-time KPI metrics: **Gross Revenue**, **Received Collections**, **Pending Balances**, and **Collection Percentages**.
  - Multi-dimensional filtering by **Branch**, **Course/Product**, and **Date Range**.

- **📝 Operations & Data Entry Workspace**
  - **Sales Entry**: Add new sales/student enrollment records into `customer_sales`.
  - **Payment Split Allocations**: Record partial or full installment payments in `payment_splits`.
  - **Smart Balance Auto-Fill**: Auto-detects exact pending balance to streamline payment collection and prevent overpayment.
  - **Automated Lifecycle Management**: Automatically updates sale status from `Open` to `Closed` once full payment is settled.

- **⚡ Advanced SQL Analytical Engine**
  - Includes 20 pre-configured analytical SQL queries covering monthly summaries, top performers, and pending collection thresholds.
  - Displays formatted raw SQL code alongside executed output tables.

---

## 🛠️ Tech Stack & Architecture

- **Frontend / UI**: [Streamlit](https://streamlit.io/)
- **Backend Language**: Python 3.10+
- **Database**: MySQL Server
- **Database Connectivity**: `mysql-connector-python` with **MySQLConnectionPool** (connection pooling)
- **Data Manipulation**: `pandas`

---

## 🗄️ Database Schema & Setup

Ensure MySQL is installed and running locally on port `3306`. Execute the following SQL scripts to initialize the database schema:

```sql
-- 1. Completely delete the database and all its tables, constraints, and triggers
DROP DATABASE IF EXISTS sales_hub_db;

-- 2. Create a clean, empty database
CREATE DATABASE sales_hub_db;

-- 3. Switch to the newly created database
USE sales_hub_db;

-- 1. Branches Table
CREATE TABLE branches (
    branch_id INT AUTO_INCREMENT PRIMARY KEY,
    branch_name VARCHAR(100) NOT NULL UNIQUE,
	branch_admin_name VARCHAR(100) NOT NULL
);

-- 2. Users Table
CREATE TABLE users (
    user_id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    password VARCHAR(255) NOT NULL,
    email VARCHAR(255) UNIQue,
    role ENUM('Super Admin', 'Admin') NOT NULL,
    branch_id INT DEFAULT NULL,
    FOREIGN KEY (branch_id) REFERENCES branches(branch_id) 
        ON DELETE RESTRICT 
        ON UPDATE CASCADE
);

-- 3. Customer Sales Table (Parent Table)
CREATE TABLE customer_sales (
    sale_id INT AUTO_INCREMENT PRIMARY KEY,
    branch_id INT NOT NULL,
    date DATE NOT NULL,
    name VARCHAR(100) NOT NULL,
    mobile_number VARCHAR(15),
    product_name VARCHAR(30),
    gross_sales DECIMAL(12,2) NOT NULL CHECK (gross_sales >= 0),
    received_amount DECIMAL(12,2) DEFAULT 0.00 CHECK (received_amount >= 0),
    
    -- STORED Generated Column for automatic calculation
    pending_amount DECIMAL(12,2) GENERATED ALWAYS AS (gross_sales - received_amount) STORED,
    
    -- Status Enum: Defaults to 'Open' when a sale is created
    status ENUM('Open', 'Close') DEFAULT 'Open' NOT NULL,
    
    -- Prevents overpayment at the database level
    CONSTRAINT chk_no_overpayment CHECK (received_amount <= gross_sales),
    
    FOREIGN KEY (branch_id) REFERENCES branches(branch_id) 
        ON DELETE RESTRICT 
        ON UPDATE CASCADE
);

-- 4. Payment Splits Table (Child Table)
CREATE TABLE payment_splits (
    payment_id INT AUTO_INCREMENT PRIMARY KEY,
    sale_id INT NOT NULL,
    payment_date DATE NOT NULL,
    amount_paid DECIMAL(12,2) NOT NULL CHECK (amount_paid > 0),
    payment_method ENUM('Cash', 'UPI', 'Card') NOT NULL,
    
    FOREIGN KEY (sale_id) REFERENCES customer_sales(sale_id) 
        ON DELETE RESTRICT 
        ON UPDATE CASCADE
);
📂 Project Structure
├── app.py              # Main Streamlit UI layout, page routes, forms & session state
├── db_engine.py        # Connection pooling, CRUD database operations, and SQL queries
├── requirements.txt    # Required Python dependencies
└── README.md           # Project documentation

⚡ Quick Start Guide
1. Clone the Repository
git clone [https://github.com/your-username/sales-hub-analytics.git](https://github.com/your-username/sales-hub-analytics.git)
cd sales-hub-analytics

2. Set Up Virtual Environment & Dependencies
# Create virtual environment
python -m venv .venv

# Activate environment (Windows)
.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

3. Configure Database Credentials
Open db_engine.py and update the DB_CONFIG dictionary with your local MySQL credentials:
DB_CONFIG = {
    'host': '127.0.0.1',
    'user': 'root',
    'password': 'YOUR_MYSQL_PASSWORD',
    'database': 'sales_hub_db',
    'port': 3306
}

4. Run the Streamlit Application
streamlit run app.py

📦 Requirements (requirements.txt)
If you haven't created a requirements.txt file yet, save these dependencies:
streamlit>=1.30.0
pandas>=2.0.0
mysql-connector-python>=8.0.0

📝 LicenseDistributed under the MIT License.
<FollowUp label="Would you like help uploading this project to GitHub using Git terminal commands?" query="Show me step-by-step terminal commands to upload my project to GitHub."/>




   
