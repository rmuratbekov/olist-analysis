# Checks every query against numbers I calculated separately with pandas.
# Run from the project folder:  python test_queries.py

import os

from dotenv import load_dotenv

import queries
from db import connect

load_dotenv()
con = connect(os.getenv("DATA_DIR", "data/raw"))

failures = 0


def check(name, got, expected, tol=0.01):
    global failures
    if isinstance(expected, float):
        ok = abs(got - expected) <= tol
    else:
        ok = got == expected
    print(("OK   " if ok else "FAIL ") + f"{name}: {got!r} (expected {expected!r})")
    if not ok:
        failures += 1


# bot
s = queries.summary(con)
check("total orders", s["total_orders"], 99441)
check("delivered", s["delivered"], 96478)
check("canceled + unavailable", s["canceled_or_unavailable"], 625 + 609)
check("first day", str(s["first_day"]), "2016-09-04")
check("last day", str(s["last_day"]), "2018-10-17")
check("revenue", s["revenue"], 13494400.74)

m = queries.month(con, "2018-07")
check("2018-07 orders", m["all_orders"], 6292)
check("2018-07 orders with items", m["orders_with_items"], 6233)
check("2018-07 revenue", m["revenue"], 878044.27)
check("2018-07 avg order", round(m["avg_order_value"], 2), 140.87)
check("2018-07 late", m["late"], 208)
check("2018-07 delivered", m["delivered"], 6156)
check("2017-11 orders", queries.month(con, "2017-11")["all_orders"], 7544)
check("month with no orders", queries.month(con, "2016-11"), None)

t = dict(queries.trend(con))
check("trend months", len(t), 20)
check("trend 2017-01", t["2017-01"], 800)
check("trend 2018-08", t["2018-08"], 6512)

top = queries.top_categories(con, 5)
check("top categories", [c for c, _ in top],
      ["health_beauty", "watches_gifts", "bed_bath_table", "sports_leisure", "computers_accessories"])
check("top 1 revenue", top[0][1], 1255695.13)

late = queries.late_deliveries(con)
check("late orders", late["late"], 6534)
check("delivered with date", late["delivered"], 96470)
check("worst states", [st for st, _, _ in late["worst_states"]], ["MA", "CE", "BA"])
check("worst state late %", round(late["worst_states"][0][2], 2), 17.43)

r = queries.reviews_by_delivery(con)
check("avg score on time", round(r["on_time"]["avg_score"], 2), 4.29)
check("avg score late", round(r["late"]["avg_score"], 2), 2.27)
check("1-star % late", round(r["late"]["one_star_pct"], 2), 53.74)

# dashboard
p = queries.period_totals(con)
check("period orders", p["orders"], 99092)
check("period revenue", round(p["revenue"], 2), 13449529.68)
check("period late %", round(p["late_pct"], 2), 6.79)
check("period avg delivery days", round(p["avg_delivery_days"], 2), 12.48)

mo = queries.monthly(con).set_index("month")
check("monthly rows", len(mo), 20)
check("monthly orders total", int(mo["orders"].sum()), 99092)
check("monthly revenue total", round(float(mo["revenue"].sum()), 2), 13449529.68)
check("2017-01 revenue", round(float(mo.loc["2017-01", "revenue"]), 2), 120098.27)
check("2017-11 late %", round(float(mo.loc["2017-11", "late_pct"]), 2), 12.40)
check("2018-08 avg delivery days", round(float(mo.loc["2018-08", "avg_delivery_days"]), 2), 7.66)

st = queries.by_state(con).set_index("state")
check("states", len(st), 27)
check("top state", st.index[0], "SP")
check("SP orders", int(st.loc["SP", "orders"]), 41621)
check("RJ late %", round(float(st.loc["RJ", "late_pct"]), 2), 12.14)
check("RJ avg delivery days", round(float(st.loc["RJ", "avg_delivery_days"]), 2), 15.22)

top18 = queries.top_categories(con, 3, "2018-01", "2018-08")
check("top 2018 categories", [c for c, _ in top18], ["health_beauty", "watches_gifts", "bed_bath_table"])
check("top 2018 revenue", top18[0][1], 770002.81)

print()
print("ALL CHECKS PASSED" if failures == 0 else f"{failures} CHECK(S) FAILED")
