from django.contrib import admin
from .models import UserProfile, AttendanceLog, SystemState

# 1. جدول بيانات المستخدمين (البصمات والـ RFID)
@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'rfid_code', 'fingerprint_id', 'has_face_data')
    search_fields = ('user__username', 'rfid_code')
    list_filter = ('created_at',)
    
    # دالة عشان تظهر علامة صح لو اليوزر عنده بصمة وش
    def has_face_data(self, obj):
        return obj.face_encoding is not None
    has_face_data.boolean = True
    has_face_data.short_description = "Has Face ID?"

# 2. جدول سجلات الحضور (Logs)
@admin.register(AttendanceLog)
class AttendanceLogAdmin(admin.ModelAdmin):
    list_display = ('user', 'access_method', 'status', 'timestamp')
    list_filter = ('access_method', 'status', 'timestamp')
    search_fields = ('user__username',)
    readonly_fields = ('timestamp',) # عشان محدش يزور التاريخ

# 3. جدول حالة النظام (System State)
@admin.register(SystemState)
class SystemStateAdmin(admin.ModelAdmin):
    list_display = ('id', 'last_update', 'current_message', 'message_type')
    readonly_fields = ('last_update',)
