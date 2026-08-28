"""
metrics.py — KPI and summary functions for the Olist analysis dataset.

Every function takes the cleaned, order-level DataFrame produced by
etl.build_analysis_dataset() (or loaded from data/processed/) and returns
either a dict of scalar summary stats or a tidy summary DataFrame. No I/O
happens inside these functions beyond the optional loader / __main__ smoke
test at the bottom, so app.py can call them directly on an in-memory df.
"""

from pathlib import Path

import pandas as pd

PROCESSED_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "processed" / "olist_analysis_dataset.csv"
)

DATE_COLS = [
    "order_purchase_timestamp",
    "order_approved_at",
    "order_delivered_carrier_date",
    "order_delivered_customer_date",
    "order_estimated_delivery_date",
    "review_creation_date",
]


def load_processed(path: Path = PROCESSED_PATH) -> pd.DataFrame:
    """Load the cleaned dataset and recompute the boolean flag columns fresh.

    CSV round-tripping can turn True/False (bool/boolean dtype) into strings
    or mixed types depending on pandas version, so rather than trust the
    serialized is_delivered/is_late columns, we recompute them here from the
    underlying dates/status the same way etl.py does. This keeps every
    downstream function working with clean, unambiguous bool dtypes.
    """
    df = pd.read_csv(path, parse_dates=DATE_COLS)
    df["is_delivered"] = df["order_status"].eq("delivered") & df["order_delivered_customer_date"].notna()
    df["is_late"] = df["delivery_delay_days"] > 0
    df.loc[~df["is_delivered"], "is_late"] = False  # not meaningful; callers filter on is_delivered anyway
    return df


def avg_delivery_delay(df: pd.DataFrame) -> dict:
    """Average and median delivery delay in days, among delivered orders."""
    delivered = df.loc[df["is_delivered"], "delivery_delay_days"].dropna()
    return {
        "mean_delay_days": round(delivered.mean(), 2) if len(delivered) else None,
        "median_delay_days": round(delivered.median(), 2) if len(delivered) else None,
        "n_delivered": int(delivered.shape[0]),
    }


def pct_late_deliveries(df: pd.DataFrame) -> dict:
    """Share of delivered orders that arrived after the estimated delivery date."""
    delivered = df.loc[df["is_delivered"]]
    n_delivered = delivered.shape[0]
    n_late = int(delivered["is_late"].sum())
    return {
        "pct_late": round(100 * n_late / n_delivered, 2) if n_delivered else None,
        "n_late": n_late,
        "n_delivered": int(n_delivered),
    }


def review_score_by_delivery_status(df: pd.DataFrame) -> pd.DataFrame:
    """Average review score for on-time vs. late delivered orders."""
    delivered = df.loc[df["is_delivered"] & df["review_score"].notna()].copy()
    delivered["delivery_status"] = delivered["is_late"].map({True: "Late", False: "On-time"})
    summary = (
        delivered.groupby("delivery_status")
        .agg(avg_review_score=("review_score", "mean"), n_orders=("review_score", "count"))
        .round(3)
        .reset_index()
    )
    return summary


def monthly_delivery_trend(df: pd.DataFrame) -> pd.DataFrame:
    """Monthly on-time vs. late delivery rate, for a trend line over time."""
    delivered = df.loc[df["is_delivered"]]
    summary = (
        delivered.groupby("order_year_month")
        .agg(n_orders=("order_id", "count"), n_late=("is_late", "sum"))
        .reset_index()
    )
    summary["pct_late"] = (100 * summary["n_late"] / summary["n_orders"]).round(2)
    summary["pct_on_time"] = (100 - summary["pct_late"]).round(2)
    return summary.sort_values("order_year_month").reset_index(drop=True)


def repeat_purchase_rate(df: pd.DataFrame) -> dict:
    """Share of customers (by customer_unique_id) with more than one order."""
    orders_per_customer = df.groupby("customer_unique_id")["order_id"].nunique()
    n_total = orders_per_customer.shape[0]
    n_repeat = int((orders_per_customer > 1).sum())
    return {
        "repeat_purchase_rate_pct": round(100 * n_repeat / n_total, 2) if n_total else None,
        "n_repeat_customers": n_repeat,
        "n_total_customers": int(n_total),
    }


def repeat_purchase_rate_by_first_delivery(df: pd.DataFrame) -> pd.DataFrame:
    """
    Repeat purchase rate segmented by whether a customer's first DELIVERED
    order arrived on-time or late. This is the metric that most directly
    answers the project's core business question: does a late first
    delivery reduce the odds a customer orders again?
    """
    delivered = df.loc[df["is_delivered"]].sort_values("order_purchase_timestamp")

    first_orders = (
        delivered.drop_duplicates(subset="customer_unique_id", keep="first")
        .set_index("customer_unique_id")["is_late"]
        .rename("first_order_late")
    )
    orders_per_customer = df.groupby("customer_unique_id")["order_id"].nunique().rename("n_orders")

    merged = pd.concat([first_orders, orders_per_customer], axis=1).dropna(subset=["first_order_late"])
    merged["first_order_status"] = merged["first_order_late"].map({True: "Late", False: "On-time"})
    merged["is_repeat"] = merged["n_orders"] > 1

    summary = (
        merged.groupby("first_order_status")["is_repeat"]
        .agg(["mean", "count"])
        .rename(columns={"mean": "repeat_rate_frac", "count": "n_customers"})
        .reset_index()
    )
    summary["repeat_rate_pct"] = (100 * summary["repeat_rate_frac"]).round(2)
    return summary[["first_order_status", "repeat_rate_pct", "n_customers"]]


