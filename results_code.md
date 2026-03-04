# Web Testing & Monitoring Guide

## 1. 코드 로직 및 API 테스트 (pytest + TestClient)
가장 기본이 되는 테스트입니다. 서버를 직접 띄우지 않고도 API가 올바른 응답 상태 코드(200 OK)와 데이터를 반환하는지 검증합니다. (여기서는 널리 쓰이는 FastAPI의 TestClient를 예시로 들었습니다.)

```python
# test_api.py
from fastapi.testclient import TestClient
from main import app  # 개발 중인 메인 애플리케이션 임포트

client = TestClient(app)

def test_read_main():
    # 메인 페이지("/")에 GET 요청을 보냄
    response = client.get("/")
    
    # HTTP 상태 코드가 200인지 확인
    assert response.status_code == 200
    
    # 응답된 JSON 데이터가 기대하는 값과 일치하는지 확인
    assert response.json() == {"message": "웹 서비스가 정상적으로 실행 중입니다."}

```

## 2. 성능 및 부하 테스트 (Locust)
파이썬 기반으로 시나리오를 작성하여 가상의 사용자들이 서버에 접속하는 상황을 흉내 냅니다. 서버가 트래픽을 얼마나 잘 견디는지 한눈에 파악할 수 있습니다.

# locustfile.py 
```python
from locust import HttpUser, task, between

class WebsiteUser(HttpUser):
    # 유저들이 요청을 보내는 사이의 대기 시간 (1초 ~ 5초)
    wait_time = between(1, 5)

    @task(3)  # 메인 페이지 접속을 더 자주(가중치 3) 수행
    def load_main_page(self):
        self.client.get("/")

    @task(1)  # 검색 기능 사용 (가중치 1)
    def search_feature(self):
        # 가상의 검색 요청 시나리오
        self.client.get("/search?q=test_query")
```

## 3. 브라우저 및 UI 테스트 (Playwright)
실제 크롬 브라우저를 백그라운드에서 띄워 사용자의 행동을 흉내 내고 화면 요소들을 검증합니다. 프로젝트의 시각적 통일감을 위해 설정해 둔 흰색 배경이나 블루 컬러의 로고 같은 핵심 UI 요소들이 웹상에서 의도한 대로 잘 렌더링되었는지 자동으로 확인할 수 있습니다.

# test_ui.py
```python
from playwright.sync_api import Page, expect

def test_homepage_ui_and_logo(page: Page):
    # 1. 테스트할 웹페이지로 이동
    page.goto("http://localhost:8000")
    
    # 2. 메인 화면 배경색이 흰색(rgb(255, 255, 255))인지 확인
    body = page.locator("body")
    expect(body).to_have_css("background-color", "rgb(255, 255, 255)")

    # 3. 로고 요소가 블루 컬러 계열인지(예: 특정 hex 코드나 rgb 값) 확인
    logo = page.locator(".header-logo")
    expect(logo).to_be_visible() # 화면에 나타나는지 확인
    expect(logo).to_have_css("color", "rgb(0, 0, 255)") # 의도한 블루 컬러가 맞는지 검증
    
    # 4. 특정 버튼 클릭 시나리오 테스트
    page.click("text=로그인")
    expect(page).to_have_url("http://localhost:8000/login")

```

## 4. 모니터링 및 로깅 (Sentry 적용 예시)
모니터링은 일반적인 '테스트 코드'라기보다는, 실제 서비스가 돌아갈 때 실시간으로 에러를 잡아내고 지표를 수집하기 위한 설정(Configuration) 코드에 가깝습니다. 애플리케이션 진입점에 Sentry를 연결해 두면 예기치 못한 버그가 터졌을 때 즉시 알림을 받을 수 있습니다.

```python
# main.py (애플리케이션 최상단)
import sentry_sdk
from fastapi import FastAPI

# Sentry 초기화 (발급받은 DSN 주소 입력)
sentry_sdk.init(
    dsn="[https://examplePublicKey@o0.ingest.sentry.io/0](https://examplePublicKey@o0.ingest.sentry.io/0)",
    
    # 운영(production) 환경에서의 성능 모니터링 설정 (0.0에서 1.0 사이)
    traces_sample_rate=1.0,
)

app = FastAPI()

@app.get("/error-test")
def trigger_error():
    # 이 코드가 실행되어 에러가 발생하면 Sentry 대시보드로 즉시 리포트가 전송됨
    division_by_zero = 1 / 0

```