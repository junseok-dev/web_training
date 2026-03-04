# app/models.py
from django.db import models
from django.contrib.auth.models import User

# 유저 추가 정보 (API 키 저장)
class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    openai_api_key = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return f"{self.user.username}'s Profile"

# 테스트 기록 저장
class QuizHistory(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    category = models.CharField(max_length=50) # Python, SQL 등
    score = models.IntegerField()
    total_questions = models.IntegerField()
    ai_analysis = models.TextField() # AI 분석 결과 텍스트 전체 저장
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {self.category} ({self.created_at.strftime('%m/%d %H:%M')})"