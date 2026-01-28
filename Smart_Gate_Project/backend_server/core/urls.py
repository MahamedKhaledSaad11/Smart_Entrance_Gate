from django.urls import path
from . import views

urlpatterns = [
    path('signup/', views.signup_view, name='signup'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('dashboard/', views.user_dashboard, name='user_dashboard'),
    path('add_face/', views.add_face_wizard, name='add_face_wizard'),
    path('validate_face/', views.validate_and_capture, name='validate_face'),
    path('save_face_profile/', views.save_face_profile, name='save_face_profile'),
    path('admin_dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('update_rfid/', views.update_rfid, name='update_rfid'),
    path('trigger_enroll/', views.trigger_enroll, name='trigger_enroll'),
    path('trigger_delete_all/', views.trigger_delete_all, name='trigger_delete_all'),
    path('api/status/', views.esp_status),
    path('api/save-finger/', views.esp_save_finger),
    path('api/confirm-delete/', views.esp_confirm_delete),
    path('api/check-access/', views.check_access),
    path('', views.login_view, name='home'),
]
