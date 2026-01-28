import sys
import os

# --- 1. FIX WAYLAND CRASH (Important for RPi) ---
os.environ["QT_QPA_PLATFORM"] = "xcb"

# --- IMPORTS ---
import cv2
import face_recognition
import numpy as np
import pickle
import sqlite3
import time
import mediapipe as mp
import math
import threading
from datetime import datetime

# --- PyQt6 IMPORTS ---
from PyQt6.QtWidgets import QApplication, QMainWindow, QLabel, QVBoxLayout, QHBoxLayout, QWidget, QFrame, QGraphicsDropShadowEffect, QSizePolicy
from PyQt6.QtGui import QImage, QPixmap, QFont, QColor
from PyQt6.QtCore import QThread, pyqtSignal, Qt

# ==========================================
# ⚙️ HARDWARE CONFIG (GPIO & RELAY)
# ==========================================
RELAY_PIN = 17
try:
    import RPi.GPIO as GPIO
    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(RELAY_PIN, GPIO.OUT)
    GPIO.output(RELAY_PIN, GPIO.LOW)
    HARDWARE_AVAILABLE = True
    print("✅ GPIO Initialized (Relay Ready)")
except ImportError:
    print("⚠️ GPIO not found (Running in Simulation Mode)")
    HARDWARE_AVAILABLE = False

# ==========================================
# ⚙️ SYSTEM CONFIG
# ==========================================
# المسار الكامل للداتا بيز
DB_PATH = '/home/team/Desktop/Smart_Gate_Project/backend_server/db.sqlite3'

PROCESS_SCALE = 0.5         
TOLERANCE = 0.45            
EYE_AR_THRESH = 0.22        
EYE_AR_CONSEC_FRAMES = 2    

# ==========================================
# 🧠 HELPER FUNCTIONS
# ==========================================
def get_ear(lm):
    """حساب نسبة فتح العين (Eye Aspect Ratio)"""
    def dist(p1, p2): return math.sqrt((p1.x-p2.x)**2 + (p1.y-p2.y)**2)
    v1 = dist(lm[160], lm[144]); v2 = dist(lm[158], lm[153])
    h = dist(lm[33], lm[133])
    return (v1+v2)/(2.0*h)

