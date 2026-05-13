FROM rclone/rclone:latest

RUN apk add --no-cache bash docker-cli

COPY backup-wwtp-sql.sh /usr/local/bin/backup-wwtp-sql.sh

ENTRYPOINT ["bash", "/usr/local/bin/backup-wwtp-sql.sh"]
