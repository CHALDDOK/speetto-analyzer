# 스피또 당첨 확률 분석기 🎰

동행복권 스피또 발행내역을 자동으로 수집해서
"출고율 높고 1등 잔여 많은 회차"를 한눈에 보여주는 웹 서비스입니다.

---

## 📁 파일 구조

```
speitto-analyzer/
├── main.py          ← 서버 메인 파일
├── scraper.py       ← 동행복권 데이터 자동 수집
├── requirements.txt ← Python 패키지 목록
├── Dockerfile       ← 배포 설정
└── static/
    └── index.html   ← 웹 화면
```

---

## 🚀 배포 방법 (Render.com - 무료)

### 1단계. GitHub 계정 만들기
- https://github.com 에서 회원가입 (무료)

### 2단계. 새 저장소 만들기
1. GitHub 로그인 후 우측 상단 `+` → `New repository`
2. Repository name: `speitto-analyzer`
3. `Create repository` 클릭
4. 이 폴더의 모든 파일을 업로드
   - `Upload an existing file` 클릭
   - 파일들을 드래그앤드롭 (static 폴더째로)
   - `Commit changes` 클릭

### 3단계. Render.com 배포
1. https://render.com 에서 회원가입 (GitHub 계정으로 로그인)
2. `New +` → `Web Service` 클릭
3. GitHub 연결 → `speitto-analyzer` 저장소 선택
4. 설정:
   - **Name**: speitto-analyzer (원하는 이름)
   - **Environment**: Docker
   - **Region**: Singapore (가장 가까움)
5. `Create Web Service` 클릭
6. 빌드 완료까지 5~10분 대기
7. 완료 후 제공된 URL로 접속! 🎉

### 4단계. 외부 공유
- Render.com이 `https://speitto-analyzer.onrender.com` 같은 URL을 제공합니다
- 이 URL을 누구에게나 공유하면 접속 가능합니다

---

## ⚠️ 주의사항

- Render.com 무료 티어는 15분 미접속 시 서버가 잠듦
  → 첫 접속 시 로딩이 30~60초 걸릴 수 있음
- 데이터는 60분마다 자동 갱신됩니다
- 동행복권 사이트 접근이 차단될 경우 데이터 수집이 실패할 수 있음

---

## 🔧 종합점수 계산 공식

```
종합점수 = (입고율 × 0.5) + (1등잔여 × 20, 최대40) + (2등잔여 × 3, 최대9)
```

| 점수    | 등급   | 의미               |
|---------|--------|--------------------|
| 85점 이상 | 🔥 최상 | 지금 바로 사세요   |
| 65~84  | ⚡ 양호 | 괜찮은 선택        |
| 40~64  | 📊 보통 | 무난함             |
| 39이하  | 💤 낮음 | 비추천             |
