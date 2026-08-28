"""
app.py — Streamlit dashboard for the Olist e-commerce delivery analysis.

Core business question: how does delivery delay affect review scores and the
likelihood of repeat purchases? Supporting angles: payment behavior, order
density/revenue by state, on-time vs. late delivery trend over time.

Run with: streamlit run src/app.py
"""

from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

import etl
import metrics

# ---- Palette: fixed-order categorical hues + status pair (colorblind-safe) ----
COLOR_GOOD = "#0ca30c"      # status: on-time / good
COLOR_CRITICAL = "#d03b3b"  # status: late / critical
COLOR_BLUE = "#2a78d6"      # neutral magnitude (bar length already encodes value)
MUTED = "#898781"

CATEGORICAL_MAP = {
    "credit_card": "#2a78d6",
    "boleto": "#eb6834",
    "voucher": "#1baf7a",
    "debit_card": "#eda100",
    "not_defined": "#898781",
}
ORDINAL_BLUES_MAP = {
    "1": "#86b6ef",
    "2": "#5598e7",
    "3": "#2a78d6",
    "4-6": "#1c5cab",
    "7-12": "#104281",
    "13+": "#0d366b",
}

st.set_page_config(page_title="Olist Delivery & Review Analytics", layout="wide")


def style_fig(fig, title: str | None = None, bar_radius: bool = False):
    """Shared chart chrome tuned for Streamlit's dark theme: transparent
    background so charts blend into the page instead of sitting in a
    mismatched light card, soft muted gridlines instead of harsh default
    ones, and (optionally) rounded bar corners for a less "sharp" look."""
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#c3c2b7", size=13, family="system-ui, -apple-system, 'Segoe UI', sans-serif"),
        title=dict(text=title, font=dict(color="#ffffff", size=16)) if title else None,
        margin=dict(l=40, r=20, t=55 if title else 20, b=40),
        hoverlabel=dict(bgcolor="#22221f", font_color="#ffffff", bordercolor="#3a3a37"),
        xaxis=dict(gridcolor="#2c2c2a", zerolinecolor="#3a3a37", linecolor="#3a3a37", showline=True),
        yaxis=dict(gridcolor="#2c2c2a", zerolinecolor="#3a3a37", linecolor="#3a3a37", showline=True),
    )
    if bar_radius:
        fig.update_traces(marker_cornerradius=4, selector=dict(type="bar"))
    return fig


@st.cache_data
def get_data() -> pd.DataFrame:
    """Load the processed dataset, building it from raw CSVs on first run if needed."""
    if not metrics.PROCESSED_PATH.exists():
        raw_df = etl.build_analysis_dataset()
        etl.save_processed(raw_df)
    return metrics.load_processed()


df = get_data()

st.title("Olist E-Commerce: Delivery Delay, Reviews & Repeat Purchases")
st.caption(
    "How does delivery delay affect review scores and the likelihood of repeat "
    "purchases? Brazilian e-commerce orders on the Olist marketplace."
)

# ---------------- Sidebar filters ----------------
st.sidebar.header("Filters")

min_date = df["order_purchase_timestamp"].min().date()
max_date = df["order_purchase_timestamp"].max().date()

date_range = st.sidebar.date_input(
    "Order date range",
    value=(min_date, max_date),
    min_value=min_date,
    max_value=max_date,
)
if isinstance(date_range, tuple) and len(date_range) == 2:
    start_date, end_date = date_range
else:
    start_date, end_date = min_date, max_date

all_states = sorted(df["customer_state"].dropna().unique())
selected_states = st.sidebar.multiselect("Customer state", options=all_states, default=all_states)

if not selected_states:
    st.warning("Select at least one state in the sidebar to see results.")
    st.stop()

state_mask = df["customer_state"].isin(selected_states)
date_mask = (df["order_purchase_timestamp"].dt.date >= start_date) & (
    df["order_purchase_timestamp"].dt.date <= end_date
)
filtered_df = df.loc[state_mask & date_mask]

if filtered_df.empty:
    st.warning("No orders match the selected filters.")
    st.stop()

# Repeat-purchase metrics look at a customer's FULL order history, so the date
# filter (which would truncate that history) intentionally does not apply here —
# only the state filter carries over.
repeat_scope_df = df.loc[state_mask]

# ---------------- KPI row ----------------
delay_stats = metrics.avg_delivery_delay(filtered_df)
late_stats = metrics.pct_late_deliveries(filtered_df)
avg_review = filtered_df["review_score"].mean()
repeat_stats = metrics.repeat_purchase_rate(repeat_scope_df)

