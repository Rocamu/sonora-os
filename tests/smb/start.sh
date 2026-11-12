#!/bin/sh
set -eu
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq --no-install-recommends samba > /tmp/install.log
mkdir -p /var/log/samba /run/samba
cat > /etc/samba/smb.conf <<'CONF'
[global]
  server role = standalone server
  security = user
  map to guest = Bad User
  server min protocol = SMB3
  log level = 0
  load printers = no
  disable spoolss = yes
[Music]
  path = /music
  guest ok = yes
  read only = yes
  browsable = yes
  force user = nobody
CONF
exec smbd --foreground --no-process-group --debug-stdout
