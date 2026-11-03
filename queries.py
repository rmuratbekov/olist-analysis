import re

# Rules used in all queries:
# - valid order = not canceled / unavailable
# - revenue = sum of item prices of valid orders (no freight), R$
# - late = delivered after the estimated date (compared by day)

VALID = "order_status NOT IN ('canceled', 'unavailable')"

DELIVERED_CTE = """
delivered AS (
    SELECT
        order_id,
        customer_id,
        order_purchase_timestamp,
        CAST(order_delivered_customer_date AS DATE)
            > CAST(order_estimated_delivery_date AS DATE) AS late
    FROM orders
    WHERE order_status = 'delivered'
      AND order_delivered_customer_date IS NOT NULL
)
"""

# one row per order with everything the dashboard needs
ORDER_FACTS_CTE = """
order_revenue AS (
    SELECT order_id, SUM(price) AS revenue
    FROM order_items
    GROUP BY order_id
),
order_facts AS (
    SELECT
        o.order_id,
        o.customer_id,
        strftime(o.order_purchase_timestamp, '%Y-%m') AS month,
        o.order_status NOT IN ('canceled', 'unavailable') AS is_valid,
        o.order_status = 'delivered'
            AND o.order_delivered_customer_date IS NOT NULL AS is_delivered,
        CAST(o.order_delivered_customer_date AS DATE)
            > CAST(o.order_estimated_delivery_date AS DATE) AS late,
        date_diff('day', CAST(o.order_purchase_timestamp AS DATE),
                  CAST(o.order_delivered_customer_date AS DATE)) AS delivery_days,
        r.revenue
    FROM orders AS o
    LEFT JOIN order_revenue AS r ON r.order_id = o.order_id
)
"""

MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


# ---------- bot ----------

def summary(con):
    total, delivered, lost, first_day, last_day = con.execute("""
        SELECT
            COUNT(*),
            SUM(CASE WHEN order_status = 'delivered' THEN 1 ELSE 0 END),
            SUM(CASE WHEN order_status IN ('canceled', 'unavailable') THEN 1 ELSE 0 END),
            CAST(MIN(order_purchase_timestamp) AS DATE),
            CAST(MAX(order_purchase_timestamp) AS DATE)
        FROM orders
    """).fetchone()

    revenue = con.execute(f"""
        SELECT SUM(i.price)
        FROM order_items AS i
        JOIN orders AS o ON o.order_id = i.order_id
        WHERE o.{VALID}
    """).fetchone()[0]

    return {
        "total_orders": total,
        "delivered": delivered,
        "canceled_or_unavailable": lost,
        "first_day": first_day,
        "last_day": last_day,
        "revenue": float(revenue),
    }


def month(con, ym):
    if not MONTH_RE.match(ym):
        raise ValueError("Month must look like 2018-07")

    all_orders = con.execute(
        "SELECT COUNT(*) FROM orders WHERE strftime(order_purchase_timestamp, '%Y-%m') = ?",
        [ym],
    ).fetchone()[0]
    if all_orders == 0:
        return None

    orders_with_items, revenue = con.execute(f"""
        SELECT COUNT(DISTINCT o.order_id), SUM(i.price)
        FROM orders AS o
        JOIN order_items AS i ON i.order_id = o.order_id
        WHERE o.{VALID}
          AND strftime(o.order_purchase_timestamp, '%Y-%m') = ?
    """, [ym]).fetchone()

    late, delivered = con.execute(f"""
        WITH {DELIVERED_CTE}
        SELECT SUM(CASE WHEN late THEN 1 ELSE 0 END), COUNT(*)
        FROM delivered
        WHERE strftime(order_purchase_timestamp, '%Y-%m') = ?
    """, [ym]).fetchone()

    revenue = float(revenue or 0)
    return {
        "month": ym,
        "all_orders": all_orders,
        "orders_with_items": orders_with_items,
        "revenue": revenue,
        "avg_order_value": revenue / orders_with_items if orders_with_items else 0.0,
        "late": late or 0,
        "delivered": delivered,
    }


def trend(con):
    # Jan 2017 - Aug 2018 only: 2016 is almost empty and after Aug 2018 it's mostly cancellations
    return con.execute("""
        SELECT strftime(order_purchase_timestamp, '%Y-%m') AS month, COUNT(*) AS orders
        FROM orders
        WHERE order_purchase_timestamp >= TIMESTAMP '2017-01-01'
          AND order_purchase_timestamp <  TIMESTAMP '2018-09-01'
        GROUP BY month
        ORDER BY month
    """).fetchall()


