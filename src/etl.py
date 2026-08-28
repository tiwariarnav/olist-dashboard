"""
etl.py — cleaning and joining Olist e-commerce data into a single
analysis-ready DataFrame keyed on order_id.

Source tables used (from data/olistcsvs/):
    olist_orders_dataset.csv
    olist_order_items_dataset.csv
    olist_order_payments_dataset.csv
    olist_customers_dataset.csv
    olist_order_reviews_dataset.csv

order_items and order_payments are one-to-many with order_id (multiple
items / multiple payment methods per order), so both are aggregated to
one row per order_id before joining. order_reviews occasionally has more
than one review per order; we keep the most recent.
"""

from pathlib import Path

import pandas as pd

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "olistcsvs"
PROCESSED_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"

DATE_COLS_ORDERS = [
    "order_purchase_timestamp",
    "order_approved_at",
    "order_delivered_carrier_date",
    "order_delivered_customer_date",
    "order_estimated_delivery_date",
]


def load_raw(raw_dir: Path = RAW_DIR) -> dict[str, pd.DataFrame]:
    """Load the five source CSVs used in this project."""
    return {
        "orders": pd.read_csv(raw_dir / "olist_orders_dataset.csv"),
        "order_items": pd.read_csv(raw_dir / "olist_order_items_dataset.csv"),
        "order_payments": pd.read_csv(raw_dir / "olist_order_payments_dataset.csv"),
        "customers": pd.read_csv(raw_dir / "olist_customers_dataset.csv"),
        "order_reviews": pd.read_csv(raw_dir / "olist_order_reviews_dataset.csv"),
    }


def clean_orders(orders: pd.DataFrame) -> pd.DataFrame:
    """Parse date columns, drop rows missing key IDs, drop exact duplicates."""
    df = orders.copy()
    for col in DATE_COLS_ORDERS:
        df[col] = pd.to_datetime(df[col], errors="coerce")
    df = df.dropna(subset=["order_id", "customer_id"])
    df = df.drop_duplicates(subset="order_id")
    return df


def clean_customers(customers: pd.DataFrame) -> pd.DataFrame:
    """Normalize state codes, drop rows missing key IDs."""
    df = customers.copy()
    df["customer_state"] = df["customer_state"].str.upper().str.strip()
    df = df.dropna(subset=["customer_id", "customer_unique_id"])
    df = df.drop_duplicates(subset="customer_id")
    return df


def aggregate_order_items(order_items: pd.DataFrame) -> pd.DataFrame:
    """Collapse order_items (one row per item) to one row per order_id."""
    df = order_items.copy()
    df["price"] = pd.to_numeric(df["price"], errors="coerce")
    df["freight_value"] = pd.to_numeric(df["freight_value"], errors="coerce")

    agg = (
        df.groupby("order_id")
        .agg(
            n_items=("order_item_id", "count"),
            n_unique_products=("product_id", "nunique"),
            n_unique_sellers=("seller_id", "nunique"),
            item_price_total=("price", "sum"),
            freight_value_total=("freight_value", "sum"),
        )
        .reset_index()
    )
    agg["order_value_total"] = agg["item_price_total"] + agg["freight_value_total"]
    return agg


def aggregate_order_payments(order_payments: pd.DataFrame) -> pd.DataFrame:
    """Collapse order_payments (possibly multiple methods per order) to one row per order_id."""
    df = order_payments.copy()
    df["payment_value"] = pd.to_numeric(df["payment_value"], errors="coerce")

    payment_value_total = df.groupby("order_id")["payment_value"].sum().rename("payment_value_total")
    max_installments = df.groupby("order_id")["payment_installments"].max().rename("max_installments")
    n_payment_methods = df.groupby("order_id")["payment_type"].nunique().rename("n_payment_methods")

    # "primary" payment method = whichever method contributed the most value to the order
    primary = (
        df.sort_values("payment_value", ascending=False)
        .drop_duplicates(subset="order_id")
        .set_index("order_id")["payment_type"]
        .rename("primary_payment_type")
    )

    return pd.concat(
        [payment_value_total, max_installments, n_payment_methods, primary], axis=1
    ).reset_index()


def aggregate_order_reviews(order_reviews: pd.DataFrame) -> pd.DataFrame:
    """Collapse order_reviews to one row per order_id, keeping the most recent review."""
    df = order_reviews.copy()
    df["review_creation_date"] = pd.to_datetime(df["review_creation_date"], errors="coerce")
    df = df.sort_values("review_creation_date").drop_duplicates(subset="order_id", keep="last")
    return df[["order_id", "review_score", "review_creation_date"]]


def build_analysis_dataset(raw: dict[str, pd.DataFrame] | None = None) -> pd.DataFrame:
    """Clean, aggregate, and join all source tables into one order-level DataFrame."""
    if raw is None:
        raw = load_raw()

    orders = clean_orders(raw["orders"])
    customers = clean_customers(raw["customers"])
    items_agg = aggregate_order_items(raw["order_items"])
    payments_agg = aggregate_order_payments(raw["order_payments"])
    reviews_agg = aggregate_order_reviews(raw["order_reviews"])

    df = orders.merge(customers, on="customer_id", how="left")
    df = df.merge(items_agg, on="order_id", how="left")
    df = df.merge(payments_agg, on="order_id", how="left")
    df = df.merge(reviews_agg, on="order_id", how="left")

    # delivery_delay_days: actual delivery date minus estimated delivery date.
    # Positive = delivered later than estimated (late). Only defined for delivered orders.
    df["delivery_delay_days"] = (
        df["order_delivered_customer_date"] - df["order_estimated_delivery_date"]
    ).dt.days

    df["is_delivered"] = df["order_status"].eq("delivered") & df["order_delivered_customer_date"].notna()
    df["is_late"] = (df["delivery_delay_days"] > 0).astype("boolean")  # nullable bool dtype
    df.loc[~df["is_delivered"], "is_late"] = pd.NA  # undefined for non-delivered orders

    df["order_year_month"] = df["order_purchase_timestamp"].dt.to_period("M").astype(str)

    return df


def save_processed(df: pd.DataFrame, out_dir: Path = PROCESSED_DIR) -> Path:
    """Save the cleaned, joined dataset to data/processed/."""
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "olist_analysis_dataset.csv"
    df.to_csv(out_path, index=False)
    return out_path


if __name__ == "__main__":
    analysis_df = build_analysis_dataset()
    out_path = save_processed(analysis_df)
    print(f"Saved {len(analysis_df):,} rows x {len(analysis_df.columns)} cols to {out_path}")
    print("\nColumn dtypes:")
    print(analysis_df.dtypes)
    print("\nNulls per column (top 10):")
    print(analysis_df.isna().sum().sort_values(ascending=False).head(10))
