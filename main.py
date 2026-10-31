from datetime import datetime, timedelta, timezone
import io
import threading
import time
from flask import Flask, jsonify, render_template, request
import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt
import telebot
from telebot.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
)

app = Flask(__name__, template_folder='.')

YEREVAN_TZ = timezone(timedelta(hours=4))

latest_data = {
    "temp": 0.0,
    "ph": 7.0,
    "do": 6.0,
    "ec": 150.0,
    "tds": 100.0,
    "nitrogen": 1.2,
    "phosphorus": 0.05,
    "potassium": 2.5,
}

history_data = []
is_streaming = False
is_chart_streaming = False
is_paused_for_input = False
user_states = {}

# Ձեր նոր Telegram Token-ը
TELEGRAM_TOKEN = "8698217070:AAGk0MuujXNEzKtmZq2Qi43eU9-srd3pQW4"
bot = telebot.TeleBot(TELEGRAM_TOKEN)
active_chat_ids = set()


@app.route("/")
def home():
  return render_template("index.html")


@app.route("/api/data", methods=["GET"])
def api_data():
  return jsonify(latest_data)


@app.route("/api/history", methods=["GET"])
def api_history():
  return jsonify(history_data)


@app.route("/api/analyze", methods=["POST"])
def api_analyze():
  req = request.json or {}
  area = float(req.get("area", 20))

  d = latest_data
  ph = float(d.get("ph", 7))
  do = float(d.get("do", 6))
  tds = float(d.get("tds", 100))

  analysis = []
  if 6.5 <= ph <= 7.6:
    analysis.append(f"✅ pH-ը նորմալ սահմաններում է ({ph}):")
  else:
    analysis.append(f"❌ pH-ը խախտված է ({ph}):")

  if do >= 5.0:
    analysis.append(f"✅ Թթվածինը (DO) լավ մակարդակի վրա է ({do} mg/L):")
  else:
    analysis.append(f"❌ Թթվածինը (DO) շատ ցածր է ({do} mg/L):")

  if tds <= 400:
    analysis.append(f"✅ Աղերի պարունակությունը (TDS) նորմալ է ({tds} ppm):")
  else:
    analysis.append(
        f"❌ Աղերի պարունակությունը (TDS) բարձր է ({tds} ppm): Անհրաժեշտ է"
        " ջրի մասնակի փոխարինում:"
    )

  volume_m3 = area * 1.5
  water_liters = volume_m3 * 1000

  recommendations = [
      f"📐 Լողավազանի մակերեսը: <b>{area} մ²</b> (~{water_liters:.0f} լիտր"
      f" ջուր)"
  ]

  if ph > 7.6:
    diff = ph - 7.2
    grams_needed = volume_m3 * (diff * 10 * 10)
    recommendations.append(
        f"🧪 <b>Լուծում:</b> Ավելացրեք <b>pH Minus</b> շուրջ"
        f" <b>{max(10, int(grams_needed))} գրամ</b>։"
    )
  elif ph < 6.5:
    recommendations.append(
        "🧪 <b>Լուծում:</b> Ավելացրեք <b>pH Plus</b> բարձրացնելու համար։"
    )
  else:
    recommendations.append(
        "✨ <b>Լուծում:</b> Հավելյալ քիմիական նյութերի կարիք չկա։"
    )

  recommendations.append(
      f"🔄 <b>Ֆիլտրացիա:</b> Միացրեք ֆիլտրման համակարգը օրական"
      f" <b>{int(volume_m3 / 4) + 2} ժամ</b>։"
  )

  return jsonify({
      "status": "success",
      "analysis": analysis,
      "recommendations": recommendations,
  })


@app.route("/update-data", methods=["POST"])
def update_data():
  global latest_data, history_data
  try:
    data = request.json
    if data:
      for key in latest_data:
        if key in data:
          latest_data[key] = float(data[key])

      now = time.time()
      history_data.append({"time": now, "data": dict(latest_data)})
      history_data = [
          rec for rec in history_data if rec["time"] >= (now - 3600)
      ]

      return jsonify({"status": "success"}), 200
  except Exception as e:
    return jsonify({"status": "error", "message": str(e)}), 400
  return jsonify({"status": "bad request"}), 400


def run_flask():
  app.run(host="0.0.0.0", port=10000)


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
  return markup


@bot.message_handler(commands=["start"])
def send_welcome(message):
  chat_id = message.chat.id
  active_chat_ids.add(chat_id)
  bot.send_message(
      chat_id,
      "👋 Բարև ձեզ։ Սա ջրի որակի մոնիտորինգի համակարգն է:",
      reply_markup=get_live_markup(),
  )


if __name__ == "__main__":
  threading.Thread(target=run_flask, daemon=True).start()
  print("Telegram բոտը և սերվերը պատրաստ են...")
  bot.infinity_polling(skip_pending=True, remove_webhook=True)
    
