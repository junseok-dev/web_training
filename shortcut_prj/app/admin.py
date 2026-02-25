from django.contrib import admin
from .models import AnalysisResult

@admin.register(AnalysisResult)
class AnalysisResultAdmin(admin.ModelAdmin):
    list_display = ('user', 'idea', 'similarity_score', 'risk_level', 'created_at')
    list_filter = ('risk_level', 'created_at')
    search_fields = ('idea', 'user__username')