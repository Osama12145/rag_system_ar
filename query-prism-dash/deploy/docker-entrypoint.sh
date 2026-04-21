#!/bin/sh
set -eu

: "${BACKEND_UPSTREAM:=http://backend:8000}"

envsubst '${BACKEND_UPSTREAM}' \
  < /etc/nginx/templates/default.conf.template \
  > /etc/nginx/conf.d/default.conf

cat <<EOF >/usr/share/nginx/html/config.js
window.__APP_CONFIG__ = {
  API_BASE: ""
};
EOF

exec nginx -g 'daemon off;'
