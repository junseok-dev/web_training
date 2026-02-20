from django.db import models

class Player(models.Model):
    name = models.CharField(max_length=100)
    season = models.CharField(max_length=20) # 예: 24TOTY
    position = models.CharField(max_length=10) # FW, MF 등
    ovr = models.IntegerField()
    image_url = models.URLField(blank=True) # 외부 이미지 링크 사용 시 편함

    def __str__(self):
        return f"[{self.season}] {self.name}"