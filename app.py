import streamlit as st
import datetime
import db_engine as db

st.set_page_config(page_title="Sales Hub Dashboard", page_icon="📊", layout="wide")

# -------------------------------------------------------------
# 1. AUTHENTICATION & SESSION STATE
# -------------------------------------------------------------
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False
if 'user' not in st.session_state:
    st.session_state['user'] = None

if not st.session_state['logged_in']:
    st.title("🔑 Sales Hub Login")
    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submit = st.form_submit_button("Login")
        
        if submit:
            user_data = db.authenticate_user(username, password)
            if user_data:
                st.session_state['logged_in'] = True
                st.session_state['user'] = user_data
                st.success(f"Welcome, {user_data['username']}!")
                st.rerun()
            else:
                st.error("Invalid username or password.")
    st.stop()

# -------------------------------------------------------------
# 2. NAVIGATION SIDEBAR
# -------------------------------------------------------------
user = st.session_state['user']
st.sidebar.title("Navigation")
st.sidebar.write("Go to")

nav_choice = st.sidebar.radio(
    "", 
    ["Dashboard & Reports", "Data Entry Workspace", "Advanced SQL Engine"]
)

st.sidebar.markdown("---")
st.sidebar.write(f"👤 User: **{user['username']}**")
st.sidebar.write(f"🔑 Role: **{user['role']}**")

if st.sidebar.button("Log Out"):
    st.session_state['logged_in'] = False
    st.session_state['user'] = None
    st.rerun()

# -------------------------------------------------------------
# PAGE 1: DASHBOARD & REPORTS
# -------------------------------------------------------------
if nav_choice == "Dashboard & Reports":
    st.title("📊 Interactive Reporting Dashboard")

    col_f1, col_f2, col_f3, col_f4 = st.columns(4)
    
    branches_df = db.get_branches()
    if user['role'] == 'Super Admin':
        branch_options = ['All'] + list(branches_df['branch_name'])
        selected_branch_name = col_f1.selectbox("Filter Branch", branch_options)
        if selected_branch_name == 'All':
            selected_branch_id = 'All'
        else:
            selected_branch_id = int(branches_df[branches_df['branch_name'] == selected_branch_name]['branch_id'].values[0])
    else:
        user_branch_id = int(user['branch_id'])
        user_branch_name = branches_df[branches_df['branch_id'] == user_branch_id]['branch_name'].values[0]
        col_f1.selectbox("Filter Branch", [user_branch_name], disabled=True)
        selected_branch_id = user_branch_id

    product_options = ['All'] + db.get_products()
    selected_product = col_f2.selectbox("Filter Product", product_options)

    start_date = col_f3.date_input("Start Date", value=datetime.date(2024, 1, 1))
    end_date = col_f4.date_input("End Date", value=datetime.date.today())

    df_sales = db.fetch_filtered_sales(selected_branch_id, selected_product, start_date, end_date)

    total_gross = df_sales['gross_sales'].sum() if not df_sales.empty else 0.0
    total_received = df_sales['received_amount'].sum() if not df_sales.empty else 0.0
    total_pending = df_sales['pending_amount'].sum() if not df_sales.empty else 0.0
    pending_pct = (total_pending / total_gross * 100) if total_gross > 0 else 0.0

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Gross Revenue", f"₹{total_gross:,.2f}")
    m2.metric("Received Amount", f"₹{total_received:,.2f}")
    m3.metric("Pending Amount", f"₹{total_pending:,.2f}")
    m4.metric("Pending Collection %", f"{pending_pct:.1f}%")

    st.markdown("---")
    st.subheader("Filtered Customer Sales Records")
    st.dataframe(df_sales, use_container_width=True)

