from datetime import datetime, timedelta, timezone
import threading
import time
from flask import Flask, jsonify, request
import telebot
from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup

app = Flask(__name__)


@app.route("/")
def home():
  return "Bot is running 24/7!"


def run_flask():
  app.run(host="0.0.0.0", port=10000)


# Ձեր Telegram Token-ը (Chat ID-ն այլևս պարտադիր չէ նախապես գրել)
TELEGRAM_TOKEN = "8763355556:AAH8Yy4X0Fc57M9CDF-UWT8BWh6_pk2hYI0"

bot = telebot.TeleBot(TELEGRAM_TOKEN)

# Բոլոր այն օգտատերերի ID-ները, ովքեր կմտնեն բոտ (պահպանվում են ավտոմատ)
active_chat_ids = set()

# Տեղական ժամային գոտի (UTC+4 Հայաստանի ժամանակով)
YEREVAN_TZ = timezone(timedelta(hours=4))

latest_data = {
    "temp": 0.0,
    "ph": 0.0,
    "do": 0.0,
    "ec": 0.0,
    "tds": 0.0,
    "nitrogen": 0.0,
    "phosphorus": 0.0,
    "potassium": 0.0,
}

history_data = []
is_streaming = False
is_paused_for_input = False
user_states = {}


@app.route("/update-data", methods=["POST"])
def update_data():
  global latest_data, history_data
  try:
    data = request.json
    if data:
      latest_data["temp"] = float(data.get("temp", latest_data["temp"]))
      latest_data["ph"] = float(data.get("ph", latest_data["ph"]))
      latest_data["do"] = float(data.get("do", latest_data["do"]))
      latest_data["ec"] = float(data.get("ec", latest_data["ec"]))
      latest_data["tds"] = float(data.get("tds", latest_data["tds"]))
      latest_data["nitrogen"] = float(
          data.get("nitrogen", latest_data["nitrogen"])
      )
      latest_data["phosphorus"] = float(
          data.get("phosphorus", latest_data["phosphorus"])
      )
      latest_data["potassium"] = float(
          data.get("potassium", latest_data["potassium"])
      )

      now = time.time()
      history_data.append({"time": now, "data": dict(latest_data)})
      history_data = [
          rec for rec in history_data if rec["time"] >= (now - 3600)
      ]

      return jsonify({"status": "success"}), 200
  except Exception as e:
    return jsonify({"status": "error", "message": str(e)}), 400
  return jsonify({"status": "bad request"}), 400


def get_live_markup():
  markup = InlineKeyboardMarkup()
  markup.add(
      InlineKeyboardButton(
          "📊 Ընթացիկ վերլուծություն և խորհուրդ", callback_data="analyze_current"
      )
  )
  markup.add(
      InlineKeyboardButton(
          "📈 1 ժամվա բոլոր տվյալների վերլուծություն",
          callback_data="analyze_history",
      )
  )
  markup.add(
      InlineKeyboardButton("⏹ Կանգնեցնել լայվը", callback_data="stop_live")
  )
  return markup


def get_start_markup():
  markup = InlineKeyboardMarkup()
  markup.add(
      InlineKeyboardButton(
          "▶️ Սկսել լայվ տվյալների ցուցադրումը", callback_data="start_live"
      )
  )
  return markup


# Ցանկացած օգտատեր, երբ գրում է /start կամ բացում է բոտը
@bot.message_handler(commands=["start"])
def send_welcome(message):
  chat_id = message.chat.id
  active_chat_ids.add(chat_id)
  bot.send_message(
      chat_id,
      "👋 Բարև ձեզ։ Սա ջրի որակի մոնիտորինգի համակարգն է։\n🎛 Սեղմեք ստորև նշված"
      " կոճակը՝ լայվ տվյալները տեսնելու համար:",
      reply_markup=get_start_markup(),
  )


