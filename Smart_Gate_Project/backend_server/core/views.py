from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth import login, logout
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .models import UserProfile, AttendanceLog
from django.contrib.auth.models import User
import face_recognition, numpy as np, pickle, cv2, mediapipe as mp
from django.contrib.auth.decorators import user_passes_test

# MediaPipe Setup
mp_face_mesh = mp.solutions.face_mesh
face_mesh = mp_face_mesh.FaceMesh(max_num_faces=1, refine_landmarks=True)

# Global Command State
SYSTEM_COMMAND = {"mode": "normal", "target_user_id": None}

# --- AUTH ---
@user_passes_test(lambda u: u.is_superuser)
def signup_view(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            UserProfile.objects.create(user=user)
            
            # التعديل 2: شيلنا سطر login(request, user)
            # عشان الأدمن يفضل هو اللي فاتح ميعملش سويتش لليوزر الجديد
            
            return redirect('admin_dashboard') # يرجع للوحة التحكم بعد الإنشاء
    else: 
        form = UserCreationForm()
    
    return render(request, 'core/signup.html', {'form': form})

def login_view(request):
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            login(request, form.get_user())
            if request.user.is_superuser: return redirect('admin_dashboard')
            return redirect('user_dashboard')
    else: form = AuthenticationForm()
    return render(request, 'core/login.html', {'form': form})

def logout_view(request): logout(request); return redirect('login')

# --- USER DASHBOARD ---
@login_required
def user_dashboard(request):
    logs = AttendanceLog.objects.filter(user=request.user).order_by('-timestamp')
    has_face = request.user.profile.face_encoding is not None
    return render(request, 'core/user_dashboard.html', {'logs': logs, 'has_face': has_face})

@login_required
def add_face_wizard(request): return render(request, 'core/add_face_wizard.html')

# --- FACE VALIDATION & CAPTURE ---
@csrf_exempt
def validate_and_capture(request):
    if request.method == 'POST':
        try:
            step = int(request.POST.get('step'))
            image_file = request.FILES.get('image')
            
            # Optimization: Resize for speed
            file_bytes = np.frombuffer(image_file.read(), np.uint8)
            img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
            small_frame = cv2.resize(img, (0, 0), fx=0.5, fy=0.5)
            rgb = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)
            
            # 1. MediaPipe Validation
            results = face_mesh.process(rgb)
            if not results.multi_face_landmarks:
                return JsonResponse({'status': 'fail', 'msg': 'No face detected!'})
            
            lm = results.multi_face_landmarks[0].landmark
            nose = lm[1].x; left = lm[234].x; right = lm[454].x
            rel_nose = (nose - left) / (right - left)
            
            valid, msg = False, ""
            if step in [1, 4]: # Front
                if 0.35 < rel_nose < 0.65: valid=True
                else: msg="Look Straight"
            elif step == 2: # Left
                if rel_nose > 0.60: valid=True
                else: msg="Turn Left"
            elif step == 3: # Right
                if rel_nose < 0.40: valid=True
                else: msg="Turn Right"
            elif step == 5: # Smile
                mouth = lm[291].x - lm[61].x
                if mouth > 0.45 or (0.40 < rel_nose < 0.60): valid=True
                else: msg="Smile!"

            if not valid: return JsonResponse({'status': 'fail', 'msg': msg})

            # 2. Encoding
            boxes = face_recognition.face_locations(rgb, model="hog")
            encs = face_recognition.face_encodings(rgb, boxes)
            
            if encs:
                if 'temp_encodings' not in request.session or step == 1:
                    request.session['temp_encodings'] = []
                
                saved = request.session['temp_encodings']
                saved.append(encs[0].tolist()) # Convert to list for JSON
                request.session['temp_encodings'] = saved
                return JsonResponse({'status': 'success'})
            return JsonResponse({'status': 'fail', 'msg': 'Blurry face'})
            
        except Exception as e: return JsonResponse({'status': 'error', 'msg': str(e)})
    return JsonResponse({'status': 'error'})

@login_required
def save_face_profile(request):
    encs = request.session.get('temp_encodings', [])
    if len(encs) >= 5:
        p = request.user.profile
        p.face_encoding = pickle.dumps(encs) # Save LIST of encodings
        if request.FILES.get('final_image'): p.profile_picture = request.FILES.get('final_image')
        p.save()
        del request.session['temp_encodings']
        return JsonResponse({'status': 'saved'})
    return JsonResponse({'status': 'error'})