def top_categories(con, n=5, start="2016-01", end="2018-12"):
    n = int(n)
    if not 1 <= n <= 20:
        raise ValueError("Pick a number from 1 to 20")

    # 2 categories have no english name -> use the portuguese one
    rows = con.execute(f"""
        SELECT
            COALESCE(t.product_category_name_english, p.product_category_name, 'unknown') AS category,
            SUM(i.price) AS revenue
        FROM order_items AS i
        JOIN orders AS o ON o.order_id = i.order_id
        LEFT JOIN products AS p ON p.product_id = i.product_id
        LEFT JOIN category_translation AS t ON t.product_category_name = p.product_category_name
        WHERE o.{VALID}
          AND strftime(o.order_purchase_timestamp, '%Y-%m') BETWEEN ? AND ?
        GROUP BY category
        ORDER BY revenue DESC
        LIMIT {n}
    """, [start, end]).fetchall()
    return [(cat, float(rev)) for cat, rev in rows]


def late_deliveries(con, min_orders=500):
    late, delivered = con.execute(f"""
        WITH {DELIVERED_CTE}
        SELECT SUM(CASE WHEN late THEN 1 ELSE 0 END), COUNT(*)
        FROM delivered
    """).fetchone()

    # states with few orders give noisy percentages, so they're skipped
    worst_states = con.execute(f"""
        WITH {DELIVERED_CTE}
        SELECT
            c.customer_state AS state,
            COUNT(*) AS delivered,
            AVG(CASE WHEN d.late THEN 1.0 ELSE 0.0 END) * 100 AS late_pct
        FROM delivered AS d
        JOIN customers AS c ON c.customer_id = d.customer_id
        GROUP BY state
        HAVING COUNT(*) >= ?
        ORDER BY late_pct DESC
        LIMIT 3
    """, [min_orders]).fetchall()

    return {
        "late": late,
        "delivered": delivered,
        "worst_states": [(s, n, float(p)) for s, n, p in worst_states],
    }


def reviews_by_delivery(con):
    # counted per review (some orders have 2-3 reviews)
    rows = con.execute(f"""
        WITH {DELIVERED_CTE}
        SELECT
            d.late,
            COUNT(*) AS reviews,
            AVG(r.review_score) AS avg_score,
            AVG(CASE WHEN r.review_score = 1 THEN 1.0 ELSE 0.0 END) * 100 AS one_star_pct
        FROM delivered AS d
        JOIN reviews AS r ON r.order_id = d.order_id
        GROUP BY d.late
    """).fetchall()

    result = {}
    for late, reviews, avg_score, one_star_pct in rows:
        key = "late" if late else "on_time"
        result[key] = {
            "reviews": reviews,
            "avg_score": float(avg_score),
            "one_star_pct": float(one_star_pct),
        }
    return result


# ---------- dashboard ----------

def period_totals(con, start="2017-01", end="2018-08"):
    # numbers for the top row of the dashboard
    orders, revenue, late_pct, avg_days = con.execute(f"""
        WITH {ORDER_FACTS_CTE}
        SELECT
            COUNT(*),
            SUM(CASE WHEN is_valid THEN revenue END),
            AVG(CASE WHEN is_delivered AND late THEN 100.0
                     WHEN is_delivered THEN 0.0 END),
            AVG(CASE WHEN is_delivered THEN delivery_days END)
        FROM order_facts
        WHERE month BETWEEN ? AND ?
    """, [start, end]).fetchone()
    return {
        "orders": orders,
        "revenue": float(revenue or 0),
        "late_pct": float(late_pct or 0),
        "avg_delivery_days": float(avg_days or 0),
    }


def monthly(con, start="2017-01", end="2018-08"):
    return con.execute(f"""
        WITH {ORDER_FACTS_CTE}
        SELECT
            month,
            COUNT(*) AS orders,
            SUM(CASE WHEN is_valid THEN revenue END) AS revenue,
            AVG(CASE WHEN is_delivered AND late THEN 100.0
                     WHEN is_delivered THEN 0.0 END) AS late_pct,
            AVG(CASE WHEN is_delivered THEN delivery_days END) AS avg_delivery_days
        FROM order_facts
        WHERE month BETWEEN ? AND ?
        GROUP BY month
        ORDER BY month
    """, [start, end]).df()


def by_state(con, start="2017-01", end="2018-08"):
    return con.execute(f"""
        WITH {ORDER_FACTS_CTE}
        SELECT
            c.customer_state AS state,
            COUNT(*) AS orders,
            SUM(CASE WHEN f.is_valid THEN f.revenue END) AS revenue,
            AVG(CASE WHEN f.is_delivered AND f.late THEN 100.0
                     WHEN f.is_delivered THEN 0.0 END) AS late_pct,
            AVG(CASE WHEN f.is_delivered THEN f.delivery_days END) AS avg_delivery_days
        FROM order_facts AS f
        JOIN customers AS c ON c.customer_id = f.customer_id
        WHERE f.month BETWEEN ? AND ?
        GROUP BY state
        ORDER BY orders DESC
    """, [start, end]).df()
