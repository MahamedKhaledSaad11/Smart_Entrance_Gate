#include <WiFi.h>
#include <HTTPClient.h>
#include <WiFiClientSecure.h>
#include <ArduinoJson.h>
#include <Adafruit_Fingerprint.h>
#include <SPI.h>
#include <MFRC522.h>

// ==========================================
// 1. إعدادات الشبكة والسيرفر (عدل هنا)
// ==========================================
const char* ssid = "HUAWEI MediaPad M5 lite 10";;
const char* password = "9ad644e623a0";
 // باسورد الشبكة
const char* serverBase = "https://192.168.43.46:8000"; // ⚠️ ضع IP الراسبيري الصحيح هنا

// ==========================================
// 2. إعدادات الهاردوير (Pins)
// ==========================================
#define LED_PIN 2

// Fingerprint Sensor (Green -> GPIO 16, White -> GPIO 17)
HardwareSerial mySerial(2);
Adafruit_Fingerprint finger = Adafruit_Fingerprint(&mySerial);

// RFID (SPI Pins: SDA=5, SCK=18, MOSI=23, MISO=19)
#define SS_PIN 5
#define RST_PIN 4
MFRC522 mfrc522(SS_PIN, RST_PIN);

// ==========================================
// 3. متغيرات النظام
// ==========================================
unsigned long lastPoll = 0;
bool isEnrolling = false; // ⚠️ متغير مهم جداً لمنع تكرار التسجيل

// ==========================================
// 4. دالة الإعداد (Setup)
// ==========================================
void setup() {
  Serial.begin(115200);
  pinMode(LED_PIN, OUTPUT);
  
  // 1. الاتصال بالواي فاي
  WiFi.begin(ssid, password);
  Serial.print("Connecting to WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500); Serial.print(".");
  }
  Serial.println("\n✅ WiFi Connected!");

  // 2. تشغيل حساس البصمة
  // (Rx, Tx) -> (16, 17)
  mySerial.begin(57600, SERIAL_8N1, 16, 17);
  finger.begin(57600);
  if (finger.verifyPassword()) {
    Serial.println("✅ Fingerprint Sensor Found");
  } else {
    Serial.println("❌ Fingerprint Sensor NOT Found (Check Wiring Green/White)");
  }

  // 3. تشغيل RFID
  SPI.begin();
  mfrc522.PCD_Init();
  Serial.println("✅ RFID Ready");
  
  Serial.println("--- SYSTEM STARTED ---");
}

// ==========================================
// 5. الدالة الرئيسية (Loop)
// ==========================================
void loop() {
  // الأولوية: لو إحنا مش بنسجل دلوقتي، روح اسأل السيرفر
  if (!isEnrolling && millis() - lastPoll > 2000) {
    checkServerCommands();
    lastPoll = millis();
  }

  // لو إحنا مش بنسجل، راقب الباب (دخول وخروج)
  if (!isEnrolling) {
    checkAccess();
  }
}

// ==========================================
// 6. دوال الاتصال بالسيرفر
// ==========================================

// دالة موحدة لإرسال الطلبات (HTTPS)
String sendRequest(String endpoint, String payload, bool isPost) {
  if (WiFi.status() == WL_CONNECTED) {
    WiFiClientSecure client;
    client.setInsecure(); // ⚠️ ضروري عشان نتجاهل شهادة SSL المحلية
    
    HTTPClient http;
    String url = String(serverBase) + endpoint;
    
    if (http.begin(client, url)) {
      if (isPost) http.addHeader("Content-Type", "application/x-www-form-urlencoded");
      
      int httpCode = isPost ? http.POST(payload) : http.GET();
      
      if (httpCode > 0) {
        String response = http.getString();
        http.end();
        return response;
      } else {
        Serial.print("HTTP Error: "); Serial.println(httpCode);
      }
      http.end();
    } else {
      Serial.println("Connection Failed");
    }
  }
  return "";
}

// فحص أوامر السيرفر (Enroll / Delete / Normal)
void checkServerCommands() {
  String res = sendRequest("/api/status/", "", false);
  
  // تحليل الرد
  if (res.indexOf("\"mode\": \"enroll\"") > 0) {
    Serial.println("\n🔵 COMMAND RECEIVED: ENROLL");
    isEnrolling = true;  // 1. قفل النظام
    blink(3);            // 2. تنبيه بصري
    enrollProcess();     // 3. تنفيذ التسجيل
    isEnrolling = false; // 4. فتح النظام
  }
  else if (res.indexOf("\"mode\": \"delete_all\"") > 0) {
    Serial.println("\n🔴 COMMAND RECEIVED: DELETE ALL");
    isEnrolling = true;
    finger.emptyDatabase();
    blink(5);
    sendRequest("/api/confirm-delete/", "", true);
    Serial.println("Database Wiped!");
    isEnrolling = false;
  }
}

