#!/bin/bash
set -Eeuo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends qemu-system-x86 qemu-utils ovmf curl python3 netcat-openbsd
exec /bin/bash /project/build/test-boot.sh "${1:-bios}"
