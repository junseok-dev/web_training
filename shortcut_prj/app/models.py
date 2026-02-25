from django.db import models
from django.contrib.auth.models import User

class AnalysisResult(models.Model):
    user = models.ForeignKey(User, related_name='analyses', on_delete=models.CASCADE)
    idea = models.TextField()
    similarity_score = models.IntegerField()
    risk_level = models.CharField(max_length=10)
    
    similar_patent = models.CharField(max_length=255, default="해당 없음")
    summary = models.TextField()
    detailed_strategy = models.TextField(default="") # LLM 상세 제언
    final_verdict = models.TextField(default="")    # 최종 AI 결론
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']