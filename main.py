from datetime import datetime, timedelta, timezone
import io
import threading
import time
from flask import Flask, jsonify, request
import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt
import telebot
from telebot.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
)

app = Flask(__name__)


@app.route("/")
def home():
  return "Bot is running 24/7 with timestamps on charts!"


def run_flask():
  app.run(host="0.0.0.0", port=10000)


TELEGRAM_TOKEN = "8763355556:AAH8Yy4X0Fc57M9CDF-UWT8BWh6_pk2hYI0"

bot = telebot.TeleBot(TELEGRAM_TOKEN)

active_chat_ids = set()
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
is_chart_streaming = False
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
      InlineKeyboardButton(
          "📉 Ուղարկել բոլոր գրաֆիկները (Ալբոմով)", callback_data="send_all_charts"
      )
  )

  if is_chart_streaming:
    markup.add(
        InlineKeyboardButton(
            "⏹ Կանգնեցնել լայվ գրաֆիկները", callback_data="stop_live"
        )
    )
  else:
    markup.add(
        InlineKeyboardButton(
            "🔄 Միացնել գրաֆիկների լայվը", callback_data="start_chart_live"
        )
    )

  if not is_streaming:
    markup.add(
        InlineKeyboardButton(
            "▶️ Միացնել տեքստային լայվը", callback_data="start_live"
        )
    )
  else:
    markup.add(
        InlineKeyboardButton(
            "⏹ Կանգնեցնել տեքստային լայվը", callback_data="stop_live"
        )
    )

  return markup


def get_start_markup():
  markup = InlineKeyboardMarkup()
  markup.add(
      InlineKeyboardButton(
          "▶️ Սկսել տեքստային լայվ մոնիտորինգը", callback_data="start_live"
      )
  )
  markup.add(
      InlineKeyboardButton(
          "🔄 Սկսել գրաֆիկների լայվը", callback_data="start_chart_live"
      )
  )
  markup.add(
      InlineKeyboardButton(
          "📉 Ստանալ բոլոր գրաֆիկները", callback_data="send_all_charts"
      )
  )
  return markup


def get_chart_live_stop_markup():
  markup = InlineKeyboardMarkup()
  markup.add(
      InlineKeyboardButton(
          "⏹ Կանգնեցնել լայվ գրաֆիկները", callback_data="stop_live"
      )
  )
  return markup


def generate_single_chart(param_key, param_title, unit, color):
  if not history_data:
    times = [datetime.now(YEREVAN_TZ)]
    vals = [latest_data.get(param_key, 0.0)]
  else:
    times = [
        datetime.fromtimestamp(r["time"], YEREVAN_TZ) for r in history_data
    ]
    vals = [r["data"].get(param_key, 0.0) for r in history_data]

  current_time_str = datetime.now(YEREVAN_TZ).strftime("%Y-%m-%d %H:%M:%S")

  fig, ax = plt.subplots(figsize=(8, 4.2), dpi=150)
  ax.plot(
      times,
      vals,
      color=color,
      marker="o",
      markersize=4,
      linewidth=2,
      label=f"{param_title} ({unit})",
  )
  ax.set_xlabel("Ժամանակ (հետհաշվարկ)", fontsize=9, fontweight="bold")
  ax.set_ylabel(f"{param_title} ({unit})", fontsize=10, fontweight="bold")
  ax.grid(True, linestyle="--", alpha=0.5)

  plt.title(
      f"{param_title}-ի Փոփոխության Գրաֆիկ\n📅 Թարմացված է՝ {current_time_str}",
      fontsize=11,
      fontweight="bold",
      pad=12,
  )
  fig.tight_layout()

  buf = io.BytesIO()
  plt.savefig(buf, format="png", dpi=150)
  buf.seek(0)
  plt.close(fig)
  return buf


def send_all_sensor_charts_as_album(chat_id):
  charts_config = [
      ("temp", "🌡 Ջերմաստիճան", "°C", "#d9534f"),
      ("ph", "🧪 pH Արժեք", "pH", "#0275d8"),
      ("do", "💨 Թթվածին (DO)", "mg/L", "#5bc0de"),
      ("ec", "⚡ Էլեկտրահաղորդականություն (EC)", "uS/cm", "#6f42c1"),
      ("tds", "🧂 Չալուծված Աղեր (TDS)", "ppm", "#f0ad4e"),
      ("nitrogen", "🟢 Ազոտ (N)", "mg/L", "#5cb85c"),
      ("phosphorus", "🟣 Ֆոսֆոր (P)", "mg/L", "#e83e8c"),
      ("potassium", "🔴 Կալիում (K)", "mg/L", "#8d6e63"),
  ]

  media_group = []
  for idx, (key, title, unit, color) in enumerate(charts_config):
    photo_buf = generate_single_chart(key, title, unit, color)
    caption = (
        f"📈 *Ջրի Որակի Բոլոր Գրաֆիկները և Ժամանակը*" if idx == 0 else ""
    )
    media_group.append(
        InputMediaPhoto(
            photo_buf, caption=caption, parse_mode="Markdown" if caption else None
        )
    )

  try:
    bot.send_media_group(chat_id, media=media_group)
  except Exception as e:
    print(f"Error sending media group: {e}")