@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
  global is_streaming, is_paused_for_input, user_states
  chat_id = call.message.chat.id
  active_chat_ids.add(chat_id)

  if call.data == "start_live":
    is_streaming = True
    is_paused_for_input = False
    bot.answer_callback_query(call.id, "Լայվը միացվեց!")
    bot.send_message(
        chat_id, "▶️ *Մոնիտորինգը սկսվեց...*", parse_mode="Markdown"
    )

  elif call.data == "stop_live":
    is_streaming = False
    bot.answer_callback_query(call.id, "Լայվը կանգնեցվեց:")
    bot.send_message(
        chat_id,
        "⏹ *Կանգնեցված է։*",
        parse_mode="Markdown",
        reply_markup=get_start_markup(),
    )

  elif call.data == "analyze_current":
    is_paused_for_input = True
    bot.answer_callback_query(call.id, "Վերլուծվում են տվյալները...")

    d = latest_data
    ph = float(d.get("ph", 7))
    do = float(d.get("do", 6))
    tds = float(d.get("tds", 100))

    analysis = []
    if 6.5 <= ph <= 7.6:
      analysis.append(f"✅ pH-ը նորմալ է ({ph}):")
    else:
      analysis.append(f"❌ pH-ը խախտված է ({ph}):")

    if do >= 5.0:
      analysis.append(f"✅ Թթվածինը լավ է ({do} mg/L):")
    else:
      analysis.append(f"❌ Թթվածինը ցածր է ({do} mg/L):")

    if tds <= 400:
      analysis.append(f"✅ TDS-ը նորմալ է ({tds} ppm):")
    else:
      analysis.append(f"❌ TDS-ը բարձր է ({tds} ppm):")

    report = "\n".join(analysis)
    user_states[chat_id] = {"action": "pool_size_current", "data": d}

    msg = (
        f"📊 *Ընթացիկ Տվյալների Վերլուծություն*\n\n{report}\n\n"
        f"⏸ *Լայվը կանգնեցված է սպասման ռեժիմում։*\n"
        f"💧 *Խնդրում եմ գրեք ձեր լողավազանի մակերեսը (քառակուսի մետրով, օրինակ՝"
        f" 20):*"
    )
    bot.send_message(chat_id, msg, parse_mode="Markdown")

  elif call.data == "analyze_history":
    is_paused_for_input = True
    bot.answer_callback_query(call.id, "Հաշվարկվում են 1 ժամվա տվյալները...")

    recent_records = [
        rec for rec in history_data if rec["time"] >= (time.time() - 3600)
    ]
    if not recent_records:
      recent_records = [{"time": time.time(), "data": latest_data}]

    avg_temp = sum(r["data"]["temp"] for r in recent_records) / len(
        recent_records
    )
    avg_ph = sum(r["data"]["ph"] for r in recent_records) / len(recent_records)
    avg_do = sum(r["data"]["do"] for r in recent_records) / len(recent_records)
    avg_ec = sum(r["data"]["ec"] for r in recent_records) / len(recent_records)
    avg_tds = sum(r["data"]["tds"] for r in recent_records) / len(
        recent_records
    )
    avg_n = sum(r["data"]["nitrogen"] for r in recent_records) / len(
        recent_records
    )
    avg_p = sum(r["data"]["phosphorus"] for r in recent_records) / len(
        recent_records
    )
    avg_k = sum(r["data"]["potassium"] for r in recent_records) / len(
        recent_records
    )

    now_str = datetime.now(YEREVAN_TZ).strftime("%d.%m.%Y - %H:%M:%S")

    msg = (
        f"📈 *1 Ժամվա Բոլոր Տվյալների Վերլուծություն*\n"
        f"🕒 Ժամ՝ `{now_str}`\n"
        f"📊 Չափումների քանակը՝ `{len(recent_records)}` հատ\n\n"
        f"🌡 Միջին ջերմաստիճան՝ `{avg_temp:.1f} °C`\n"
        f"🧪 Միջին pH՝ `{avg_ph:.2f}`\n"
        f"💨 Միջին Թթվածին (DO)՝ `{avg_do:.2f} mg/L`\n"
        f"⚡ Միջին EC՝ `{avg_ec:.2f} uS/cm`\n"
        f"🧂 Միջին TDS՝ `{avg_tds:.2f} ppm`\n"
        f"🟢 Միջին Ազոտ (N)՝ `{avg_n:.2f} mg/L`\n"
        f"🟣 Միջին Ֆոսֆոր (P)՝ `{avg_p:.3f} mg/L`\n"
        f"🔴 Միջին Կալիում (K)՝ `{avg_k:.2f} mg/L`\n\n"
        f"▶️ *Լայվ հեռարձակումը շարունակվում է...*"
    )
    bot.send_message(chat_id, msg, parse_mode="Markdown")
    is_paused_for_input = False


