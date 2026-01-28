import serial
import sqlite3
import time
import sys
import re

# ==========================================
# ⚙️ إعدادات الاتصال
# ==========================================
SERIAL_PORT = '/dev/ttyUSB0'   
BAUD_RATE = 115200              
# ⚠️ تأكد من المسار الكامل لقاعدة البيانات
DB_PATH = '/home/team/Desktop/Smart_Gate_Project/backend_server/db.sqlite3'

def update_db(msg, msg_type):
    """تحديث قاعدة البيانات"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # التحديث مع التوقيت لحل مشكلة الـ Constraints
        c.execute("""
            UPDATE core_systemstate 
            SET current_message=?, message_type=?, last_update=datetime('now') 
            WHERE id=1
        """, (msg, msg_type))
        
        if c.rowcount == 0:
            c.execute("""
                INSERT INTO core_systemstate (id, current_message, message_type, last_update) 
                VALUES (1, ?, ?, datetime('now'))
            """, (msg, msg_type))
        
        conn.commit()
        conn.close()
        print(f"✅ DB UPDATED: {msg} [{msg_type}]")
        
    except Exception as e:
        print(f"❌ DB Write Error: {e}")

# ==========================================
# 🚀 تشغيل الجسر
# ==========================================
print(f"🔌 Connecting to {SERIAL_PORT} @ {BAUD_RATE}...")

try:
    ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
    print("✅ Connected! Listening...")
    ser.reset_input_buffer()

    while True:
        if ser.in_waiting > 0:
            try:
                line = ser.readline().decode('utf-8', errors='ignore').strip()
                if not line or len(line) < 2: continue

                print(f"📥 Received from ESP: {line}")

                lower_line = line.lower()

                # --- 1. ترجمة رسائل الـ RFID (الجديد) 🔥 ---
                
                # لو الرسالة فيها ACCESS GRANTED (سواء بصمة أو كارت)
                if "access granted" in lower_line or "open" in lower_line:
                    # نبعت success عشان الـ GUI يفتح الريلاي
                    update_db("Access Granted", "success")

                # لو الرسالة فيها رقم الكارت SCANNED RFID
                elif "scanned rfid" in lower_line:
                    # نحاول نطلع رقم الكارت ونعرضه
                    parts = line.split(":")
                    card_id = parts[1].strip() if len(parts) > 1 else ""
                    msg = f"Card Scanned: {card_id}"
                    update_db(msg, "info")

                # --- 2. باقي الرسائل القديمة (Fingerprint) ---
                elif "denied" in lower_line or "unknown" in lower_line:
                    update_db("Access Denied", "error")

                elif "found id" in lower_line or "matched" in lower_line:
                    match = re.search(r'\d+', line)
                    user_id = match.group() if match else "?"
                    msg = f"Welcome User {user_id}"
                    update_db(msg, "success")

                # --- 3. تعليمات التسجيل ---
                elif "place" in lower_line:
                    update_db("Place Finger on Sensor", "info")
                elif "remove" in lower_line:
                    update_db("Remove Finger Now", "info")
                elif "enroll" in lower_line:
                    update_db("Enroll Mode Active", "info")
                elif "waiting" in lower_line:
                    update_db("Waiting...", "info")
                elif "stored" in lower_line:
                    update_db("Saved Successfully!", "success")

            except Exception as e:
                print(f"⚠️ Error: {e}")
                
        time.sleep(0.01)

except KeyboardInterrupt:
    print("\n🛑 Stopped.")
except Exception as e:
    print(f"❌ Connection Error: {e}")