kpi1, kpi2, kpi3, kpi4 = st.columns(4)
kpi1.metric(
    "Avg. Delivery Delay",
    f"{delay_stats['mean_delay_days']:+.1f} days" if delay_stats["mean_delay_days"] is not None else "—",
    help="Actual delivery date minus estimated delivery date. Negative = arrived early.",
)
kpi2.metric(
    "Late Delivery Rate",
    f"{late_stats['pct_late']:.1f}%" if late_stats["pct_late"] is not None else "—",
)
kpi3.metric(
    "Avg. Review Score",
    f"{avg_review:.2f} / 5" if pd.notna(avg_review) else "—",
)
kpi4.metric(
    "Repeat Purchase Rate",
    f"{repeat_stats['repeat_purchase_rate_pct']:.1f}%"
    if repeat_stats["repeat_purchase_rate_pct"] is not None
    else "—",
    help="Share of customers with more than one order, based on full order history (state filter applies; date filter does not).",
)

st.divider()

# ---------------- Core question: delay -> reviews & repeat purchases ----------------
st.subheader("Does a late delivery change customer behavior?")

col_a, col_b = st.columns(2)

with col_a:
    delivered = filtered_df.loc[filtered_df["is_delivered"] & filtered_df["review_score"].notna()].copy()
    delivered["review_score"] = delivered["review_score"].astype(int).astype(str)
    fig_box = px.box(
        delivered,
        x="review_score",
        y="delivery_delay_days",
        points=False,
        color_discrete_sequence=[COLOR_BLUE],
        category_orders={"review_score": ["1", "2", "3", "4", "5"]},
        labels={"review_score": "Review score", "delivery_delay_days": "Delivery delay (days)"},
    )
    fig_box.update_traces(
        fillcolor="rgba(42, 120, 214, 0.35)",
        line=dict(color=COLOR_BLUE, width=1.5),
        marker=dict(color=COLOR_BLUE),
    )
    fig_box.add_hline(y=0, line_dash="dot", line_width=1, line_color=MUTED)
    fig_box.update_layout(showlegend=False, yaxis_range=[-45, 45])
    style_fig(fig_box, "Delivery delay by review score")
    st.plotly_chart(fig_box, use_container_width=True, theme=None)
    st.caption(
        "Dotted line = delivered exactly on the estimated date. Late orders "
        "(above the line) skew sharply toward lower review scores. Cropped to "
        "±45 days for readability — a small number of extreme outliers fall outside this range."
    )

with col_b:
    repeat_by_delivery = metrics.repeat_purchase_rate_by_first_delivery(repeat_scope_df)
    fig_repeat = px.bar(
        repeat_by_delivery,
        x="first_order_status",
        y="repeat_rate_pct",
        color="first_order_status",
        color_discrete_map={"On-time": COLOR_GOOD, "Late": COLOR_CRITICAL},
        category_orders={"first_order_status": ["On-time", "Late"]},
        text="repeat_rate_pct",
        labels={"first_order_status": "First delivery status", "repeat_rate_pct": "Repeat purchase rate (%)"},
    )
    fig_repeat.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
    fig_repeat.update_layout(showlegend=False, yaxis_range=[0, repeat_by_delivery["repeat_rate_pct"].max() * 1.3])
    style_fig(fig_repeat, "Repeat purchase rate by first-delivery outcome", bar_radius=True)
    st.plotly_chart(fig_repeat, use_container_width=True, theme=None)
    st.caption("Segmented by whether a customer's first delivered order arrived on-time or late.")

st.divider()

# ---------------- Delivery performance over time ----------------
st.subheader("Delivery performance over time")
trend = metrics.monthly_delivery_trend(filtered_df)
fig_trend = px.line(
    trend,
    x="order_year_month",
    y="pct_late",
    markers=True,
    color_discrete_sequence=[COLOR_CRITICAL],
    labels={"order_year_month": "Month", "pct_late": "Late deliveries (%)"},
)
fig_trend.update_traces(
    line=dict(shape="spline", smoothing=0.6, width=2.5),
    marker=dict(size=7, line=dict(width=1, color="#1a1a19")),
)
fig_trend.update_layout(xaxis_tickangle=-45)
style_fig(fig_trend, "Monthly late-delivery rate")
st.plotly_chart(fig_trend, use_container_width=True, theme=None)

st.divider()

# ---------------- Order density & revenue by state ----------------
st.subheader("Order density & revenue by state")
state_summary = metrics.revenue_orders_by_state(filtered_df).head(15).sort_values("n_orders")
fig_state = px.bar(
    state_summary,
    x="n_orders",
    y="customer_state",
    orientation="h",
    color_discrete_sequence=[COLOR_BLUE],
    labels={"n_orders": "Number of orders", "customer_state": "State"},
    hover_data=["total_revenue", "avg_order_value"],
)
style_fig(fig_state, "Top 15 states by order volume", bar_radius=True)
st.plotly_chart(fig_state, use_container_width=True, theme=None)

st.divider()

