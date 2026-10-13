from datetime import datetime
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


# Telegram կարգավորումներ
TELEGRAM_TOKEN = "8763355556:AAH8Yy4X0Fc57M9CDF-UWT8BWh6_pk2hYI0"
TELEGRAM_CHAT_ID = "8467592413"

bot = telebot.TeleBot(TELEGRAM_TOKEN)

# Պահպանում ենք ESP32-ից ստացված վերջին տվյալները
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


# ESP32-ն ուղարկում է տվյալները այս հասցեին POST հարցումով
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
          "📊 Լայվ տվյալների վերլուծություն և խորհուրդ",
          callback_data="analyze_current",
      )
  )
  markup.add(
      InlineKeyboardButton(
          "📈 1 ժամվա պատմության վերլուծություն", callback_data="analyze_history"
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


@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
  global is_streaming, is_paused_for_input, user_states

  if call.data == "start_live":
    is_streaming = True
    is_paused_for_input = False
    bot.answer_callback_query(call.id, "Լայվ ցուցադրումը միացվեց!")
    bot.send_message(
        TELEGRAM_CHAT_ID,
        "▶️ *Լայվ մոնիտորինգը սկսվեց...*",
        parse_mode="Markdown",
    )

  elif call.data == "stop_live":
    is_streaming = False
    bot.answer_callback_query(call.id, "Լայվը կանգնեցվեց:")
    bot.send_message(
        TELEGRAM_CHAT_ID,
        "⏹ *Լայվ հեռարձակումը կանգնեցված է։*",
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
    user_states[call.message.chat.id] = {"action": "pool_size_current", "data": d}

    msg = (
        f"📊 *Ընթացիկ Տվյալների Վերլուծություն*\n\n{report}\n\n"
        f"⏸ *Լայվը դադարեցված է սպասման ռեժիմում։*\n"
        f"💧 *Խնդրում եմ գրեք ձեր լողավազանի մակերեսը (քառակուսի մետրով, օրինակ՝"
        f" 20):*"
    )
    bot.send_message(TELEGRAM_CHAT_ID, msg, parse_mode="Markdown")

  elif call.data == "analyze_history":
    is_paused_for_input = True
    bot.answer_callback_query(call.id, "Վերլուծվում են պատմության տվյալները...")

    recent_records = [
        rec for rec in history_data if rec["time"] >= (time.time() - 3600)
    ]
    if not recent_records:
      recent_records = [{"time": time.time(), "data": latest_data}]

    temps = [r["data"]["temp"] for r in recent_records]
    phs = [r["data"]["ph"] for r in recent_records]
    avg_temp = sum(temps) / len(temps)
    avg_ph = sum(phs) / len(phs)

    now_str = datetime.now().strftime("%d.%m.%Y - %H:%M:%S")
    msg = (
        f"📈 *1 Ժամվա Պատմության Վերլուծություն*\n\n📅 Ժամ՝ `{now_str}`\n• Միջին"
        f" ջերմաստիճան՝ `{avg_temp:.1f}°C`\n• Միջին pH-ը՝ `{avg_ph:.2f}`\n\n▶️"
        f" *Լայվ հեռարձակումը վերսկսվում է...*"
    )
    bot.send_message(TELEGRAM_CHAT_ID, msg, parse_mode="Markdown")
    is_paused_for_input = False


# Հաղորդագրությունների մշակում (լողավազանի մակերեսի ստացման համար)
@bot.message_handler(func=lambda message: True)
def handle_text_messages(message):
  global is_paused_for_input, user_states
  chat_id = message.chat.id

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
    if is_streaming and not is_paused_for_input:
      d = latest_data
      time_str = datetime.now().strftime("%H:%M:%S")

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

      try:
        bot.send_message(
            TELEGRAM_CHAT_ID,
            text,
            parse_mode="Markdown",
            reply_markup=get_live_markup(),
        )
      except Exception as e:
        print(f"Live stream error: {e}")

    time.sleep(5)


if __name__ == "__main__":
  threading.Thread(target=run_flask, daemon=True).start()
  threading.Thread(target=live_stream_loop, daemon=True).start()

  print("Telegram բոտը և սերվերը պատրաստ են...")
  try:
    bot.send_message(
        TELEGRAM_CHAT_ID,
        "🎛 Սեղմեք կոճակը լայվ մոնիտորինգը սկսելու համար:",
        reply_markup=get_start_markup(),
    )
  except Exception:
    pass

  bot.infinity_polling(skip_pending=True)
