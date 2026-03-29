#!/bin/bash

# ShopCrawl Backup Script
# 사용법: ./backup.sh
# Cron 설정: 0 3 * * * /opt/shopcrawl/backup.sh >> /opt/shopcrawl/backups/cron.log 2>&1

set -e

# 설정
BACKUP_DIR="/opt/shopcrawl/backups"
DATA_DIR="/opt/shopcrawl/data"
DATE=$(date +%Y%m%d_%H%M%S)
RETENTION_DAYS=7

echo "[$DATE] 백업 시작"

# 백업 디렉토리 확인
mkdir -p "$BACKUP_DIR"

# DB 백업
if [ -f "$DATA_DIR/hotdeals.db" ]; then
    echo "DB 백업 중..."
    cp "$DATA_DIR/hotdeals.db" "$BACKUP_DIR/hotdeals_backup_$DATE.db"
    echo "DB 백업 완료: hotdeals_backup_$DATE.db"
else
    echo "경고: DB 파일을 찾을 수 없습니다"
fi

# ChromaDB 백업
if [ -d "/opt/shopcrawl/chroma_db" ]; then
    echo "ChromaDB 백업 중..."
    tar -czf "$BACKUP_DIR/chroma_backup_$DATE.tar.gz" -C /opt/shopcrawl chroma_db
    echo "ChromaDB 백업 완료: chroma_backup_$DATE.tar.gz"
else
    echo "경고: ChromaDB 디렉토리를 찾을 수 없습니다"
fi

# 오래된 백업 삭제
echo "오래된 백업 정리 중..."
find "$BACKUP_DIR" -name "hotdeals_backup_*.db" -mtime +$RETENTION_DAYS -delete
find "$BACKUP_DIR" -name "chroma_backup_*.tar.gz" -mtime +$RETENTION_DAYS -delete

# 현재 백업 목록
echo "현재 백업 목록:"
ls -lh "$BACKUP_DIR" | tail -5

echo "[$DATE] 백업 완료"
