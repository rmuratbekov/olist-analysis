# Olist e-commerce analysis

Analysis of the [Olist Brazilian e-commerce dataset](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce) (about 99k orders, 2016–2018) with SQL in DuckDB, plus two small tools on top of the same queries:

- a Telegram bot that answers questions like "how did July go?" or "which categories sell best?"
- a Streamlit dashboard with sales, categories, states and delivery times

## What I found

- About 6.8% of delivered orders arrive late, but those orders get much worse reviews: 2.27 stars on average vs 4.29 for on-time orders, and 54% of their reviews are 1 star.
- Late delivery depends a lot on the state. In SP about 4.5% of orders are late, in RJ about 12%.
- November 2017 is the biggest month (7,544 orders), which is Black Friday.

## Files

| File | What it does |
| --- | --- |
| `db.py` | creates DuckDB views over the raw CSV files (nothing is copied) |
| `queries.py` | all SQL, one function per question |
| `bot.py` | Telegram bot |
| `dashboard.py` | Streamlit dashboard |
| `test_queries.py` | checks every query against numbers calculated separately in pandas |
| `notebooks/` | exploration notebooks |

## How to run

1. Download the dataset from Kaggle and put the CSV files in `data/raw/`.
2. Install the libraries: `pip install -r requirements.txt`
3. Check the queries: `python test_queries.py` (should end with `ALL CHECKS PASSED`)
4. Dashboard: `streamlit run dashboard.py`
5. Bot: create a bot with @BotFather in Telegram, copy `.env.example` to `.env`, paste the token, then `python bot.py`

## Notes on the numbers

- Revenue is the sum of item prices for orders that weren't canceled or unavailable. Freight is not included.
- An order is late if it was delivered after the estimated delivery date (compared by day).
- The dashboard uses Jan 2017 – Aug 2018. 2016 has very few orders, and after August 2018 almost all orders are cancellations.
