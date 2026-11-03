# Olist sales dashboard
# Run from the project folder:  streamlit run dashboard.py

import os

import altair as alt
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

import queries
from db import connect

load_dotenv()
st.set_page_config(page_title="Olist sales", layout="wide")


@st.cache_resource
def get_con():
    return connect(os.getenv("DATA_DIR", "data/raw"))


# streamlit can run the page in several threads at once, and one duckdb
# connection can't be used by two of them -> each run gets its own cursor
con = get_con().cursor()

# all months in the usable period, for the slider
all_months = queries.monthly(con)["month"].tolist()

st.title("Olist sales dashboard")
st.caption("Brazilian marketplace, Jan 2017 – Aug 2018. Revenue = item prices of valid orders, R$.")

start, end = st.select_slider("Period", options=all_months, value=(all_months[0], all_months[-1]))

# ---- top numbers ----
t = queries.period_totals(con, start, end)
c1, c2, c3, c4 = st.columns(4)
c1.metric("Orders", f"{t['orders']:,}")
c2.metric("Revenue", f"R$ {t['revenue'] / 1e6:.2f}M")
c3.metric("Late deliveries", f"{t['late_pct']:.1f}%")
c4.metric("Avg delivery time", f"{t['avg_delivery_days']:.1f} days")

# ---- sales by month ----
st.subheader("Sales by month")
mo = queries.monthly(con, start, end)
left, right = st.columns(2)
left.markdown("**Orders**")
left.line_chart(mo, x="month", y="orders")
right.markdown("**Revenue, R$**")
right.line_chart(mo, x="month", y="revenue")

# ---- delivery ----
st.subheader("Delivery")
left, right = st.columns(2)
left.markdown("**Late deliveries, % of delivered orders**")
left.line_chart(mo, x="month", y="late_pct")
right.markdown("**Average delivery time, days**")
right.line_chart(mo, x="month", y="avg_delivery_days")

# ---- categories ----
st.subheader("Top categories by revenue")
cats = queries.top_categories(con, 10, start, end)
cat_df = pd.DataFrame(cats, columns=["category", "revenue"])
cat_df["category"] = cat_df["category"].str.replace("_", " ")
bars = (
    alt.Chart(cat_df)
    .mark_bar()
    .encode(
        x=alt.X("revenue:Q", title="Revenue, R$"),
        y=alt.Y("category:N", sort="-x", title=None),  # biggest on top
        tooltip=["category:N", alt.Tooltip("revenue:Q", format=",.0f")],
    )
)
st.altair_chart(bars)

# ---- states ----
st.subheader("By state")
states = queries.by_state(con, start, end)
st.dataframe(
    states,
    hide_index=True,
    column_config={
        "state": "State",
        "orders": st.column_config.NumberColumn("Orders", format="%d"),
        "revenue": st.column_config.NumberColumn("Revenue, R$", format="%.0f"),
        "late_pct": st.column_config.NumberColumn("Late, %", format="%.1f"),
        "avg_delivery_days": st.column_config.NumberColumn("Avg delivery, days", format="%.1f"),
    },
)