# --- ADMIN DASHBOARD ---
@user_passes_test(lambda u: u.is_superuser)
def admin_dashboard(request):
    logs = AttendanceLog.objects.all().order_by('-timestamp')[:50]
    users = User.objects.all()
    # Filter users needing fingerprint
    no_finger = User.objects.filter(profile__fingerprint_id__isnull=True)
    return render(request, 'core/admin_dashboard.html', {'logs': logs, 'users': users, 'no_finger': no_finger})

@user_passes_test(lambda u: u.is_superuser)
def update_rfid(request):
    if request.method=='POST':
        u = User.objects.get(id=request.POST.get('user_id'))
        u.profile.rfid_code = request.POST.get('rfid_code')
        u.profile.save()
    return redirect('admin_dashboard')

# --- HARDWARE CONTROL APIs ---
@csrf_exempt
def trigger_enroll(request):
    global SYSTEM_COMMAND
    if request.user.is_superuser:
        SYSTEM_COMMAND = {"mode": "enroll", "target_user_id": request.POST.get('user_id')}
        return JsonResponse({"status": "ok", "msg": "Scanner Active"})
    return JsonResponse({"status": "error"})

@csrf_exempt
def trigger_delete_all(request):
    global SYSTEM_COMMAND
    if request.user.is_superuser:
        SYSTEM_COMMAND = {"mode": "delete_all", "target_user_id": None}
        UserProfile.objects.all().update(fingerprint_id=None)
        return JsonResponse({"status": "ok", "msg": "Wiping data..."})
    return JsonResponse({"status": "error"})

# ESP32 Communication
def esp_status(request): return JsonResponse(SYSTEM_COMMAND)

@csrf_exempt
def esp_save_finger(request):
    global SYSTEM_COMMAND
    fid = request.POST.get("id")
    
    response_data = {"status": "error"}

    # التأكد إننا فعلاً في وضع التسجيل
    if SYSTEM_COMMAND["mode"] == "enroll" and SYSTEM_COMMAND["target_user_id"]:
        try:
            # محاولة الحفظ
            user = User.objects.get(id=SYSTEM_COMMAND["target_user_id"])
            user.profile.fingerprint_id = int(fid)
            user.profile.save()
            response_data = {"status": "saved", "user": user.username}
            print(f"[SUCCESS] Fingerprint {fid} linked to {user.username}")
        except Exception as e:
            print(f"[ERROR] Failed to link finger: {e}")
            response_data = {"status": "error", "msg": str(e)}
        
        # ⚠️ الحل السحري: تصفير الحالة فوراً مهما حصل
        # ده بيضمن إن السيرفر مش هيقول للـ ESP32 يسجل تاني
        SYSTEM_COMMAND = {"mode": "normal", "target_user_id": None}
            
    return JsonResponse(response_data)

@csrf_exempt
def esp_confirm_delete(request):
    global SYSTEM_COMMAND
    SYSTEM_COMMAND = {"mode": "normal", "target_user_id": None}
    return JsonResponse({"status": "ok"})

@csrf_exempt
def check_access(request):
    type = request.POST.get("type")
    data = request.POST.get("data") # الكود الجاي من الـ ESP32
    
    print(f"⚡ [ACCESS CHECK] Type: {type} | Data: {data}") # طباعة للتشخيص

    try:
        user_profile = None
        
        if type == 'finger': 
            user_profile = UserProfile.objects.get(fingerprint_id=data)
        elif type == 'rfid': 
            # iexact: يعني ابحث وتجاهل الـ Capital/Small
            # strip: امسح أي مسافات زيادة
            user_profile = UserProfile.objects.get(rfid_code__iexact=data.strip())
            
        # تسجيل الدخول
        AttendanceLog.objects.create(
            user=user_profile.user, 
            access_method=type.upper(),
            status="Success"
        )
        print(f"✅ Granted: {user_profile.user.username}")
        return JsonResponse({"status": "granted", "user": user_profile.user.username})
        
    except UserProfile.DoesNotExist:
        print(f"❌ Denied: No user found with {type}={data}")
        return JsonResponse({"status": "denied"})
    except Exception as e:
        print(f"⚠️ Error: {e}")
        return JsonResponse({"status": "error"})
