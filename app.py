# app.py
# Sales & Stock Management Dashboard linked to a fixed Google Sheet with Profit calculation
# Fixed imports and Streamlit data leak warning by setting page config first
# Requirements: pip install streamlit pandas gspread oauth2client plotly

# --- Standard library imports ------------------------------------------------
from datetime import datetime

# --- Streamlit setup --------------------------------------------------------
import streamlit as st
st.set_page_config(layout="wide", page_title="Sales & Stock Dashboard")

# --- Third-party imports ----------------------------------------------------
import pandas as pd
import plotly.express as px
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- Config -----------------------------------------------------------------
SHEET_URL = "https://docs.google.com/spreadsheets/d/1r4BLV7NFdtagJPjjneqKyUrGbb1qnzyUqCaDuQHqFZU/edit?gid=0"
CREDS_FILE = "service_account.json"  # Make sure this file is in your app folder

# --- Google Sheets Setup ---------------------------------------------------

def get_gsheet_client(creds_file):
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_name(creds_file, scope)
    client = gspread.authorize(creds)
    return client

@st.cache_data(ttl=60)
def load_data():
    client = get_gsheet_client(CREDS_FILE)
    spreadsheet = client.open_by_url(SHEET_URL)
    sales_ws = spreadsheet.worksheet("Sales")
    stock_ws = spreadsheet.worksheet("Stock")
    sales_df = pd.DataFrame(sales_ws.get_all_records())
    stock_df = pd.DataFrame(stock_ws.get_all_records())
    return sales_df, stock_df, sales_ws, stock_ws

# --- Data preparation -------------------------------------------------------

def sanitize_and_prepare(sales_df, stock_df):
    sales_df = sales_df.copy()
    stock_df = stock_df.copy()

    # Ensure correct types
    if "Date" in sales_df.columns:
        sales_df["Date"] = pd.to_datetime(sales_df["Date"], errors="coerce")
    for col in ["Quantity Sold", "Unit Price", "Cost Price"]:
        if col not in sales_df.columns:
            sales_df[col] = 0
    sales_df["Total"] = sales_df["Quantity Sold"] * sales_df["Unit Price"]
    sales_df["Profit"] = (sales_df["Unit Price"] - sales_df["Cost Price"]) * sales_df["Quantity Sold"]

    for col in ["Opening Stock", "Stock In", "Stock Out", "Min Threshold"]:
        if col not in stock_df.columns:
            stock_df[col] = 0
    for col in ["Opening Stock", "Stock In", "Stock Out", "Min Threshold"]:
        stock_df[col] = pd.to_numeric(stock_df[col], errors="coerce").fillna(0).astype(int)

    # Aggregate sales by product
    sales_agg = sales_df.groupby("Product", as_index=False).agg({
        "Quantity Sold": "sum",
        "Total": "sum",
        "Profit": "sum"
    })
    sales_agg.rename(columns={"Quantity Sold": "Total Sold", "Total": "Sales Value", "Profit": "Total Profit"}, inplace=True)

    # Merge with stock
    merged = pd.merge(stock_df, sales_agg, on="Product", how="left")
    merged["Total Sold"] = merged["Total Sold"].fillna(0).astype(int)
    merged["Sales Value"] = merged["Sales Value"].fillna(0.0)
    merged["Total Profit"] = merged["Total Profit"].fillna(0.0)
    merged["Current Stock"] = merged["Opening Stock"] + merged["Stock In"] - merged["Stock Out"] - merged["Total Sold"]

    return sales_df, stock_df, merged

# --- Main App ---------------------------------------------------------------

