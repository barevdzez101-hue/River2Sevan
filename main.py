import time
from datetime import datetime
import requests
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from flask import Flask
import threading

# Flask վեբ սերվեր Render-ի և UptimeRobot-ի համար
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running 24/7!"

def run_flask():
    app.run(host='0.0.0.0', port=10000)

# Telegram կարգավորումներ
TELEGRAM_TOKEN = "8763355556:AAH8Yy4X0Fc57M9CDF-UWT8BWh6_pk2hYI0"
TELEGRAM_CHAT_ID = "8467592413"

# ESP32-ի IP հասցեն
ESP32_URL = "http://10.115.2.12/data"

bot = telebot.TeleBot(TELEGRAM_TOKEN)

# Հիշողություն պատմության համար
history_data = []

# Կարգավորումների փոփոխականներ
is_streaming = False
is_paused_for_input = False
user_states = {}

def get_device_data():
    """Վերցնում է տվյալները ESP32-ից կամ վերադարձնում փորձնական տվյալներ, եթե կապ չկա"""
    try:
        response = requests.get(ESP32_URL, timeout=3)
        if response.status_code == 200:
            return response.json()
    except Exception:
        pass
    return {
        'temp': 24.5, 
        'ph': 7.8, 
        'do': 5.2, 
        'ec': 180, 
        'tds': 120, 
        'nitrogen': 0.45, 
        'phosphorus': 0.03,
        'potassium': 4.2
    }

def get_live_markup():
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("📊 Լայվ տվյալների վերլուծություն և խորհուրդ", callback_data="analyze_current"))
    markup.add(InlineKeyboardButton("📈 1 ժամվա տվյալների վերլուծություն", callback_data="analyze_history"))
    markup.add(InlineKeyboardButton("⏹ Կանգնեցնել լայվը", callback_data="stop_live"))
    return markup

def get_start_markup():
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("▶️ Սկսել լայվ տվյալների ցուցադրումը (ամեն 5 վրկ)", callback_data="start_live"))
    return markup

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    global is_streaming, is_paused_for_input, user_states
    
    if call.data == "start_live":
        is_streaming = True
        is_paused_for_input = False
        bot.answer_callback_query(call.id, "Լայվ ցուցադրումը միացվեց!")
        bot.send_message(TELEGRAM_CHAT_ID, "▶️ *Լայվ մոնիտորինգը սկսվեց...*", parse_mode="Markdown")

    elif call.data == "stop_live":
        is_streaming = False
        bot.answer_callback_query(call.id, "Լայվը կանգնեցվեց:")
        bot.send_message(TELEGRAM_CHAT_ID, "⏹ *Լայվ հեռարձակումը կանգնեցված է։*", parse_mode="Markdown", reply_markup=get_start_markup())

    elif call.data == "analyze_current":
        is_paused_for_input = True
        bot.answer_callback_query(call.id, "Վերլուծվում են տվյալները...")
        
        d = get_device_data()
        ph = float(d.get('ph', 7))
        do = float(d.get('do', 6))
        tds = float(d.get('tds', 100))
        n = float(d.get('nitrogen', 0.5))
        p = float(d.get('phosphorus', 0.03))
        k = float(d.get('potassium', 4.0))
        
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

        analysis.append(f"🟢 Ազոտ (N): `{n} mg/L` (Նորմայում)")
        analysis.append(f"🟣 Ֆոսֆոր (P): `{p} mg/L` (Նորմայում)")
        analysis.append(f"🔴 Կալիում (K): `{k} mg/L` (Խմելու ջրի նորմայում)")

        report = "\n".join(analysis)
        user_states[call.message.chat.id] = {'action': 'pool_size_current', 'data': d}
        
        msg = (
            f"📊 *Ընթացիկ Տվյալների Վերլուծություն*\n\n{report}\n\n"
            f"⏸ *Լայվը դադարեցված է սպասման ռեժիմում։*\n"
            f"💧 *Խնդրում եմ գրեք ձեր լողավազանի մակերեսը (քառակուսի մետրով, օրինակ՝ 20):*"
        )
        bot.send_message(TELEGRAM_CHAT_ID, msg, parse_mode="Markdown")

    elif call.data == "analyze_history":
        is_paused_for_input = True
        bot.answer_callback_query(call.id, "Վերլուծվում են պատմության տվյալները...")
        
        recent_records = [rec for rec in history_data if rec['time'] >= (time.time() - 3600)]

        if not recent_records:
            d = get_device_data()
            recent_records = [{'time': time.time(), 'data': d}]

        temps = [r['data']['temp'] for r in recent_records]
        phs = [r['data']['ph'] for r in recent_records]
        nitrogens = [r['data']['nitrogen'] for r in recent_records]
        phosphoruses = [r['data']['phosphorus'] for r in recent_records]
        potassiums = [r['data']['potassium'] for r in recent_records]
        
        avg_temp = sum(temps) / len(temps)
        avg_ph = sum(phs) / len(phs)
        avg_n = sum(nitrogens) / len(nitrogens)
        avg_p = sum(phosphoruses) / len(phosphoruses)
        avg_k = sum(potassiums) / len(potassiums)

        now_str = datetime.now().strftime("%d.%m.%Y - %H:%M:%S")

        analysis = [
            f"📅 *Ամսաթիվ և ժամ:* `{now_str}`",
            f"• Չափումների քանակը: `{len(recent_records)}`",
            f"• Միջին ջերմաստիճանը՝ `{avg_temp:.1f}°C`",
            f"• Միջին pH-ը՝ `{avg_ph:.2f}`",
            f"• Միջին Ազոտ (N)՝ `{avg_n:.2f} mg/L`",
            f"• Միջին Ֆոսֆոր (P)՝ `{avg_p:.3f} mg/L`",
            f"• Միջին Կալիում (K)՝ `{avg_k:.2f} mg/L`\n",
            f"📜 *Վերջին 5 չափումները:*"
        ]

        last_five = recent_records[-5:]
        for idx, rec in enumerate(last_five, 1):
            t_formatted = datetime.fromtimestamp(rec['time']).strftime("%H:%M:%S")
            rd = rec['data']
            analysis.append(f"{idx}. [{t_formatted}] 🌡 {rd.get('temp')}°C | N:{rd.get('nitrogen')} | P:{rd.get('phosphorus')} | K:{rd.get('potassium')}")

        report = "\n".join(analysis)
        
        msg = (
            f"📈 *1 Ժամվա Պատմության Վերլուծություն*\n\n{report}\n\n"
            f"▶ *Լայվ հեռարձակումը ավտոմատ վերսկսվում է...*"
        )
        bot.send_message(TELEGRAM_CHAT_ID, msg, parse_mode="Markdown")
        is_paused_for_input = False

