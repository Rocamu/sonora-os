#!/bin/bash
set -Eeuo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends \
 ca-certificates debootstrap xz-utils e2fsprogs dosfstools fdisk gdisk parted \
 grub-pc-bin grub-efi-amd64-bin grub-efi-ia32-bin grub2-common mtools kmod rsync curl udev
exec /bin/bash /project/build/rootfs.sh
