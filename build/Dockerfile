FROM --platform=linux/amd64 debian:trixie-slim
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates debootstrap xz-utils e2fsprogs dosfstools fdisk gdisk parted \
    grub-pc-bin grub-efi-amd64-bin grub-efi-ia32-bin grub2-common mtools kmod rsync curl udev \
    && rm -rf /var/lib/apt/lists/*
COPY rootfs.sh image.sh /usr/local/lib/sonora-build/
CMD ["/bin/bash"]