// ==========================================
// 7. دوال البصمة والـ RFID
// ==========================================

// عملية تسجيل بصمة جديدة
void enrollProcess() {
  int id = getNextFreeID();
  if (id == -1) return;
  
  Serial.print("Enrolling ID #"); Serial.println(id);
  
  // خطوة 1: وضع الاصبع
  Serial.println("Place finger...");
  while (finger.getImage() != FINGERPRINT_OK);
  finger.image2Tz(1);
  Serial.println("Remove finger");
  digitalWrite(LED_PIN, HIGH); delay(500); digitalWrite(LED_PIN, LOW);
  delay(1000);
  while (finger.getImage() != FINGERPRINT_NOFINGER);
  
  // خطوة 2: التأكيد
  Serial.println("Place same finger again...");
  while (finger.getImage() != FINGERPRINT_OK);
  finger.image2Tz(2);
  digitalWrite(LED_PIN, HIGH); delay(500); digitalWrite(LED_PIN, LOW);
  
  // الحفظ
  if (finger.createModel() == FINGERPRINT_OK) {
    if (finger.storeModel(id) == FINGERPRINT_OK) {
      Serial.println("✅ Stored locally!");
      // إرسال للسيرفر للربط
      String r = sendRequest("/api/save-finger/", "id=" + String(id), true);
      if (r.indexOf("saved") > 0) Serial.println("✅ Linked to User on Server!");
      blink(2);
    } else {
      Serial.println("❌ Store Error");
      blink(5);
    }
  } else {
    Serial.println("❌ Mismatch Error");
    blink(5);
  }
}

// البحث عن مكان فارغ
int getNextFreeID() {
  for (int i = 1; i < 127; i++) {
    if (finger.loadModel(i) != FINGERPRINT_OK) return i;
  }
  return -1;
}

// فحص الدخول (Finger + RFID)
void checkAccess() {
  // --- 1. Fingerprint Check ---
  if (finger.getImage() == FINGERPRINT_OK) {
    if (finger.image2Tz() == FINGERPRINT_OK) {
      if (finger.fingerFastSearch() == FINGERPRINT_OK) {
        Serial.print("Finger Found ID: "); Serial.println(finger.fingerID);
        
        String r = sendRequest("/api/check-access/", "type=finger&data=" + String(finger.fingerID), true);
        handleAccessResponse(r);
      } else {
        Serial.println("Unknown Finger");
        blink(2);
      }
    }
  }

  // --- 2. RFID Check ---
  if (mfrc522.PICC_IsNewCardPresent() && mfrc522.PICC_ReadCardSerial()) {
    String uid = "";
    for (byte i = 0; i < mfrc522.uid.size; i++) {
      uid += String(mfrc522.uid.uidByte[i] < 0x10 ? "0" : "");
      uid += String(mfrc522.uid.uidByte[i], HEX);
    }
    uid.toUpperCase(); // حروف كبيرة
    
    // ⚠️ انسخ الكود ده وحطه في صفحة الأدمن ⚠️
    Serial.print(">>> SCANNED RFID: "); Serial.println(uid);
    
    String r = sendRequest("/api/check-access/", "type=rfid&data=" + uid, true);
    handleAccessResponse(r);
    
    mfrc522.PICC_HaltA();
    mfrc522.PCD_StopCrypto1();
    delay(1000);
  }
}

// التعامل مع رد السيرفر (فتح الباب)
void handleAccessResponse(String response) {
  if (response.indexOf("granted") > 0) {
    Serial.println("🔓 ACCESS GRANTED");
    openDoor();
  } else {
    Serial.println("🔒 ACCESS DENIED");
    blink(5); // رعشة رفض سريعة
  }
}

// فتح الباب (تشغيل الريليه/الليد)
void openDoor() {
  digitalWrite(LED_PIN, HIGH);
  delay(3000); // فتح لمدة 3 ثواني
  digitalWrite(LED_PIN, LOW);
}

// وميض الليد (للتنبيهات)
void blink(int n) {
  for (int i=0; i<n; i++) {
    digitalWrite(LED_PIN, HIGH); delay(100);
    digitalWrite(LED_PIN, LOW); delay(100);
  }
}