# ---------------- Payment behavior ----------------
st.subheader("Payment behavior")
col_p1, col_p2 = st.columns(2)

with col_p1:
    pay_dist = metrics.payment_type_distribution(filtered_df)
    fig_pay = px.bar(
        pay_dist,
        x="payment_type",
        y="n_orders",
        color="payment_type",
        color_discrete_map=CATEGORICAL_MAP,
        category_orders={"payment_type": list(pay_dist["payment_type"])},
        labels={"payment_type": "Payment type", "n_orders": "Orders"},
    )
    fig_pay.update_layout(showlegend=False)
    style_fig(fig_pay, "Orders by payment type", bar_radius=True)
    st.plotly_chart(fig_pay, use_container_width=True, theme=None)

with col_p2:
    inst_dist = metrics.installment_distribution(filtered_df)
    inst_dist["installments"] = inst_dist["installments"].astype(str)
    fig_inst = px.bar(
        inst_dist,
        x="installments",
        y="n_orders",
        color="installments",
        color_discrete_map=ORDINAL_BLUES_MAP,
        category_orders={"installments": ["1", "2", "3", "4-6", "7-12", "13+"]},
        labels={"installments": "Installments", "n_orders": "Orders"},
    )
    fig_inst.update_layout(showlegend=False)
    style_fig(fig_inst, "Orders by installment count", bar_radius=True)
    st.plotly_chart(fig_inst, use_container_width=True, theme=None)

st.divider()

# ---------------- Explore: open-ended dimension x metric ----------------
st.subheader("Explore your own question")
st.caption(
    "Pick a dimension and a metric to build a chart from the filtered data above — "
    "for questions the fixed charts on this page don't specifically answer."
)

explore_df = metrics.prepare_explore_columns(filtered_df)

col_dim, col_metric = st.columns(2)
with col_dim:
    dimension_label = st.selectbox("Break down by", list(metrics.EXPLORE_DIMENSIONS.keys()))
with col_metric:
    metric_label = st.selectbox("Measure", metrics.EXPLORE_METRICS)

dimension_col = metrics.EXPLORE_DIMENSIONS[dimension_label]
explore_result = metrics.explore_by(explore_df, dimension_col, metric_label)

ORDERED_CATEGORIES = {
    "Review score": ["1", "2", "3", "4", "5"],
    "Delivery status": ["On-time", "Late"],
}

if explore_result.empty:
    st.info("No data available for this combination with the current filters.")
elif dimension_label == "Month":
    fig_explore = px.line(
        explore_result.sort_values(dimension_col),
        x=dimension_col,
        y="value",
        markers=True,
        color_discrete_sequence=[COLOR_BLUE],
        labels={dimension_col: dimension_label, "value": metric_label},
    )
    fig_explore.update_traces(
        line=dict(shape="spline", smoothing=0.6, width=2.5),
        marker=dict(size=7, line=dict(width=1, color="#1a1a19")),
    )
    fig_explore.update_layout(xaxis_tickangle=-45)
    style_fig(fig_explore, f"{metric_label} by {dimension_label.lower()}")
    st.plotly_chart(fig_explore, use_container_width=True, theme=None)
elif dimension_label == "State":
    ordered = explore_result.sort_values("value")
    fig_explore = px.bar(
        ordered,
        x="value",
        y=dimension_col,
        orientation="h",
        color_discrete_sequence=[COLOR_BLUE],
        labels={dimension_col: dimension_label, "value": metric_label},
    )
    fig_explore.update_layout(height=max(400, 22 * len(ordered)))
    style_fig(fig_explore, f"{metric_label} by {dimension_label.lower()}", bar_radius=True)
    st.plotly_chart(fig_explore, use_container_width=True, theme=None)
else:
    category_orders = (
        {dimension_col: ORDERED_CATEGORIES[dimension_label]}
        if dimension_label in ORDERED_CATEGORIES
        else {}
    )
    ordered = (
        explore_result
        if dimension_label in ORDERED_CATEGORIES
        else explore_result.sort_values("value", ascending=False)
    )
    fig_explore = px.bar(
        ordered,
        x=dimension_col,
        y="value",
        color_discrete_sequence=[COLOR_BLUE],
        category_orders=category_orders,
        labels={dimension_col: dimension_label, "value": metric_label},
    )
    style_fig(fig_explore, f"{metric_label} by {dimension_label.lower()}", bar_radius=True)
    st.plotly_chart(fig_explore, use_container_width=True, theme=None)

if not explore_result.empty:
    with st.expander("View underlying table"):
        st.dataframe(
            explore_result.rename(columns={dimension_col: dimension_label, "value": metric_label}),
            use_container_width=True,
        )

st.divider()

with st.expander(f"View filtered raw data ({len(filtered_df):,} orders)"):
    st.dataframe(filtered_df, use_container_width=True)
