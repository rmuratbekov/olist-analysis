# Telegram bot for the Olist data
# Run from the project folder:  python bot.py   (needs TELEGRAM_BOT_TOKEN in .env)

import logging
import os

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

import queries
from db import connect

load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger(__name__)

con = connect(os.getenv("DATA_DIR", "data/raw"))

HELP = """Olist sales bot. Data: Brazilian marketplace, Sep 2016 – Oct 2018, prices in R$.

/summary – totals for the whole dataset
/month 2018-07 – one month: orders, revenue, average order, late deliveries
/trend – orders per month, Jan 2017 – Aug 2018
/top 5 – best categories by revenue (1–20)
/late – late delivery share and worst states
/reviews – how late delivery affects review scores"""


def money(x):
    return f"R$ {x:,.0f}"


def pct(part, whole):
    return f"{part / whole * 100:.1f}%" if whole else "n/a"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP)


async def summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = queries.summary(con)
    await update.message.reply_text(
        f"Orders: {s['total_orders']:,} ({s['first_day']} to {s['last_day']})\n"
        f"Delivered: {s['delivered']:,} ({pct(s['delivered'], s['total_orders'])})\n"
        f"Canceled or unavailable: {s['canceled_or_unavailable']:,}\n"
        f"Revenue (item prices, valid orders): {money(s['revenue'])}"
    )


async def month(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Which month? Example: /month 2018-07")
        return
    try:
        m = queries.month(con, context.args[0])
    except ValueError as e:
        await update.message.reply_text(f"{e}. Example: /month 2018-07")
        return
    if m is None:
        await update.message.reply_text(f"No orders in {context.args[0]}. Data runs Sep 2016 – Oct 2018.")
        return
    await update.message.reply_text(
        f"{m['month']}\n"
        f"Orders placed: {m['all_orders']:,}\n"
        f"Revenue: {money(m['revenue'])}\n"
        f"Average order: R$ {m['avg_order_value']:,.2f}\n"
        f"Late deliveries: {m['late']:,} of {m['delivered']:,} delivered ({pct(m['late'], m['delivered'])})"
    )


async def trend(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = queries.trend(con)
    peak = max(n for _, n in rows)
    lines = [f"{ym}  {'█' * round(n / peak * 15):<15} {n:,}" for ym, n in rows]
    text = "Orders per month\n\n" + "\n".join(lines)
    await update.message.reply_text(f"<pre>{text}</pre>", parse_mode="HTML")


async def top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        n = int(context.args[0]) if context.args else 5
        rows = queries.top_categories(con, n)
    except ValueError:
        await update.message.reply_text("Pick a number from 1 to 20. Example: /top 5")
        return
    lines = [f"{i}. {cat.replace('_', ' ')} – {money(rev)}" for i, (cat, rev) in enumerate(rows, 1)]
    await update.message.reply_text(f"Top {n} categories by revenue\n\n" + "\n".join(lines))


async def late(update: Update, context: ContextTypes.DEFAULT_TYPE):
    d = queries.late_deliveries(con)
    states = "\n".join(f"{st}: {p:.1f}% late ({n:,} delivered)" for st, n, p in d["worst_states"])
    await update.message.reply_text(
        f"Late deliveries: {d['late']:,} of {d['delivered']:,} delivered orders ({pct(d['late'], d['delivered'])})\n\n"
        f"Worst states (500+ delivered orders):\n{states}"
    )


async def reviews(update: Update, context: ContextTypes.DEFAULT_TYPE):
    r = queries.reviews_by_delivery(con)
    on, lt = r["on_time"], r["late"]
    await update.message.reply_text(
        "Review score by delivery\n\n"
        f"On time: {on['avg_score']:.2f} / 5, 1-star {on['one_star_pct']:.1f}% ({on['reviews']:,} reviews)\n"
        f"Late: {lt['avg_score']:.2f} / 5, 1-star {lt['one_star_pct']:.1f}% ({lt['reviews']:,} reviews)\n\n"
        "Late delivery is the clearest driver of bad reviews in this data."
    )


async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("I don't know that one.\n\n" + HELP)


async def on_error(update, context: ContextTypes.DEFAULT_TYPE):
    log.error("Error while handling an update", exc_info=context.error)
    if isinstance(update, Update) and update.message:
        await update.message.reply_text("Something went wrong on my side. Try again or send /help.")


async def on_connected(app):
    log.info("Connected as @%s. Bot is running.", app.bot.username)


def main():
    if not TOKEN:
        raise SystemExit("TELEGRAM_BOT_TOKEN is missing. Copy .env.example to .env and paste your token.")

    # default timeout is 5s, too short on my connection
    app = (
        Application.builder()
        .token(TOKEN)
        .connect_timeout(30)
        .read_timeout(30)
        .write_timeout(30)
        .post_init(on_connected)
        .build()
    )
    app.add_handler(CommandHandler(["start", "help"], start))
    app.add_handler(CommandHandler("summary", summary))
    app.add_handler(CommandHandler("month", month))
    app.add_handler(CommandHandler("trend", trend))
    app.add_handler(CommandHandler("top", top))
    app.add_handler(CommandHandler("late", late))
    app.add_handler(CommandHandler("reviews", reviews))
    app.add_handler(MessageHandler(filters.COMMAND | filters.TEXT, unknown))
    app.add_error_handler(on_error)

    log.info("Connecting to Telegram... Press Ctrl+C to stop.")
    app.run_polling(bootstrap_retries=5)


if __name__ == "__main__":
    main()
