#!/bin/bash
# Run inside the Sonora builder with only its own image attached as a loop device.
set -Eeuo pipefail
ROOT=${SONORA_BUILD_ROOT:-/build/rootfs}
OUT=${SONORA_IMAGE_OUT:-/project/images}
VERSION=${SONORA_VERSION:-0.1.0}
SIZE_MIB=${SONORA_IMAGE_SIZE_MIB:-4096}
IMAGE="$OUT/sonora-os-${VERSION}-amd64.img"
MNT=/build/image-mount
LOOP=
cleanup() {
  set +e
  mountpoint -q "$MNT/boot/efi" && umount "$MNT/boot/efi"
  mountpoint -q "$MNT" && umount "$MNT"
  [[ -n "$LOOP" ]] && losetup -d "$LOOP"
}
trap cleanup EXIT
[[ -e "$ROOT/.sonora-finalized" ]] || { echo 'Rootfs finalization is required first.' >&2; exit 2; }
[[ $SIZE_MIB =~ ^[0-9]+$ && $SIZE_MIB -ge 3072 ]] || { echo 'Image must be at least 3072 MiB.' >&2; exit 2; }
mkdir -p "$OUT" "$MNT"
[[ ! -e "$IMAGE" ]] || { echo "Refusing to replace existing image: $IMAGE" >&2; exit 2; }
truncate -s "${SIZE_MIB}M" "$IMAGE"
sgdisk --clear \
 --new=1:2048:+1M --typecode=1:ef02 --change-name=1:'Sonora BIOS boot' \
 --new=2:0:+128M --typecode=2:ef00 --change-name=2:'Sonora EFI' \
 --new=3:0:0 --typecode=3:8300 --change-name=3:'Sonora system' "$IMAGE"
LOOP=$(losetup --find --show --partscan "$IMAGE")
# Never permit a physical block-device target or another task's loop mapping.
[[ $LOOP =~ ^/dev/loop[0-9]+$ ]] || { echo 'Unexpected loop device.' >&2; exit 3; }
BACKING=$(losetup -n -O BACK-FILE "$LOOP")
[[ "$BACKING" == "$IMAGE" ]] || { echo "Unexpected backing file: $BACKING" >&2; exit 3; }
for n in 1 2 3; do
  node="${LOOP}p$n"
  if [[ ! -b "$node" ]]; then
    dev=$(cat "/sys/class/block/$(basename "$node")/dev")
    mknod "$node" b "${dev%:*}" "${dev#*:}"
  fi
