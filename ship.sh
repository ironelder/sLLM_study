#!/bin/sh
# 스테이징된 변경을 .git/STUDY_COMMIT_MSG 로 커밋하고 현재 브랜치를 push (메시지는 미리 작성, 실행은 사람)
set -eu
cd "$(dirname "$0")"
MSG=.git/STUDY_COMMIT_MSG
[ -f "$MSG" ] || { echo "커밋 메시지 파일 없음: $MSG"; exit 1; }
git diff --cached --quiet && { echo "스테이징된 변경 없음"; exit 1; }
git commit -F "$MSG"
git push
rm -f "$MSG"
git log --oneline -1