# -------------------------------------------------------------
# PAGE 2: DATA ENTRY WORKSPACE
# -------------------------------------------------------------
elif nav_choice == "Data Entry Workspace":
    st.title("📝 Operations Record Creator")
    
    tab1, tab2 = st.tabs(["Add New Sales Entry", "Log Payment Split Details"])

    # ---------------------------------------------------------
    # TAB 1: ADD NEW SALES ENTRY
    # ---------------------------------------------------------
    with tab1:
        st.subheader("New Sale Generation")
        with st.form("new_sale_form"):
            branches_df = db.get_branches()
            if user['role'] == 'Super Admin':
                b_names = list(branches_df['branch_name'])
                selected_b_name = st.selectbox("Select Target Branch", b_names)
                target_b_id = int(branches_df[branches_df['branch_name'] == selected_b_name]['branch_id'].values[0])
            else:
                target_b_id = int(user['branch_id'])
                b_name_user = branches_df[branches_df['branch_id'] == target_b_id]['branch_name'].values[0]
                st.selectbox("Select Target Branch", [b_name_user], disabled=True)

            col1, col2 = st.columns(2)
            c_name = col1.text_input("Student Name")
            c_course = col2.selectbox("Select Course Name", ["AI", "Data Science", "Python Full Stack", "Web Development", "Cloud Computing"])

            col3, col4 = st.columns(2)
            c_mobile = col3.text_input("Mobile Number")
            c_date = col4.date_input("Joining Date", value=datetime.date.today())

            c_gross = st.number_input("Gross Sales Amount (₹)", min_value=0.0, step=500.0, format="%.2f")
            st.selectbox("Initial Order Status", ["Open"], disabled=True)

            submit_sale = st.form_submit_button("Publish Sales Entry")
            
            if submit_sale:
                if not c_name.strip():
                    st.error("⚠️ Please enter Student Name.")
                elif c_gross <= 0:
                    st.error("⚠️ Gross Sales Amount must be greater than 0.")
                else:
                    success, msg = db.insert_new_sale(target_b_id, c_date, c_name, c_mobile, c_course, c_gross)
                    if success:
                        st.success("✅ " + msg)
                        st.rerun()
                    else:
                        st.error("❌ " + msg)

        st.markdown("---")
        st.subheader("📋 Output Verification: Recent Customer Sales Table (`customer_sales`)")
        recent_sales_df = db.get_recent_sales(limit=10)
        st.dataframe(recent_sales_df, use_container_width=True)

    # ---------------------------------------------------------
    # TAB 2: LOG PAYMENT SPLIT DETAILS
    # ---------------------------------------------------------
    with tab2:
        st.subheader("Post Payment Installment Split")
        
        filter_b = 'All' if user['role'] == 'Super Admin' else int(user['branch_id'])
        active_sales = db.get_active_pending_sales(filter_b)

        if active_sales.empty:
            st.info("ℹ️ No active sales with pending balances were found for your branch.")
        else:
            with st.form("payment_split_form"):
                active_sales['display_label'] = active_sales.apply(
                    lambda r: f"ID {int(r['sale_id'])} - {r['customer_name']} ({r['product_name']}) - ₹{float(r['pending_balance']):,.2f} Pending", 
                    axis=1
                )
                
                selected_label = st.selectbox("Select Target Active Sale ID Asset", active_sales['display_label'])
                selected_sale_id = int(selected_label.split(" - ")[0].replace("ID ", ""))

                # Fetch exact remaining balance for auto-filling
                current_pending = float(active_sales[active_sales['sale_id'] == selected_sale_id]['pending_balance'].values[0])

                p_channel = st.selectbox("Payment Collection Channel", ["Cash", "UPI", "Credit/Debit Card", "Net Banking"])
                
                # Auto-fills current_pending directly into the input box
                p_amount = st.number_input(
                    "Collected Split Amount Balance (₹)", 
                    min_value=0.01, 
                    max_value=current_pending, 
                    value=current_pending, 
                    step=100.0, 
                    format="%.2f"
                )
                p_date = st.date_input("Payment Date", value=datetime.date.today())

                submit_pay = st.form_submit_button("Apply Payment Allocation")
                
                if submit_pay:
                    success, msg = db.insert_payment_split(selected_sale_id, p_date, p_amount, p_channel)
                    if success:
                        st.success("✅ " + msg)
                        st.rerun()
                    else:
                        st.error("❌ " + msg)

        st.markdown("---")
        st.subheader("📋 Output Verification: Payment Splits Table (`payment_splits`)")
        recent_payments_df = db.get_recent_payment_splits(limit=10)
        st.dataframe(recent_payments_df, use_container_width=True)

# -------------------------------------------------------------
# 3. ADVANCED SQL ENGINE
# -------------------------------------------------------------
elif nav_choice == "Advanced SQL Engine":
    st.title("⚡ Advanced SQL Analytical Engine")
    
    selected_query_title = st.selectbox("Choose Analytical Query", list(db.ANALYTICAL_QUERIES.keys()))
    raw_query = db.ANALYTICAL_QUERIES[selected_query_title]

    with st.expander("View Underlying SQL Code", expanded=True):
        st.code(raw_query, language="sql")

    if st.button("Execute Query"):
        res_df = db.run_custom_query(raw_query)
        st.dataframe(res_df, use_container_width=True)