def main():
    st.title("📊 Sales & Stock Management Dashboard (Google Sheets)")

    try:
        sales_df_raw, stock_df_raw, sales_ws, stock_ws = load_data()
    except Exception as e:
        st.error(f"Could not load Google Sheet: {e}")
        st.stop()

    sales_df, stock_df, merged = sanitize_and_prepare(sales_df_raw, stock_df_raw)

    # KPI Cards
    col1, col2, col3, col4, col5 = st.columns([2,2,2,2,2])
    total_sales_value = sales_df['Total'].sum()
    total_units_sold = int(sales_df['Quantity Sold'].sum())
    total_current_stock = int(merged['Current Stock'].sum())
    low_stock_count = int((merged['Current Stock'] <= merged['Min Threshold']).sum())
    total_profit = sales_df['Profit'].sum()

    col1.metric("Total Sales", f"{total_sales_value:,.2f}")
    col2.metric("Units Sold", f"{total_units_sold}")
    col3.metric("Total Current Stock", f"{total_current_stock}")
    col4.metric("Low-stock Items", f"{low_stock_count}")
    col5.metric("Total Profit", f"{total_profit:,.2f}")

    st.markdown("---")

    # Layout
    left, right = st.columns((2,1))

    with left:
        st.subheader("Sales Overview")
        if not sales_df.empty:
            min_date = sales_df['Date'].min()
            max_date = sales_df['Date'].max()
            start_date, end_date = st.date_input("Select date range", value=(min_date.date(), max_date.date()))

            product_list = ['All'] + sorted(sales_df['Product'].dropna().unique().tolist())
            product_sel = st.selectbox("Filter by product", product_list)

            filtered_sales = sales_df[(sales_df['Date'] >= pd.to_datetime(start_date)) & (sales_df['Date'] <= pd.to_datetime(end_date))]
            if product_sel != 'All':
                filtered_sales = filtered_sales[filtered_sales['Product'] == product_sel]

            if not filtered_sales.empty:
                sales_by_date = filtered_sales.groupby('Date', as_index=False)['Total'].sum()
                fig_sales = px.line(sales_by_date, x='Date', y='Total', title='Sales Over Time')
                st.plotly_chart(fig_sales, use_container_width=True)

                profit_by_date = filtered_sales.groupby('Date', as_index=False)['Profit'].sum()
                fig_profit = px.line(profit_by_date, x='Date', y='Profit', title='Profit Over Time')
                st.plotly_chart(fig_profit, use_container_width=True)

                top_products = filtered_sales.groupby('Product', as_index=False).agg({"Quantity Sold": "sum", "Total": "sum", "Profit": "sum"}).sort_values('Quantity Sold', ascending=False).head(10)
                st.write("Top products (by units sold)")
                st.dataframe(top_products)

            st.markdown("---")
            st.subheader("Sales Records")
            st.dataframe(filtered_sales.reset_index(drop=True))
        else:
            st.info("No sales data available.")

    with right:
        st.subheader("Stock Overview")
        st.dataframe(merged[['Product','Category','Opening Stock','Stock In','Stock Out','Total Sold','Current Stock','Min Threshold','Sales Value','Total Profit']].sort_values('Current Stock'))

        st.markdown("### Low-stock Alerts")
        low_stock_df = merged[merged['Current Stock'] <= merged['Min Threshold']]
        if not low_stock_df.empty:
            st.warning(f"{len(low_stock_df)} product(s) at or below threshold")
            st.dataframe(low_stock_df[['Product','Current Stock','Min Threshold']])
        else:
            st.success("No low-stock items")

        st.markdown("---")
        st.subheader("Adjust Stock (updates Google Sheet)")
        product_to_adjust = st.selectbox("Product to adjust", options=merged['Product'].tolist())
        add_in = st.number_input("Add stock (Stock In)", value=0, step=1)
        add_out = st.number_input("Remove stock (Stock Out)", value=0, step=1)
        set_threshold = st.number_input("Set Min Threshold", value=int(merged.loc[merged['Product'] == product_to_adjust, 'Min Threshold'].iloc[0]), step=1)

        if st.button("Apply Adjustment"):
            idx = merged[merged['Product'] == product_to_adjust].index[0]
            merged.at[idx, 'Stock In'] += int(add_in)
            merged.at[idx, 'Stock Out'] += int(add_out)
            merged.at[idx, 'Min Threshold'] = int(set_threshold)
            merged.at[idx, 'Current Stock'] = merged.at[idx, 'Opening Stock'] + merged.at[idx, 'Stock In'] - merged.at[idx, 'Stock Out'] - merged.at[idx, 'Total Sold']

            row_num = stock_df[stock_df['Product'] == product_to_adjust].index[0] + 2
            stock_ws.update_cell(row_num, stock_df.columns.get_loc("Stock In")+1, int(merged.at[idx,'Stock In']))
            stock_ws.update_cell(row_num, stock_df.columns.get_loc("Stock Out")+1, int(merged.at[idx,'Stock Out']))
            stock_ws.update_cell(row_num, stock_df.columns.get_loc("Min Threshold
