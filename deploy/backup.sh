#!/usr/bin/env sh
# 데이터베이스 백업. 서버가 돌고 있는 채로 안전하게 복사본을 뜬다(SQLite 온라인 백업).
# 사용: 저장소 루트에서 `sh deploy/backup.sh` (cron으로 하루 한 번 권장)
# 복사본에는 비밀번호 해시와 암호화된 인증 앱 비밀값, 매매 기록이 들어 있다. 서버 밖 안전한 곳으로 옮겨 보관한다.
set -eu

KEEP="${KEEP:-14}"                 # 남겨 둘 백업 개수
OUT_DIR="${OUT_DIR:-./backups}"
STAMP="$(date +%Y%m%d-%H%M%S)"
TMP="/data/backup-${STAMP}.db"

mkdir -p "$OUT_DIR"

docker compose exec -T app python - "$TMP" <<'PY'
import sqlite3
import sys

source = sqlite3.connect("/data/alphapilot.db")
target = sqlite3.connect(sys.argv[1])
with target:
    source.backup(target)
target.close()
source.close()
PY

docker compose cp "app:${TMP}" "${OUT_DIR}/alphapilot-${STAMP}.db"
docker compose exec -T app rm -f "$TMP"

# 오래된 백업 정리: 이 스크립트가 만든 이름의 파일만, 최근 KEEP개를 빼고 지운다.
ls -1t "${OUT_DIR}"/alphapilot-*.db 2>/dev/null | tail -n +"$((KEEP + 1))" | while IFS= read -r old; do
  rm -f -- "$old"
done

echo "백업 완료: ${OUT_DIR}/alphapilot-${STAMP}.db"
