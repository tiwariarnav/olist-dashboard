# Olist E-Commerce Analytics Dashboard

An interactive Streamlit dashboard analyzing ~99K orders from the [Olist Brazilian E-Commerce dataset](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce) (Kaggle) to answer:

**How does delivery delay affect review scores and the likelihood of repeat purchases?**

Supporting angles covered in the dashboard: payment behavior (method + installments), order density and revenue by state, and the on-time vs. late delivery trend over time.

**Live demo →** *(add your Streamlit Community Cloud URL here after deploying — see [Deployment](#deployment))*

<!-- ![Dashboard screenshot](docs/screenshot-overview.png) -->
*(screenshots to be added — see the live demo link above in the meantime)*

## Key findings

Based on 96,470 delivered orders placed between September 2016 and October 2018:

- **Late deliveries are strongly associated with worse reviews.** Orders delivered late average a **2.27 / 5** review score, versus **4.29 / 5** for orders delivered on time.
- **The relationship is monotonic across the entire review scale**, not just a late/on-time split — the late-delivery rate falls steadily as review score rises:

  | Review score | 1 | 2 | 3 | 4 | 5 |
  |---|---|---|---|---|---|
  | Late-delivery rate | 36.7% | 18.8% | 8.8% | 3.4% | 1.9% |

- **Late deliveries measurably reduce repeat purchases.** Customers whose *first* order arrived late go on to make a second purchase **2.66%** of the time, versus **3.23%** for customers whose first order arrived on time — a relative drop of about 18%.
- **Most orders arrive early, not late.** The average delivery lands **11.9 days ahead of the estimated date** (median: 12 days early), and only **6.8%** of delivered orders (6,534 of 96,470) are late overall — but the late rate is not stable over time: it climbed from 1.2% in June 2018 to 6.2% in August 2018, the last full month in the dataset.
- **Credit card dominates payment behavior**: 75.4% of orders use a credit card, followed by boleto (19.9%), voucher (3.2%), and debit card (1.5%).
- **Order volume and revenue are heavily concentrated in São Paulo state** (SP: 41,746 orders, R$5.9M revenue) — more than 3x the next-highest state (RJ).

*(All figures are reproducible from `data/processed/olist_analysis_dataset.csv` via the functions in `src/metrics.py`.)*

## Dashboard features

- **KPI row**: average delivery delay, late-delivery rate, average review score, repeat purchase rate — all recalculated live as filters change.
- **Delay vs. reviews & repeat purchases**: box plot of delivery delay by review score, and a repeat-purchase-rate comparison by first-order delivery outcome.
- **Delivery performance over time**: monthly late-delivery rate trend.
- **Order density & revenue by state**: top states by order volume, with revenue and average order value on hover.
- **Payment behavior**: distribution by payment type and installment count.
- **Explore**: pick any dimension (state, payment type, month, review score, delivery status) and any metric to build an ad-hoc chart — for questions the fixed charts above don't specifically answer.
- **Filters**: order date range and customer state, applied across the whole page (repeat-purchase metrics intentionally use each customer's full order history rather than the date-filtered slice, since truncating it would misrepresent repeat behavior).
- **Light/dark aware charts**, with a manual override in case Streamlit's automatic theme detection lags after switching (a known upstream issue).

## Dataset & methodology

Five of the nine source tables are used, joined on `order_id` into a single order-level analysis dataset:

| Table | Role |
|---|---|
| `olist_orders_dataset.csv` | Order status and the four timestamp fields delivery delay is computed from |
| `olist_order_items_dataset.csv` | Item price + freight, aggregated to one row per order |
| `olist_order_payments_dataset.csv` | Payment method(s) and installment count, aggregated to one row per order |
| `olist_customers_dataset.csv` | Customer state and the stable `customer_unique_id` used for repeat-purchase analysis |
| `olist_order_reviews_dataset.csv` | Review score (most recent, if an order has more than one) |

Key derived fields:

- `delivery_delay_days` — actual delivery date minus estimated delivery date (negative = early), defined only for delivered orders.
- `is_late` — `delivery_delay_days > 0`.
- Repeat-purchase rate is measured on `customer_unique_id` (stable across orders), not `customer_id` (unique per order in this dataset).

Full ETL logic lives in `src/etl.py`; all KPI/aggregation logic lives in `src/metrics.py`. Both are plain pandas functions, independent of Streamlit, so they can be tested or reused outside the dashboard.

## Project structure

```
olist-dashboard/
├── src/
│   ├── etl.py        # load, clean, join raw CSVs -> analysis dataset
│   ├── metrics.py     # KPI and aggregation functions
│   └── app.py          # Streamlit dashboard
├── data/
│   ├── olistcsvs/      # raw Kaggle CSVs (not tracked in git — see below)
│   └── processed/       # built analysis dataset (tracked in git, so the app runs out of the box)
├── requirements.txt
└── .streamlit/config.toml   # theme accent color
```

## Running locally

Requires **Python 3.10+**.

1. **Get the data.** The processed analysis dataset (`data/processed/olist_analysis_dataset.csv`) is already committed to this repo, so you can skip straight to step 2. If you want to re-run the ETL from scratch instead, download the [Olist Brazilian E-Commerce dataset](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce) from Kaggle, extract the CSVs into `data/olistcsvs/`, and delete `data/processed/olist_analysis_dataset.csv` — the app rebuilds it automatically on next run.

2. **Set up the environment:**

   ```bash
   git clone <this-repo-url>
   cd olist-dashboard
   python3 -m venv .venv
   source .venv/bin/activate   # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Run the dashboard:**

   ```bash
   streamlit run src/app.py
   ```

   The app loads the committed processed dataset directly. If it's ever missing (e.g. you deleted it to re-run the ETL), the app automatically rebuilds it from the raw CSVs in `data/olistcsvs/` on first run via `etl.py`.

## Deployment

Deployed on [Streamlit Community Cloud](https://streamlit.io/cloud) (free for public GitHub repos). To deploy your own copy:

1. **Push this repo to GitHub** (public, since raw data isn't committed — see `.gitignore`):

   ```bash
   git remote add origin https://github.com/<your-username>/olist-dashboard.git
   git push -u origin master
   ```

2. **Sign in to [share.streamlit.io](https://share.streamlit.io)** with your GitHub account.

3. Click **"Create app"** → **"Deploy a public app from GitHub"**, then select:
   - **Repository**: `<your-username>/olist-dashboard`
   - **Branch**: `master`
   - **Main file path**: `src/app.py`

4. Click **Deploy**. Streamlit Cloud installs `requirements.txt` and starts the app automatically. The pre-built `data/processed/olist_analysis_dataset.csv` is committed to this repo (see [Project structure](#project-structure)), so the app loads it directly and skips re-running the ETL step on Cloud.

5. Once deployed, Streamlit Cloud gives you a permanent URL like `https://<your-app-name>.streamlit.app` — add it to the **Live demo** link at the top of this README.

Redeploys happen automatically on every push to the connected branch.

## Tech stack

Python · pandas · Streamlit · Plotly

## Data source

[Olist Brazilian E-Commerce Public Dataset](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce) (Kaggle, CC BY-NC-SA 4.0). The raw CSVs aren't redistributed in this repo (only the joined/aggregated analysis dataset is, for reproducibility and one-click deployment) — see [Running locally](#running-locally) to obtain the original raw data directly from Kaggle.
