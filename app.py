from flask import Flask, jsonify, send_file, request
from flask_cors import CORS
import requests
import json
import os
from datetime import datetime
from collections import defaultdict

app = Flask(__name__)
CORS(app)

# دو توکن API — توکن دومی که گرفتی رو جای PUT_YOUR_SECOND_TOKEN_HERE بگذار
API_KEYS = {
    1: "B5zgBWpp87rDlVHmL6Rx963abdhRaNhT",
    2: "Bujirlnr79wxmwRbPUupj2WH22v6fi9M",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 6.1; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 OPR/106.0.0.0",
    "Accept": "application/json, text/plain, */*"
}

HTML_PATH = r'C:\Users\AMIR\Desktop\Bourse-API_fullStack\index.html'

# فایل ذخیره‌ی تاریخچه‌ی میانگین کل هر گروه (در همان پوشه‌ی این فایل ساخته می‌شود)
HISTORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "group_history.json")
MAX_HISTORY_POINTS = 100  # حداکثر تعداد نقاطی که برای هر گروه نگه‌داری می‌شود

# فایل ذخیره‌ی توکن فعال، تا بعد از ری‌استارت سرور هم انتخابت یادش بماند
ACTIVE_KEY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "active_key.json")


def load_active_key_index():
    """ایندکس توکن فعال (1 یا 2) رو از روی دیسک می‌خواند. پیش‌فرض: توکن 1"""
    if os.path.exists(ACTIVE_KEY_FILE):
        try:
            with open(ACTIVE_KEY_FILE, "r", encoding="utf-8") as f:
                idx = json.load(f).get("active", 1)
                if idx in API_KEYS:
                    return idx
        except (json.JSONDecodeError, OSError):
            pass
    return 1


def save_active_key_index(idx):
    try:
        with open(ACTIVE_KEY_FILE, "w", encoding="utf-8") as f:
            json.dump({"active": idx}, f)
    except OSError:
        pass


active_key_index = load_active_key_index()


def get_api_url():
    """ساخت URL درخواست بر اساس توکن فعال در همین لحظه"""
    key = API_KEYS.get(active_key_index, API_KEYS[1])
    return f"https://Api.BrsApi.ir/Tsetmc/AllSymbols.php?key={key}&type=1"


# گروه‌هایی که اصلاً نمی‌خواهیم نمایش داده شوند
EXCLUDED_GROUPS = {
    "پیمانکاری صنعتی",
    "فعالیت‌های فرهنگی و ورزشی",
    "حمل و نقل آبی",
    "فعالیت‌های هنری، سرگرمی و خلاقانه",
    "محصولات چوبی",
    "فعالیت مهندسی، تجزیه، تحلیل و آزمایش فنی",
    "استخراج نفت گاز و خدمات جنبی جز اکتشاف",
    "استخراج سایر معادن",
    "تولید محصولات کامپیوتری الکترونیکی و نوری",
    "هتل و رستوران",
    "محصولات کاغذی",
    "استخراج زغال سنگ",
    "ساخت دستگاه‌ها و وسایل ارتباطی",
    "دباغی، پرداخت چرم و ساخت انواع پاپوش",
    "خرده‌فروشی، به‌استثنای وسایل نقلیه موتوری",
    "نامشخص",
    "انتشار، چاپ و تکثیر",
    "تجارت عمده‌فروشی به جز وسایل نقلیه موتوری",
}


def load_history():
    """خواندن تاریخچه‌ی ذخیره‌شده از روی دیسک. اگر فایل خراب/ناموجود بود، دیکشنری خالی برمی‌گرداند."""
    if not os.path.exists(HISTORY_FILE):
        return {}
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_history(history):
    """نوشتن تاریخچه روی دیسک. در صورت خطا برنامه نباید کرش کند."""
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False)
    except OSError:
        pass


def update_history(group_averages):
    """
    یک نقطه‌ی جدید (به ازای هر رفرش) به تاریخچه‌ی هر گروه اضافه می‌کند.
    group_averages: دیکشنری {نام_گروه: میانگین_کل_درصد}
    خروجی: کل تاریخچه‌ی به‌روزشده (شامل همه‌ی گروه‌ها)
    """
    history = load_history()
    timestamp = datetime.now().strftime("%H:%M")

    for group, avg_total in group_averages.items():
        points = history.get(group, [])
        points.append({"t": timestamp, "v": avg_total})
        history[group] = points[-MAX_HISTORY_POINTS:]

    save_history(history)
    return history


