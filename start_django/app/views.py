from django.shortcuts import render
from .models import Player

def index(request):
    players = Player.objects.all() # 모든 선수 데이터 가져오기
    return render(request, 'app/index.html', {'players': players})