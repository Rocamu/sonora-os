#!/bin/bash
set -Eeuo pipefail
ROOT=${SONORA_BUILD_ROOT:-/build/rootfs}
[[ -e "$ROOT/.sonora-base-ready" ]] || { echo 'Prepare the base rootfs first.' >&2; exit 2; }
[[ -e /project/overlay.ready ]] || { echo 'The application owner must create overlay.ready before packaging.' >&2; exit 2; }
trap 'umount "$ROOT/dev/pts" "$ROOT/dev" "$ROOT/proc" "$ROOT/sys" 2>/dev/null || true' EXIT
cat > "$ROOT/usr/sbin/policy-rc.d" <<'POLICY'
#!/bin/sh
exit 101
POLICY
chmod 755 "$ROOT/usr/sbin/policy-rc.d"
mkdir -p "$ROOT/dev/pts" "$ROOT/proc" "$ROOT/sys"
mount --bind /dev "$ROOT/dev"
mount --bind /dev/pts "$ROOT/dev/pts"
mount -t proc proc "$ROOT/proc"
mount -t sysfs sysfs "$ROOT/sys"
rm -f "$ROOT/etc/resolv.conf"
cp -L /etc/resolv.conf "$ROOT/etc/resolv.conf"
cp /references/lyrionmusicserver_9.1.1_amd64.deb "$ROOT/tmp/lyrionmusicserver.deb"
chroot "$ROOT" /usr/bin/env DEBIAN_FRONTEND=noninteractive /bin/bash -e <<'CHROOT'
apt-get update
apt-get upgrade -y --no-install-recommends
apt-get install -y --no-install-recommends /tmp/lyrionmusicserver.deb grub2-common grub-pc-bin grub-efi-amd64-bin grub-efi-ia32-bin grub-efi-amd64-signed shim-signed systemd-resolved
rm -f /tmp/lyrionmusicserver.deb
apt-get clean
CHROOT
rsync -aH --numeric-ids /project/overlay/ "$ROOT/"
if [[ -x "$ROOT/usr/local/sbin/sonora-image-setup" ]]; then
  chroot "$ROOT" /usr/local/sbin/sonora-image-setup
fi
ln -sf /run/systemd/resolve/stub-resolv.conf "$ROOT/etc/resolv.conf"
rm -f "$ROOT/usr/sbin/policy-rc.d"
rm -f "$ROOT/etc/machine-id" "$ROOT/var/lib/dbus/machine-id"
: > "$ROOT/etc/machine-id"
# Every machine creates unique credentials and identifiers at first boot.
rm -f "$ROOT/var/lib/systemd/random-seed"
find "$ROOT/var/log" -type f -exec truncate -s0 '{}' +
touch "$ROOT/.sonora-finalized"
printf '\nSONORA_ROOTFS_FINALIZED\n'
