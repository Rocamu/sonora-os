#!/bin/bash
# Run only inside the owned Sonora builder container.
set -Eeuo pipefail
ROOT=${SONORA_BUILD_ROOT:-/build/rootfs}
mkdir -p "$ROOT" /build/cache
trap 'umount "$ROOT/dev/pts" "$ROOT/dev" "$ROOT/proc" "$ROOT/sys" 2>/dev/null || true' EXIT
if [[ ! -e "$ROOT/.sonora-bootstrap" ]]; then
  debootstrap --arch=amd64 --variant=minbase --include=ca-certificates trixie "$ROOT" https://deb.debian.org/debian
  touch "$ROOT/.sonora-bootstrap"
fi
cat > "$ROOT/etc/apt/sources.list" <<'SOURCES'
deb https://deb.debian.org/debian trixie main non-free-firmware
deb https://deb.debian.org/debian trixie-updates main non-free-firmware
deb https://security.debian.org/debian-security trixie-security main non-free-firmware
SOURCES
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
chroot "$ROOT" /usr/bin/env DEBIAN_FRONTEND=noninteractive /bin/bash -e <<'CHROOT'
apt-get update
apt-get install -y --no-install-recommends \
 systemd-sysv systemd-resolved dbus linux-image-amd64 initramfs-tools kmod udev \
 iproute2 iputils-ping ethtool wpasupplicant iw rfkill \
 firmware-realtek firmware-iwlwifi firmware-brcm80211 \
 alsa-utils squeezelite ffmpeg flac sox libsox-fmt-all \
 avahi-daemon avahi-utils libnss-mdns \
 cifs-utils nfs-common python3 perl locales curl ca-certificates \
 sudo openssl chrony usbutils pciutils e2fsprogs parted cloud-guest-utils \
 less nano procps psmisc rsync ntfs-3g exfatprogs eject
printf 'en_US.UTF-8 UTF-8\nes_CL.UTF-8 UTF-8\n' > /etc/locale.gen
locale-gen
update-locale LANG=es_CL.UTF-8
ln -sf /usr/share/zoneinfo/America/Santiago /etc/localtime
printf 'America/Santiago\n' > /etc/timezone
printf 'sonora\n' > /etc/hostname
printf '127.0.0.1 localhost\n127.0.1.1 sonora\n::1 localhost ip6-localhost ip6-loopback\n' > /etc/hosts
mkdir -p /etc/systemd/network
cat > /etc/systemd/network/20-wired.network <<'NETWORK'
[Match]
Name=en* eth*
[Network]
DHCP=yes
IPv6AcceptRA=yes
MulticastDNS=yes
[DHCPv4]
UseHostname=false
NETWORK
systemctl enable systemd-networkd systemd-resolved avahi-daemon chrony serial-getty@ttyS0.service
ln -sf /run/systemd/resolve/stub-resolv.conf /etc/resolv.conf
# Root cannot be used to log in; setup is handled by the Sonora console/service.
passwd -l root
rm -f /etc/machine-id /var/lib/dbus/machine-id
: > /etc/machine-id
apt-get clean
CHROOT
touch "$ROOT/.sonora-base-ready"
printf '\nSONORA_BASE_READY root=%s\n' "$ROOT"
