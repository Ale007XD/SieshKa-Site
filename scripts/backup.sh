#!/bin/sh
set -e

echo "Waiting for database..."
until pg_isready -h db -U "$POSTGRES_USER" -d "$POSTGRES_DB"; do
  sleep 5
done

echo "Starting backup service..."

while true; do
  TIMESTAMP=$(date +%Y%m%d_%H%M%S)
  BACKUP_FILE="/backups/backup_${TIMESTAMP}.sql"
  
  echo "Creating backup: $BACKUP_FILE"
  
  if pg_dump -h db -U "$POSTGRES_USER" -d "$POSTGRES_DB" > "$BACKUP_FILE"; then
    gzip "$BACKUP_FILE"
    echo "Backup completed: ${BACKUP_FILE}.gz"
    
    if [ -n "$BACKUP_RETENTION_DAYS" ]; then
      echo "Cleaning backups older than $BACKUP_RETENTION_DAYS days..."
      find /backups -name "backup_*.sql.gz" -mtime +$BACKUP_RETENTION_DAYS -delete
    fi
    
    du -h /backups/*.sql.gz 2>/dev/null | tail -5
  else
    echo "ERROR: Backup failed!"
  fi
  
  echo "Next backup in 24 hours..."
  sleep 86400
done