@bot.message_handler(func=lambda message: True)
def handle_text_messages(message):
  global is_paused_for_input, user_states
  chat_id = message.chat.id
  active_chat_ids.add(chat_id)

  if chat_id in user_states:
    state = user_states[chat_id]
    try:
      area = float(message.text.strip())
      d = state["data"]
      ph = float(d.get("ph", 7))

      volume_m3 = area * 1.5
      water_liters = volume_m3 * 1000

      recommendations = [
          f"📐 Լողավազանի մակերեսը: `{area} մ²` (~{water_liters:.0f} լիտր"
          f" ջուր):\n"
      ]

      if ph > 7.6:
        diff = ph - 7.2
        grams_needed = volume_m3 * (diff * 10 * 10)
        recommendations.append(
            f"🧪 *Լուծում:* Ավելացրեք **pH Minus** շուրջ"
            f" `{max(10, int(grams_needed))} գրամ`։"
        )
      elif ph < 6.5:
        recommendations.append(f"🧪 *Լուծում:* Ավելացրեք **pH Plus**։")
      else:
        recommendations.append(f"✅ *Լուծում:* Ջրի ցուցանիշները նորմալ են։")

      recommendations.append(
          f"🔄 *Ֆիլտրացիա:* Միացրեք ֆիլտրը օրական"
          f" `{int(volume_m3 / 4) + 2}` ժամ։"
      )

      final_text = "\n".join(recommendations)
      bot.send_message(
          chat_id,
          f"🛠 *Անհատական Խորհրդատվություն*\n\n{final_text}\n\n▶️ *Լայվ"
          f" հեռարձակումը վերսկսվում է...*",
          parse_mode="Markdown",
      )

      del user_states[chat_id]
      is_paused_for_input = False

    except ValueError:
      bot.send_message(
          chat_id, "⚠ Խնդրում եմ գրել միայն թիվ (օրինակ՝ 20):"
      )
  else:
    bot.send_message(
        chat_id,
        "🎛 Սեղմեք ստորև նշված կոճակը՝ լայվը սկսելու համար:",
        reply_markup=get_start_markup(),
    )


def live_stream_loop():
  global is_streaming, is_paused_for_input
  while True:
    if is_streaming and not is_paused_for_input and active_chat_ids:
      d = latest_data
      time_str = datetime.now(YEREVAN_TZ).strftime("%H:%M:%S")

      text = (
          f"🌊 *Ջրի Որակի Լայվ Մոնիտորինգ*\n"
          f"🕒 Ժամ: `{time_str}`\n\n"
          f"🌡 Ջերմաստիճան: `{d.get('temp')} °C`\n"
          f"🧪 pH արժեք: `{d.get('ph')}`\n"
          f"💨 Թթվածին (DO): `{d.get('do')} mg/L`\n"
          f"⚡ EC արժեք: `{d.get('ec')} uS/cm`\n"
          f"🧂 TDS արժեք: `{d.get('tds')} ppm`\n"
          f"🟢 Ազոտ (N): `{d.get('nitrogen')} mg/L`\n"
          f"🟣 Ֆոսֆոր (P): `{d.get('phosphorus')} mg/L`\n"
          f"🔴 Կալիում (K): `{d.get('potassium')} mg/L`"
      )

      # Ուղարկում ենք տվյալները բոլոր այն օգտատերերին, ովքեր բացել են բոտը
      for cid in list(active_chat_ids):
        try:
          bot.send_message(
              cid, text, parse_mode="Markdown", reply_markup=get_live_markup()
          )
        except Exception:
          pass  # Եթե ինչ-որ օգտատեր արգելափակել է բոտը, բաց ենք թողնում

    time.sleep(5)


if __name__ == "__main__":
  threading.Thread(target=run_flask, daemon=True).start()
  threading.Thread(target=live_stream_loop, daemon=True).start()

  print("Telegram բոտը և սերվերը աշխատում են բոլոր օգտատերերի համար...")
  bot.infinity_polling(skip_pending=True)