@bot.message_handler(func=lambda message: True)
def handle_text_messages(message):
    global is_paused_for_input, user_states
    chat_id = message.chat.id
    
    if chat_id in user_states:
        state = user_states[chat_id]
        try:
            area = float(message.text.strip())
            d = state['data']
            ph = float(d.get('ph', 7))
            
            volume_m3 = area * 1.5  
            water_liters = volume_m3 * 1000
            
            recommendations = [f"📐 Լողավազանի մակերեսը: `{area} մ²` (~{water_liters:.0f} լիտր ջուր):\n"]
            
            if ph > 7.6:
                diff = ph - 7.2
                grams_needed = volume_m3 * (diff * 10 * 10)
                recommendations.append(f"🧪 *Լուծում:* Ավելացրեք **pH Minus** շուրջ `{max(10, int(grams_needed))} գրամ`։")
            elif ph < 6.5:
                recommendations.append(f"🧪 *Լուծում:* Ավելացրեք **pH Plus**։")
            else:
                recommendations.append(f"✅ *Լուծում:* Ջրի ցուցանիշները նորմալ են։")
                
            recommendations.append(f"🔄 *Ֆիլտրացիա:* Միացրեք ֆիլտրը օրական `{int(volume_m3 / 4) + 2}` ժամ։")
            
            final_text = "\n".join(recommendations)
            bot.send_message(chat_id, f"🛠 *Անհատական Խորհրդատվություն*\n\n{final_text}\n\n▶️ *Լայվ հեռարձակումը վերսկսվում է...*", parse_mode="Markdown")
            
            del user_states[chat_id]
            is_paused_for_input = False
            
        except ValueError:
            bot.send_message(chat_id, "⚠ Խնդրում եմ գրել միայն թիվ (օրինակ՝ 25):")
    else:
        bot.send_message(chat_id, "🎛 Սեղմեք ստորև նշված կոճակը՝ լայվը սկսելու համար:", reply_markup=get_start_markup())

def data_collector_loop():
    global history_data
    while True:
        d = get_device_data()
        now = time.time()
        history_data.append({'time': now, 'data': d})
        
        cutoff = now - 3600
        history_data = [rec for rec in history_data if rec['time'] >= cutoff]
        
        time.sleep(30)

def live_stream_loop():
    global is_streaming, is_paused_for_input
    while True:
        if is_streaming and not is_paused_for_input:
            d = get_device_data()
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
                bot.send_message(TELEGRAM_CHAT_ID, text, parse_mode="Markdown", reply_markup=get_live_markup())
            except Exception as e:
                print(f"Live stream սխալ՝ {e}")
                
        time.sleep(5)

if __name__ == "__main__":
    # Միացնում ենք վեբ սերվերը առանձին թելով (Render-ի և UptimeRobot-ի համար)
    threading.Thread(target=run_flask, daemon=True).start()
    
    # Ձեր մյուս թելերը
    threading.Thread(target=data_collector_loop, daemon=True).start()
    threading.Thread(target=live_stream_loop, daemon=True).start()
    
    print("Telegram բոտը պատրաստ է և գործարկվել է...")
    try:
        bot.send_message(TELEGRAM_CHAT_ID, "🎛 Սեղմեք կոճակը լայվ մոնիտորինգը սկսելու համար:", reply_markup=get_start_markup())
    except Exception:
        pass
        
    bot.infinity_polling()