done
mkfs.vfat -F 32 -n SONORA_EFI "${LOOP}p2"
mkfs.ext4 -F -L SONORA_ROOT -m 1 "${LOOP}p3"
ROOT_UUID=$(blkid -s UUID -o value "${LOOP}p3")
EFI_UUID=$(blkid -s UUID -o value "${LOOP}p2")
mount "${LOOP}p3" "$MNT"
rsync -aHAX --numeric-ids --exclude=/dev/* --exclude=/proc/* --exclude=/sys/* \
 --exclude=/run/* --exclude=/tmp/* --exclude=/.sonora-* "$ROOT/" "$MNT/"
mkdir -p "$MNT"/{dev,proc,sys,run,tmp,boot/efi}
chmod 1777 "$MNT/tmp"
cat > "$MNT/etc/fstab" <<FSTAB
UUID=$ROOT_UUID / ext4 defaults,noatime,errors=remount-ro 0 1
UUID=$EFI_UUID /boot/efi vfat defaults,noatime,umask=0077 0 2
FSTAB
cat > "$MNT/etc/default/grub" <<'DEFAULTS'
GRUB_DEFAULT=0
GRUB_TIMEOUT=3
GRUB_DISTRIBUTOR="Sonora OS"
GRUB_CMDLINE_LINUX_DEFAULT="quiet console=tty0 console=ttyS0,115200n8"
GRUB_CMDLINE_LINUX="rootwait"
GRUB_DISABLE_OS_PROBER=true
GRUB_TERMINAL="console serial"
GRUB_SERIAL_COMMAND="serial --speed=115200 --unit=0 --word=8 --parity=no --stop=1"
DEFAULTS
mount "${LOOP}p2" "$MNT/boot/efi"
grub-install --target=i386-pc --boot-directory="$MNT/boot" --modules='part_gpt ext2' --recheck "$LOOP"
grub-install --target=x86_64-efi --efi-directory="$MNT/boot/efi" --boot-directory="$MNT/boot" --removable --no-nvram --recheck
grub-install --target=i386-efi --directory="$ROOT/usr/lib/grub/i386-efi" --efi-directory="$MNT/boot/efi" --boot-directory="$MNT/boot" --removable --no-nvram --recheck
KERNEL=$(find "$MNT/boot" -maxdepth 1 -type f -name 'vmlinuz-*' -printf '%f\n' | sort -V | tail -1)
[[ -n $KERNEL ]] || { echo 'No installed kernel.' >&2; exit 4; }
INITRD="initrd.img-${KERNEL#vmlinuz-}"
[[ -f "$MNT/boot/$INITRD" ]] || { echo 'No installed initramfs.' >&2; exit 4; }
mkdir -p "$MNT/boot/grub"
cat > "$MNT/boot/grub/grub.cfg" <<GRUB
set default=0
set timeout=3
serial --unit=0 --speed=115200 --word=8 --parity=no --stop=1
terminal_input console serial
terminal_output console serial
menuentry 'Sonora OS $VERSION' {
    search --no-floppy --fs-uuid --set=root $ROOT_UUID
    linux /boot/$KERNEL root=UUID=$ROOT_UUID rw rootwait quiet console=tty0 console=ttyS0,115200n8
    initrd /boot/$INITRD
}
menuentry 'Sonora OS $VERSION — recovery console' {
    search --no-floppy --fs-uuid --set=root $ROOT_UUID
    linux /boot/$KERNEL root=UUID=$ROOT_UUID rw rootwait console=tty0 console=ttyS0,115200n8 systemd.unit=rescue.target
    initrd /boot/$INITRD
}
GRUB
# Use Debian's signed removable chain when present. Its external configuration
# locates this image by filesystem UUID rather than assuming a disk number.
if [[ -f "$ROOT/usr/lib/shim/shimx64.efi.signed" && -f "$ROOT/usr/lib/grub/x86_64-efi-signed/grubx64.efi.signed" ]]; then
  install -m 644 "$ROOT/usr/lib/shim/shimx64.efi.signed" "$MNT/boot/efi/EFI/BOOT/BOOTX64.EFI"
  install -m 644 "$ROOT/usr/lib/grub/x86_64-efi-signed/grubx64.efi.signed" "$MNT/boot/efi/EFI/BOOT/grubx64.efi"
  if [[ -f "$ROOT/usr/lib/shim/mmx64.efi.signed" ]]; then
    install -m 644 "$ROOT/usr/lib/shim/mmx64.efi.signed" "$MNT/boot/efi/EFI/BOOT/mmx64.efi"
  fi
  for d in BOOT debian; do
    mkdir -p "$MNT/boot/efi/EFI/$d"
    cat > "$MNT/boot/efi/EFI/$d/grub.cfg" <<GRUBEFI
search --no-floppy --fs-uuid --set=root $ROOT_UUID
set prefix=(\$root)/boot/grub
configfile \$prefix/grub.cfg
GRUBEFI
  done
fi
# Preserve a small, machine-readable manifest alongside the public image.
chroot "$MNT" dpkg-query -W -f='${Package}\t${Version}\t${Architecture}\n' > "$OUT/sonora-os-${VERSION}-packages.tsv"
sgdisk --print "$IMAGE" > "$OUT/sonora-os-${VERSION}-partitions.txt"
printf '{"version":"%s","architecture":"amd64","size_mib":%s,"root_uuid":"%s","efi_uuid":"%s","kernel":"%s","boot":"BIOS + x86_64 UEFI + IA32 UEFI mixed mode","persistence":"writable ext4 root"}\n' \
 "$VERSION" "$SIZE_MIB" "$ROOT_UUID" "$EFI_UUID" "$KERNEL" > "$OUT/sonora-os-${VERSION}-manifest.json"
sync
umount "$MNT/boot/efi"
umount "$MNT"
e2fsck -fn "${LOOP}p3"
losetup -d "$LOOP"
LOOP=
(cd "$OUT" && sha256sum "$(basename "$IMAGE")" > "$(basename "$IMAGE").sha256")
xz -T2 -4 --keep "$IMAGE"
(cd "$OUT" && sha256sum "$(basename "$IMAGE").xz" > "$(basename "$IMAGE").xz.sha256")
printf '\nSONORA_IMAGE_READY %s.xz\n' "$IMAGE"
