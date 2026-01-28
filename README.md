# 🛡️ Smart Gate Pro: AI-Powered Access Control System

![Python](https://img.shields.io/badge/Python-3.9%2B-blue?style=for-the-badge&logo=python)
![Django](https://img.shields.io/badge/Django-Backend-092E20?style=for-the-badge&logo=django)
![PyQt6](https://img.shields.io/badge/PyQt6-GUI-41CD52?style=for-the-badge&logo=qt)
![OpenCV](https://img.shields.io/badge/OpenCV-Computer%20Vision-5C3EE8?style=for-the-badge&logo=opencv)
![Raspberry Pi](https://img.shields.io/badge/Raspberry%20Pi-IoT-C51A4A?style=for-the-badge&logo=raspberry-pi)

## 📖 Project Overview
**Smart Gate Pro** is a robust, multi-modal security system designed for automated entrance management. It combines **Face Recognition** (with Liveness Detection), **Fingerprint Scanning**, and **RFID** verification into a unified platform running on a Raspberry Pi.

The system features a decoupled architecture where a **Django** backend manages user data and logs, while a **PyQt6** interface provides real-time feedback to users. A dedicated "Guardian" process ensures 24/7 uptime by monitoring system health.

## ✨ Key Features

### 🧠 Advanced AI & Security
* **Face Recognition:** Uses `Face_Recognition` (HOG models) for high-accuracy identification.
* **👁️ Anti-Spoofing (Liveness Check):** Integrated **MediaPipe Face Mesh** to detect eye blinks, preventing photo-based spoofing attacks.
* **Multi-Factor Authentication:** Supports Fingerprint and RFID via ESP32/ESP866 integration.

### ⚙️ System Reliability
* **🛡️ Guardian Watchdog:** A custom process (`guardian.py`) that monitors the Server and GUI, automatically restarting them if they crash or hang.
* **Hardware Bridge:** A dedicated serial bridge (`serial_bridge.py`) handles asynchronous communication with ESP modules to prevent UI freezing.

### 💻 User Interface & Management
* **Interactive GUI:** Built with **PyQt6**, featuring dynamic status updates, video feed, and visual feedback for access granted/denied.
* **Admin Dashboard:** A full Django web panel to manage users, enroll fingerprints, register RFID cards, and view detailed access logs.

## 🛠️ System Architecture

| Component | Technology | Description |
| :--- | :--- | :--- |
| **Core Controller** | Raspberry Pi 4/5 | Central processing unit. |
| **Backend** | Django + SQLite | Manages User/Profile DB and Attendance Logs. |
| **Frontend** | PyQt6 | Touch-screen interface for the gate. |
| **Vision** | OpenCV & MediaPipe | Frame processing and liveness detection. |
| **Hardware Link** | PySerial | Communicates with ESP microcontroller via USB. |
| **Process Manager** | Python Subprocess | Manages lifecycle of all subsystems. |

## 📂 Project Structure

```text
Smart_Gate_Project/
├── backend_server/          # Django Project Root
│   ├── manage.py            # Django Entry Point
│   ├── core/                # App containing Models & Views
│   ├── smart_gate_pro.py    # Main GUI Application (PyQt6)
│   └── db.sqlite3           # Main Database
├── guardian.py              # System Watchdog (Start this file!)
├── serial_bridge.py         # ESP32/Arduino Communication Bridge
└── requirements.txt         # Python Dependencies
