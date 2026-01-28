import subprocess
import time
import requests
import os
import signal
import sys
from datetime import datetime

# --- CONFIGURATION ---
PROJECT_PATH = "/home/team/Desktop/Smart_Gate_Project"

# السيرفر (Django)
SERVER_CMD = ["python3", f"{PROJECT_PATH}/backend_server/manage.py", "runsslserver", "0.0.0.0:8000"]

# الواجهة (GUI) - تم تصحيح الاسم هنا ليتطابق مع ملفك
GUI_CMD = ["python3", f"{PROJECT_PATH}/backend_server/smart_gate_pro.py"]

SERVER_URL = "https://127.0.0.1:8000/admin/login/"
CHECK_INTERVAL = 10     
TIMEOUT_SECONDS = 3     
MAX_FAILURES = 3        

# --- GLOBAL VARIABLES ---
server_process = None
gui_process = None
failure_count = 0

def set_low_priority():
    """بيخلي السكريبت ده ياخد أقل أولوية عشان الكاميرا تاخد راحتها"""
    try:
        os.nice(15) 
        print("✅ Guardian Priority set to LOW (Camera is King now)")
    except:
        pass

def log(msg):
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] {msg}")
    if "Restarting" in msg:
        with open("system_guardian.log", "a") as f:
            f.write(f"[{timestamp}] {msg}\n")

def kill_process_by_name(name_keyword):
    """قتل العملية بالاسم"""
    try:
        # pkill -f بيبحث عن الاسم في سطر الأوامر كله
        subprocess.run(f"pkill -9 -f {name_keyword}", shell=True, stderr=subprocess.DEVNULL)
    except: pass

def start_server():
    global server_process
    log("🚀 Starting Server...")
    kill_process_by_name("manage.py")
    server_process = subprocess.Popen(SERVER_CMD, cwd=f"{PROJECT_PATH}/backend_server", stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
    time.sleep(3) 

def start_gui():
    global gui_process
    log("🖥️ Starting GUI (High Priority)...")
    # ⚠️ تصحيح الاسم هنا ضروري جداً
    kill_process_by_name("smart_gate_pro.py")
    gui_process = subprocess.Popen(GUI_CMD, cwd=f"{PROJECT_PATH}/backend_server")

def check_server_health():
    try:
        response = requests.get(SERVER_URL, timeout=TIMEOUT_SECONDS, verify=False)
        return response.status_code == 200
    except:
        return False

def restart_system():
    global failure_count
    log("⚠️ HANG DETECTED! Performing Emergency Restart...")
    
    if server_process: server_process.kill()
    if gui_process: gui_process.kill()
    
    kill_process_by_name("manage.py")
    kill_process_by_name("smart_gate_pro.py") # ⚠️ تصحيح الاسم
    
    time.sleep(1)
    start_server()
    start_gui()
    failure_count = 0

# --- MAIN ---
if __name__ == "__main__":
    set_low_priority()
    
    log("🛡️ Guardian Active (Silent Mode)...")
    
    # تنظيف أي عمليات قديمة
    kill_process_by_name("manage.py")
    kill_process_by_name("smart_gate_pro.py") # ⚠️ تصحيح الاسم
    
    start_server()
    start_gui()

    try:
        while True:
            # فحص هل العمليات لسه عايشة؟
            server_dead = server_process.poll() is not None
            gui_dead = gui_process.poll() is not None

            if server_dead:
                log("❌ Server Died. Reviving...")
                start_server()
            
            if gui_dead:
                log("❌ GUI Died. Reviving...")
                start_gui()

            # فحص صحة السيرفر
            if not server_dead:
                if check_server_health():
                    failure_count = 0
                else:
                    failure_count += 1
                    if failure_count >= MAX_FAILURES:
                        restart_system()

            time.sleep(CHECK_INTERVAL)

    except KeyboardInterrupt:
        log("🛑 Guardian Stopped.")
        kill_process_by_name("manage.py")
        kill_process_by_name("smart_gate_pro.py")