# ==========================================
# 🧵 WORKER THREAD (THE BRAIN)
# ==========================================
class VideoThread(QThread):
    change_pixmap_signal = pyqtSignal(np.ndarray)
    update_status_signal = pyqtSignal(str, str, str)

    def __init__(self):
        super().__init__()
        self.running = True
        
        # متغيرات التحديث التلقائي
        self.cached_user_count = 0
        self.last_db_check = 0
        
        self.load_database()
        
        self.mp_face_mesh = mp.solutions.face_mesh
        self.face_mesh = self.mp_face_mesh.FaceMesh(max_num_faces=1, refine_landmarks=True)
        
        self.state = "SEARCHING"
        self.detected_name = "Unknown"
        self.current_uid = None
        self.blink_counter = 0
        self.total_blinks = 0
        self.timer_start = 0
        self.last_hw_check = 0

    def load_database(self):
        """تحميل المستخدمين وتحديث العداد في الذاكرة"""
        print("🔄 Loading AI Database...")
        self.known_encodings, self.known_names, self.user_ids = [], [], []
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            query = """
            SELECT auth_user.id, auth_user.username, core_userprofile.face_encoding 
            FROM core_userprofile 
            JOIN auth_user ON core_userprofile.user_id = auth_user.id
            WHERE core_userprofile.face_encoding IS NOT NULL
            """
            cursor.execute(query)
            rows = cursor.fetchall()
            
            for row in rows:
                uid, username, binary = row
                if binary:
                    data = pickle.loads(binary)
                    if isinstance(data, list):
                        for enc in data:
                            self.known_encodings.append(enc)
                            self.known_names.append(username)
                            self.user_ids.append(uid)
                    else:
                        self.known_encodings.append(data)
                        self.known_names.append(username)
                        self.user_ids.append(uid)
            
            self.cached_user_count = len(rows)
            conn.close()
            print(f"✅ Loaded {len(self.known_names)} signatures for {self.cached_user_count} users.")
        except Exception as e: print(f"❌ DB Error: {e}")

    def check_for_new_users(self):
        """مراقب قاعدة البيانات"""
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(id) FROM core_userprofile WHERE face_encoding IS NOT NULL")
            res = cursor.fetchone()
            if res:
                current_count = res[0]
                if current_count != self.cached_user_count:
                    print(f"🆕 Users changed. Reloading...")
                    self.load_database()
            conn.close()
        except:
            pass

    def unlock_door(self):
        if HARDWARE_AVAILABLE:
            def trigger():
                print("🔓 Unlocking Door...")
                GPIO.output(RELAY_PIN, GPIO.HIGH)
                time.sleep(5)  # زمن فتح الباب
                GPIO.output(RELAY_PIN, GPIO.LOW)
                print("🔒 Door Locked.")
            threading.Thread(target=trigger).start()

    def log_access(self, method="FACE"):
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("INSERT INTO core_attendancelog (user_id, access_method, status, timestamp) VALUES (?, ?, ?, datetime('now'))", 
                      (self.current_uid, method, "Success"))
            conn.commit(); conn.close()
        except: pass

    def check_hardware_messages(self):
        """قراءة رسائل الهاردوير وتحديد نوع العرض (ألوان وأيقونات)"""
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("SELECT current_message, message_type FROM core_systemstate WHERE id=1")
            row = cursor.fetchone()
            
            if row and row[0]: 
                msg, mtype = row
                msg = msg.strip()
                msg_lower = msg.lower()
                
                # --- 1. حالات التسجيل والتعليمات ---
                if "place" in msg_lower:
                    self.update_status_signal.emit("ACTION REQUIRED", "Place Finger on Sensor", "#3b82f6")
                    self.state = "GRANTED" # نوقف الكاميرا مؤقتاً
                    self.timer_start = time.time()

                elif "remove" in msg_lower:
                    self.update_status_signal.emit("PLEASE WAIT", "Remove Finger Now", "#f97316")
                    self.state = "GRANTED"
                    self.timer_start = time.time()

                elif "enroll" in msg_lower or "ready" in msg_lower:
                    self.update_status_signal.emit("ENROLL MODE", "System Ready for New User", "#8b5cf6")
                    self.state = "GRANTED"
                    self.timer_start = time.time()

                elif "waiting" in msg_lower:
                    self.update_status_signal.emit("PROCESSING", "Waiting for input...", "#64748b")
                    self.state = "GRANTED"
                    self.timer_start = time.time()

                # --- 2. حالات النجاح وفتح الباب (RFID & Fingerprint) ---
                # 🔥 هنا الشرط اللي بيفتح الباب 🔥
                elif mtype == "success" or "matched" in msg_lower or "stored" in msg_lower or "granted" in msg_lower or "welcome" in msg_lower:
                    
                    self.unlock_door() # فتح الريلاي

                    display_msg = "Access Granted"
                    if "stored" in msg_lower: display_msg = "Fingerprint Saved!"
                    if "welcome" in msg_lower: display_msg = msg
                    
                    self.update_status_signal.emit("SUCCESS", display_msg, "#22c55e")
                    self.state = "GRANTED"
                    self.timer_start = time.time()
                
                # --- 3. حالات الخطأ ---
                elif mtype == "error" or "unknown" in msg_lower or "fail" in msg_lower or "denied" in msg_lower:
                    self.update_status_signal.emit("ACCESS DENIED", "Authentication Failed", "#ef4444")
                    self.state = "GRANTED"
                    self.timer_start = time.time()

                # مسح الرسالة
                cursor.execute("UPDATE core_systemstate SET current_message=NULL WHERE id=1")
                conn.commit()
            conn.close()
        except Exception as e: print(f"HW Error: {e}")

    def run(self):
        cap = cv2.VideoCapture(0)
        
        while self.running:
            current_time = time.time()

            # فحص الرسائل بسرعة (كل 0.2 ثانية)
            if current_time - self.last_hw_check > 0.2:
                self.check_hardware_messages()
                self.last_hw_check = current_time
            
            # فحص المستخدمين الجدد (كل 3 ثواني)
            if current_time - self.last_db_check > 3.0:
                self.check_for_new_users()
                self.last_db_check = current_time

            ret, frame = cap.read()
            if not ret: continue
            
            frame = cv2.flip(frame, 1)
            display_frame = frame.copy()
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            if self.state == "SEARCHING":
                small = cv2.resize(frame, (0,0), fx=PROCESS_SCALE, fy=PROCESS_SCALE)
                rgb_small = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
                locs = face_recognition.face_locations(rgb_small, model="hog")
                
                if locs and self.known_encodings:
                    for (t,r,b,l) in locs:
                        scale = int(1/PROCESS_SCALE)
                        cv2.rectangle(display_frame, (l*scale, t*scale), (r*scale, b*scale), (255, 255, 255), 2)

                    encs = face_recognition.face_encodings(rgb_small, locs)
                    dists = face_recognition.face_distance(self.known_encodings, encs[0])
                    idx = np.argmin(dists)
                    
                    if dists[idx] < TOLERANCE:
                        self.detected_name = self.known_names[idx]
                        self.current_uid = self.user_ids[idx]
                        self.total_blinks = 0
                        self.state = "CHALLENGE"
                        self.update_status_signal.emit(f"HI, {self.detected_name.upper()}", "Please BLINK to verify", "#facc15")
                    else:
                         self.update_status_signal.emit("UNKNOWN", "Access Denied", "#ef4444")

            elif self.state == "CHALLENGE":
                cv2.putText(display_frame, "LIVENESS CHECK...", (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)
                res = self.face_mesh.process(rgb_frame)
                if res.multi_face_landmarks:
                    lm = res.multi_face_landmarks[0].landmark
                    ear = get_ear(lm)
                    if ear < EYE_AR_THRESH: 
                        self.blink_counter += 1
                    else:
                        if self.blink_counter >= EYE_AR_CONSEC_FRAMES:
                            self.total_blinks += 1
                        self.blink_counter = 0
                    
                    if self.total_blinks >= 1:
                        self.state = "GRANTED"
                        self.timer_start = time.time()
                        self.unlock_door()
                        self.log_access("FACE")
                        self.update_status_signal.emit("ACCESS GRANTED", f"Welcome {self.detected_name}", "#22c55e")

            elif self.state == "GRANTED":
                cv2.rectangle(display_frame, (0,0), (640,480), (0, 255, 0), 10)
                # زمن عرض الرسالة: 4 ثواني
                if time.time() - self.timer_start > 4: 
                    self.state = "SEARCHING"
                    self.update_status_signal.emit("LOCKED", "Look at Camera", "#ffffff")

            self.change_pixmap_signal.emit(display_frame)
        cap.release()

    def stop(self):
        self.running = False
        self.wait()

# ==========================================
# 🖥️ GUI WINDOW (PyQt6)
# ==========================================
class SmartGateUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Smart Gate Pro")
        self.setStyleSheet("background-color: #0f172a;")
        self.setGeometry(100, 100, 1000, 600)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        self.left_panel = QFrame()
        self.left_panel.setStyleSheet("background-color: #1e293b; border-right: 2px solid #334155;")
        self.left_panel.setFixedWidth(350)
        left_layout = QVBoxLayout(self.left_panel)
        left_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.lbl_icon = QLabel("🔒")
        self.lbl_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_icon.setStyleSheet("font-size: 80px; margin-bottom: 20px; color: #94a3b8;")
        
        self.lbl_title = QLabel("LOCKED")
        self.lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_title.setWordWrap(True)
        self.lbl_title.setStyleSheet("color: white; font-size: 32px; font-weight: bold; font-family: sans-serif;")
        
        self.lbl_msg = QLabel("Look at Camera")
        self.lbl_msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_msg.setWordWrap(True)
        self.lbl_msg.setStyleSheet("color: #94a3b8; font-size: 20px; margin-top: 10px;")
        
        left_layout.addWidget(self.lbl_icon)
        left_layout.addWidget(self.lbl_title)
        left_layout.addWidget(self.lbl_msg)

        self.right_panel = QFrame()
        right_layout = QVBoxLayout(self.right_panel)
        right_layout.setContentsMargins(20, 20, 20, 20)
        
        self.lbl_camera = QLabel()
        self.lbl_camera.setStyleSheet("background-color: black; border-radius: 15px; border: 2px solid #3b82f6;")
        self.lbl_camera.setScaledContents(True)
        self.lbl_camera.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 150))
        self.lbl_camera.setGraphicsEffect(shadow)

        right_layout.addWidget(self.lbl_camera)

        main_layout.addWidget(self.left_panel)
        main_layout.addWidget(self.right_panel)

        self.thread = VideoThread()
        self.thread.change_pixmap_signal.connect(self.update_image)
        self.thread.update_status_signal.connect(self.update_status)
        self.thread.start()

    def update_image(self, cv_img):
        rgb_image = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb_image.shape
        bytes_per_line = ch * w
        qt_img = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
        self.lbl_camera.setPixmap(QPixmap.fromImage(qt_img))

    def update_status(self, title, msg, color_hex):
        self.lbl_title.setText(title)
        self.lbl_msg.setText(msg)
        self.lbl_title.setStyleSheet(f"color: {color_hex}; font-size: 32px; font-weight: bold;")
        self.lbl_camera.setStyleSheet(f"background-color: black; border-radius: 15px; border: 4px solid {color_hex};")
        
        # 🔥 تغيير الأيقونات حسب الحالة 🔥
        if color_hex == "#22c55e":      # أخضر (نجاح)
            self.lbl_icon.setText("🔓")
        elif color_hex == "#facc15":    # أصفر (شك/تحقق)
            self.lbl_icon.setText("👁️")
        elif color_hex == "#ef4444":    # أحمر (خطأ)
            self.lbl_icon.setText("🚫")
        elif color_hex == "#3b82f6":    # أزرق (تعليمات)
            self.lbl_icon.setText("👆")
        elif color_hex == "#f97316":    # برتقالي (تحذير)
            self.lbl_icon.setText("✋")
        elif color_hex == "#8b5cf6":    # بنفسجي (تسجيل)
            self.lbl_icon.setText("📝") 
        else:
            self.lbl_icon.setText("🔒")

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.thread.stop()
            self.close()

    def closeEvent(self, event):
        self.thread.stop()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = SmartGateUI()
    window.showFullScreen()
    sys.exit(app.exec())