def revenue_orders_by_state(df: pd.DataFrame) -> pd.DataFrame:
    """Revenue and order volume by Brazilian customer state."""
    summary = (
        df.groupby("customer_state")
        .agg(
            total_revenue=("order_value_total", "sum"),
            n_orders=("order_id", "nunique"),
            avg_order_value=("order_value_total", "mean"),
        )
        .round(2)
        .reset_index()
        .sort_values("total_revenue", ascending=False)
        .reset_index(drop=True)
    )
    return summary


def payment_type_distribution(df: pd.DataFrame) -> pd.DataFrame:
    """Distribution of orders by primary payment type."""
    counts = df["primary_payment_type"].value_counts(dropna=True)
    summary = counts.reset_index()
    summary.columns = ["payment_type", "n_orders"]
    summary["pct_orders"] = (100 * summary["n_orders"] / summary["n_orders"].sum()).round(2)
    return summary


def installment_distribution(df: pd.DataFrame) -> pd.DataFrame:
    """Distribution of orders by number of payment installments (bucketed)."""
    bins = [0, 1, 2, 3, 6, 12, float("inf")]
    labels = ["1", "2", "3", "4-6", "7-12", "13+"]
    bucketed = pd.cut(df["max_installments"], bins=bins, labels=labels)
    summary = bucketed.value_counts().sort_index().reset_index()
    summary.columns = ["installments", "n_orders"]
    summary["pct_orders"] = (100 * summary["n_orders"] / summary["n_orders"].sum()).round(2)
    return summary


# ---------------------------------------------------------------------------
# Explore tab: generic dimension x metric aggregation, for open-ended
# questions the fixed dashboard charts don't specifically answer.
# ---------------------------------------------------------------------------

EXPLORE_DIMENSIONS = {
    "State": "customer_state",
    "Payment type": "primary_payment_type",
    "Month": "order_year_month",
    "Review score": "_review_score_str",
    "Delivery status": "_delivery_status_str",
}

EXPLORE_METRICS = [
    "Number of orders",
    "Total revenue (R$)",
    "Avg order value (R$)",
    "Avg delivery delay (days)",
    "Avg review score",
    "Late delivery rate (%)",
]


def prepare_explore_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Add the small set of derived string columns the Explore tab groups by."""
    df = df.copy()
    df["_review_score_str"] = df["review_score"].apply(lambda x: str(int(x)) if pd.notna(x) else pd.NA)
    df["_delivery_status_str"] = df["is_late"].map({True: "Late", False: "On-time"})
    df.loc[~df["is_delivered"], "_delivery_status_str"] = pd.NA
    return df


def explore_by(df: pd.DataFrame, dimension_col: str, metric: str) -> pd.DataFrame:
    """
    Generic dimension x metric aggregation for the Explore tab. df must already
    have the derived columns from prepare_explore_columns(). Returns a tidy
    DataFrame with columns [dimension_col, "value", "n_orders"].
    """
    if metric == "Number of orders":
        g = df.groupby(dimension_col)["order_id"].nunique()
    elif metric == "Total revenue (R$)":
        g = df.groupby(dimension_col)["order_value_total"].sum().round(2)
    elif metric == "Avg order value (R$)":
        g = df.groupby(dimension_col)["order_value_total"].mean().round(2)
    elif metric == "Avg delivery delay (days)":
        g = df.loc[df["is_delivered"]].groupby(dimension_col)["delivery_delay_days"].mean().round(2)
    elif metric == "Avg review score":
        g = df.loc[df["review_score"].notna()].groupby(dimension_col)["review_score"].mean().round(3)
    elif metric == "Late delivery rate (%)":
        g = df.loc[df["is_delivered"]].groupby(dimension_col)["is_late"].mean().mul(100).round(2)
    else:
        raise ValueError(f"Unknown metric: {metric}")

    n_orders = df.groupby(dimension_col)["order_id"].nunique()

    result = (
        pd.concat([g.rename("value"), n_orders.rename("n_orders")], axis=1)
        .dropna(subset=["value"])
        .reset_index()
    )
    return result


if __name__ == "__main__":
    df = load_processed()

    print("=== avg_delivery_delay ===")
    print(avg_delivery_delay(df))

    print("\n=== pct_late_deliveries ===")
    print(pct_late_deliveries(df))

    print("\n=== review_score_by_delivery_status ===")
    print(review_score_by_delivery_status(df))

    print("\n=== monthly_delivery_trend (head) ===")
    print(monthly_delivery_trend(df).head())

    print("\n=== repeat_purchase_rate ===")
    print(repeat_purchase_rate(df))

    print("\n=== repeat_purchase_rate_by_first_delivery ===")
    print(repeat_purchase_rate_by_first_delivery(df))

    print("\n=== revenue_orders_by_state (top 5) ===")
    print(revenue_orders_by_state(df).head())

    print("\n=== payment_type_distribution ===")
    print(payment_type_distribution(df))

    print("\n=== installment_distribution ===")
    print(installment_distribution(df))
