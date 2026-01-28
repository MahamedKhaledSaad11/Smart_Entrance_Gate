from django.db import models
from django.contrib.auth.models import User

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    rfid_code = models.CharField(max_length=100, null=True, blank=True, unique=True)
    fingerprint_id = models.IntegerField(null=True, blank=True, unique=True)
    face_encoding = models.BinaryField(null=True, blank=True)
    profile_picture = models.ImageField(upload_to='uploads/', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.user.username

class AttendanceLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    access_method = models.CharField(max_length=50) 
    status = models.CharField(max_length=50, default="Success")
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {self.timestamp}"

# --- الجدول الناقص ---
class SystemState(models.Model):
    last_update = models.DateTimeField(auto_now=True)
    current_message = models.CharField(max_length=200, blank=True, null=True)
    message_type = models.CharField(max_length=50, default="info") 

    def __str__(self): return "System Config"