@bot.message_handler(commands=["start"])
def send_welcome(message):
  chat_id = message.chat.id
  active_chat_ids.add(chat_id)
  bot.send_message(
      chat_id,
      "👋 Բարև ձեզ։ Սա ջրի որակի մոնիտորինգի համակարգն է։\n🎛 Սեղմեք ստորև նշված"
      " կոճակը՝ լայվ տվյալները կամ գրաֆիկները տեսնելու համար:",
      reply_markup=get_start_markup(),
  )


@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
  global is_streaming, is_chart_streaming, is_paused_for_input, user_states
  chat_id = call.message.chat.id
  active_chat_ids.add(chat_id)

  if call.data == "start_live":
    is_streaming = True
    is_chart_streaming = False
    is_paused_for_input = False
    bot.answer_callback_query(call.id, "Տեքստային լայվը միացվեց!")
    bot.send_message(
        chat_id, "▶️ *Տեքստային մոնիտորինգը սկսվեց...*", parse_mode="Markdown"
    )

  elif call.data == "start_chart_live":
    is_chart_streaming = True
    is_streaming = False
    is_paused_for_input = False
    bot.answer_callback_query(call.id, "Գրաֆիկների լայվը միացվեց!")
    bot.send_message(
        chat_id,
        "📈 *Գրաֆիկների լայվ հեռարձակումը սկսվեց... (Տեքստային տվյալները դադարեցված են)*",
        parse_Mode="Markdown",
    )

  elif call.data == "stop_live":
    is_streaming = False
    is_chart_streaming = False
    bot.answer_callback_query(call.id, "Բոլոր լայվերը կանգնեցվեցին:")
    bot.send_message(
        chat_id,
        "⏹ *Բոլոր հեռարձակումները կանգնեցված են։*",
        parse_mode="Markdown",
        reply_markup=get_start_markup(),
    )

  elif call.data == "send_all_charts":
    bot.answer_callback_query(
        call.id, "Գեներացվում են բարձր որակի գրաֆիկները ժամանակագրությամբ..."
    )
    send_all_sensor_charts_as_album(chat_id)
    bot.send_message(
        chat_id,
        "✅ *Բոլոր 8 առանձին գրաֆիկները ուղարկվեցին մեկ ալբոմով։*",
        parse_mode="Markdown",
        reply_markup=get_live_markup(),
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
        f"⏸ *Լայվը դադարեցված է սպասման ռեժիմում։*\n"
        f"💧 *Խնդրում եմ գրեք ձեր լողավազանի մակերեսը (քառակուսի մետրով, օրինակ՝ 20):*"
    )
    bot.send_message(chat_id, msg, parse_mode="Markdown")

  elif call.data == "analyze_history":
    is_paused_for_input = True
    bot.answer_callback_query(call.id, "Հաշվարկվում են բոլոր տվյալները...")

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

    now_str = datetime.now(YEREVAN_TZ).strftime("%Y-%m-%d - %H:%M:%S")

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
        f"▶️ *Հեռարձակումը շարունակվում է...*"
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
          f"🛠 *Անհատական Խորհրդատվություն*\n\n{final_text}\n\n▶️ *Հեռարձակումը"
          f" վերսկսվում է...*",
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
        "🎛 Սեղմեք ստորև նշված կոճակը՝ հեռարձակումը կամ գրաֆիկները բացելու համար:",
        reply_markup=get_start_markup(),
    )


def live_stream_loop():
  global is_streaming, is_chart_streaming, is_paused_for_input
  while True:
    if is_chart_streaming and active_chat_ids:
      for cid in list(active_chat_ids):
        send_all_sensor_charts_as_album(cid)
        try:
          bot.send_message(
              cid,
              "📈 *Լայվ գրաֆիկները թարմացվեցին ըստ ժամանակի:*",
              parse_mode="Markdown",
              reply_markup=get_chart_live_stop_markup(),
          )
        except Exception:
          pass
      time.sleep(15)
      continue

    if is_streaming and not is_paused_for_input and active_chat_ids:
      d = latest_data
      time_str = datetime.now(YEREVAN_TZ).strftime("%Y-%m-%d %H:%M:%S")
      text = (
          f"🌊 *Ջրի Որակի Լայվ Մոնիտորինգ*\n"
          f"🕒 Ժամանակ: `{time_str}`\n\n"
          f"🌡 Ջերմաստիճան: `{d.get('temp')} °C`\n"
          f"🧪 pH արժեք: `{d.get('ph')}`\n"
          f"💨 Թթվածին (DO): `{d.get('do')} mg/L`\n"
          f"⚡ EC արժեք: `{d.get('ec')} uS/cm`\n"
          f"🧂 TDS արժեք: `{d.get('tds')} ppm`\n"
          f"🟢 Ազոտ (N): `{d.get('nitrogen')} mg/L`\n"
          f"🟣 Ֆոսֆոր (P): `{d.get('phosphorus')} mg/L`\n"
          f"🔴 Կալիում (K): `{d.get('potassium')} mg/L`"
      )
      for cid in list(active_chat_ids):
        try:
          bot.send_message(
              cid, text, parse_mode="Markdown", reply_markup=get_live_markup()
          )
        except Exception:
          pass
      time.sleep(5)
    else:
      time.sleep(2)


if __name__ == "__main__":
  threading.Thread(target=run_flask, daemon=True).start()
  threading.Thread(target=live_stream_loop, daemon=True).start()

  print("Telegram բոտը և սերվերը պատրաստ են...")
  bot.infinity_polling(skip_pending=True)
    
