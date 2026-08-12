#!/usr/bin/env sh
set -eu

database=${LUCULENT_DATABASE:-sqlite}

cat > /app/settings.txt <<EOF
database=$database
sqlite_path=/data/luculent.db
mysql_host=${LUCULENT_MYSQL_HOST:-mysql}
mysql_port=${LUCULENT_MYSQL_PORT:-3306}
mysql_database=${LUCULENT_MYSQL_DATABASE:-luculent}
mysql_user=${LUCULENT_MYSQL_USER:-luculent}
mysql_password=${LUCULENT_MYSQL_PASSWORD:-luculent}
EOF

exec python -m app.web --host 0.0.0.0 --port 5000
