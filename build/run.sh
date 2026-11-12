#!/bin/bash
set -Eeuo pipefail
PROJECT=$(cd "$(dirname "$0")/.." && pwd)
REFERENCES=${SONORA_REFERENCES:-$PROJECT/vendor-cache}
BUILDER=sonora-builder:trixie
VOLUME=sonora-build-rootfs
MODE=${1:-prepare}
COMMON=(--platform linux/amd64 --privileged --memory=4g --cpus=3 --label io.sonora.purpose=build --mount "type=volume,src=$VOLUME,dst=/build" --mount "type=bind,src=$PROJECT,dst=/project" --mount "type=bind,src=$REFERENCES,dst=/references,readonly")
case "$MODE" in
 prepare)
  docker volume create "$VOLUME" >/dev/null
  if ! docker image inspect "$BUILDER" >/dev/null 2>&1; then
    # Tool installation is bounded inside one task-owned Linux container.
    docker run --name sonora-tools --platform linux/amd64 --memory=2g --cpus=3 \
      --label io.sonora.purpose=build debian:trixie-slim /bin/bash -ec \
      'export DEBIAN_FRONTEND=noninteractive; apt-get update; apt-get install -y --no-install-recommends ca-certificates debootstrap xz-utils e2fsprogs dosfstools fdisk gdisk parted grub-pc-bin grub-efi-amd64-bin grub-efi-ia32-bin grub2-common mtools kmod rsync curl udev'
    docker commit sonora-tools "$BUILDER" >/dev/null
    docker rm sonora-tools >/dev/null
  fi
  docker run --rm --name sonora-rootfs "${COMMON[@]}" "$BUILDER" /bin/bash /project/build/rootfs.sh
  ;;
 finalize)
  docker run --rm --name sonora-finalize "${COMMON[@]}" "$BUILDER" /bin/bash /project/build/finalize.sh
  ;;
 image)
  docker run --rm --name sonora-image "${COMMON[@]}" "$BUILDER" /bin/bash /project/build/image.sh
  ;;
 status)
  docker ps -a --filter label=io.sonora.purpose=build --format '{{.Names}}\t{{.Status}}'
  docker volume inspect "$VOLUME" --format '{{.Name}}: {{.Mountpoint}}'
  ;;
 *) printf 'Usage: %s prepare|finalize|image|status\n' "$0" >&2; exit 2;;
esac
