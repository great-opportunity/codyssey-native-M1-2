#!/bin/sh
# Vercel 빌드 단계에서 실행: 환경 변수 API_BASE_URL을 브라우저가 읽을 수 있는 config.js로 만든다.
# (바닐라 JS는 process.env를 못 읽기 때문)
set -e
: "${API_BASE_URL:?Vercel 환경 변수 API_BASE_URL을 설정하세요}"
printf 'window.APP_CONFIG = { API_BASE_URL: "%s" };\n' "$API_BASE_URL" > config.js
echo "config.js 생성: API_BASE_URL=$API_BASE_URL"