def fetch_and_process():
    response = requests.get(get_api_url(), headers=HEADERS, timeout=30)
    if response.status_code != 200:
        return None, f"خطا در دریافت داده: {response.status_code}"

    symbols = response.json()

    # بعضی وقت‌ها وقتی سهمیه‌ی توکن تموم بشه، Api به‌جای لیست نمادها یک دیکشنری خطا برمی‌گردونه
    if not isinstance(symbols, list):
        err_text = ""
        if isinstance(symbols, dict):
            err_text = symbols.get("message") or symbols.get("error") or str(symbols)
        return None, f"خطا در دریافت داده (احتمالاً سهمیه‌ی توکن {active_key_index} تمام شده): {err_text}"

    groups = defaultdict(lambda: {"symbols_data": []})
    total = len(symbols)
    skipped = 0

    for s in symbols:
        group = s.get("cs") or "نامشخص"
        name = s.get("l18", "") or ""

        if group in EXCLUDED_GROUPS:
            skipped += 1
            continue

        if "صندوق" in group:
            skipped += 1
            continue

        if name.endswith("3") or name.endswith("2") or name.endswith("ح"):
            skipped += 1
            continue

        try:
            tvol = float(s.get("tvol") or 0)
        except (TypeError, ValueError):
            tvol = 0
        if tvol == 0:
            skipped += 1
            continue

        try:
            plp = float(s.get("plp"))
        except (TypeError, ValueError):
            continue

        # فیلتر بازار پایه: اگه فاصله tmax و tmin کمتر از 5 درصد بود حذف کن
        try:
            tmin = float(s.get("tmin") or 0)
            tmax = float(s.get("tmax") or 0)
            py   = float(s.get("py")   or 0)
            if py > 0:
                price_range_pct = (tmax - tmin) / py * 100
                if price_range_pct < 5:
                    skipped += 1
                    continue
        except (TypeError, ValueError):
            pass

        # ارزش صف خرید ردیف اول: qd1 * pd1
        try:
            qd1 = float(s.get("qd1") or 0)
            pd1 = float(s.get("pd1") or 0)
            buy_queue_value = qd1 * pd1
        except (TypeError, ValueError):
            buy_queue_value = 0

        isin = s.get("isin", "") or ""

        groups[group]["symbols_data"].append({
            "name": name,
            "plp": plp,
            "buy_queue_value": buy_queue_value,
            "isin": isin,
        })

    results = []
    for group, data in groups.items():
        syms = data["symbols_data"]
        count = len(syms)

        positives = [s for s in syms if s["plp"] > 0]
        negatives = [s for s in syms if s["plp"] < 0]

        # برای محاسبه‌ی میانگین، سهامی که بیش از حد جهیده‌اند (پرش غیرعادی) رو کنار می‌گذاریم
        # سهم بالای +3٪ وارد محاسبه‌ی میانگین مثبت نمی‌شه
        # سهم پایین‌تر از -3٪ (مثلاً -4٪) وارد محاسبه‌ی میانگین منفی نمی‌شه
        pos_for_avg = [s for s in positives if s["plp"] <= 3]
        neg_for_avg = [s for s in negatives if s["plp"] >= -3]

        avg_pos = round(sum(s["plp"] for s in pos_for_avg) / len(pos_for_avg), 2) if pos_for_avg else 0.0
        avg_neg = round(sum(s["plp"] for s in neg_for_avg) / len(neg_for_avg), 2) if neg_for_avg else 0.0

        # نمادهای بالای میانگین مثبت — سورت نزولی بر اساس درصد تغییر (تا رنگ‌های هم‌خانواده کنار هم بیفتن)
        above_avg_pos_all = sorted(
            [s for s in positives if s["plp"] >= avg_pos],
            key=lambda x: x["plp"], reverse=True
        )

        if avg_pos > 2.9:
            above_avg_pos = sorted(
                [s for s in positives if s["plp"] > 2.9],
                key=lambda x: x["plp"], reverse=True
            )
        else:
            above_avg_pos = above_avg_pos_all

        # نمادهای بین میانگین منفی و صفر — سورت صعودی بر اساس درصد (منفی‌ترین اول، نزدیک‌به‌صفر آخر)
        between = sorted(
            [s for s in syms if avg_neg <= s["plp"] <= 0],
            key=lambda x: x["plp"]
        )

        # میانگین کل درصد تغییر همه‌ی نمادهای گروه (صرف‌نظر از مثبت/منفی بودن)
        avg_total = round(sum(s["plp"] for s in syms) / count, 2) if count else 0.0

        results.append({
            "group": group,
            "count": count,
            "avg_pos": avg_pos,
            "avg_neg": avg_neg,
            "avg_total": avg_total,
            "above_avg_pos": above_avg_pos,
            "between": between,
        })

    # ذخیره‌ی نقطه‌ی جدید میانگین کل هر گروه در فایل تاریخچه (برای رسم نمودار)
    group_averages = {r["group"]: r["avg_total"] for r in results}
    history = update_history(group_averages)
    for r in results:
        r["history"] = history.get(r["group"], [])

    results.sort(key=lambda x: x["count"], reverse=True)
    return {"groups": results, "total": total, "skipped": skipped}, None


@app.route("/")
def index():
    return send_file(HTML_PATH)


@app.route("/api/data")
def api_data():
    data, err = fetch_and_process()
    if err:
        return jsonify({"error": err}), 500
    return jsonify(data)


@app.route("/api/key-status")
def key_status():
    """وضعیت فعلی توکن‌ها رو برمی‌گرداند تا فرانت‌اند بدونه کدوم فعاله"""
    return jsonify({
        "active": active_key_index,
        "available": sorted(API_KEYS.keys()),
    })


@app.route("/api/switch-key", methods=["POST"])
def switch_key():
    """سوییچ بین توکن‌ها (index باید 1 یا 2 باشه)"""
    global active_key_index

    payload = request.get_json(silent=True) or {}
    try:
        idx = int(payload.get("index"))
    except (TypeError, ValueError):
        return jsonify({"error": "ایندکس توکن نامعتبر است"}), 400

    if idx not in API_KEYS:
        return jsonify({"error": "این توکن تعریف نشده است"}), 400

    if not API_KEYS[idx] or API_KEYS[idx].startswith("PUT_YOUR_"):
        return jsonify({"error": f"توکن {idx} هنوز در app.py تنظیم نشده است"}), 400

    active_key_index = idx
    save_active_key_index(idx)
    return jsonify({"active": active_key_index})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
