# 서버에 올리기

이 구성(`docker-compose.yml`, `deploy/Dockerfile`, `deploy/Caddyfile`)은 작성만 했고 **실제 서버에서 빌드해 본 적은 없다.** 처음 올릴 때 빌드 오류가 나면 그 메시지를 기준으로 고쳐야 한다.

## 준비할 것

- 서울 리전 리눅스 서버 1대(메모리 2GB 이상 권장), **고정 공인 IP**. 키움 API는 등록한 IP에서만 인증되므로 IP가 바뀌면 안 된다.
- 도메인 1개. DNS A 레코드가 서버 IP를 가리켜야 HTTPS 인증서가 발급된다.
- 서버에 Docker와 Docker Compose.
- 방화벽은 80, 443만 연다. 앱 포트(8000)는 밖에 열지 않는다.

## 순서

1. 저장소를 서버에 올리고 그 폴더로 들어간다.
2. `.env.example`을 `.env`로 복사해 값을 채운다. 최소한 `AP_DOMAIN`, `AP_ALLOWED_HOSTS`, `AP_SECRET_KEY`, `AP_SETUP_TOKEN`이 필요하다. 파일 안의 "만들기" 명령으로 무작위 값을 만든다.
3. 실행한다.

```bash
docker compose up -d --build
```

4. 로그에서 앱이 뜬 것을 확인한다.

```bash
docker compose logs -f app
```

5. 브라우저로 `https://<도메인>`에 접속해 처음 등록을 한다. 비밀번호, `AP_SETUP_TOKEN` 값, 인증 앱 QR 순서다. 등록을 마친 뒤에는 `.env`에서 `AP_SETUP_TOKEN`을 지우고 다시 올려도 된다.

## 운영

- **엔진은 하나만.** `app` 서비스를 여러 개로 늘리지 않는다. 주문이 두 번 나갈 수 있다.
- **백업.** `sh deploy/backup.sh`가 돌고 있는 채로 데이터베이스 복사본을 `backups/`에 만든다. 하루 한 번 cron에 걸고, 복사본은 서버 밖으로 옮겨 둔다. 복사본에는 비밀번호 해시와 매매 기록이 들어 있다.
- **업데이트.** 코드를 바꾼 뒤 `docker compose up -d --build`. 서버가 다시 시작되면 화면 위에 확인 안내가 뜨고, 확인하기 전까지 모든 주문 계획이 승인을 기다린다.
- **`AP_SECRET_KEY`는 바꾸지 않는다.** 바꾸면 인증 앱 비밀값을 풀 수 없어 로그인 등록을 다시 해야 한다.
- **로그인 분실.** 비밀번호나 인증 앱을 잃으면 데이터베이스의 `users` 표를 비우고 처음 등록을 다시 한다(매매 기록은 남는다).

## 확인할 것

- `https://<도메인>/api/health`가 `{"ok": true}`를 돌려준다.
- 로그인하지 않은 채 `https://<도메인>/api/status`는 401이다.
- 응답 머리에 `Strict-Transport-Security`와 `Content-Security-Policy`가 있다.
