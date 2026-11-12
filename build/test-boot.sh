#!/bin/bash
# Run in an ARM64 Linux container with qemu-system-x86 and ovmf installed.
# The delivered image is opened read-only behind a temporary qcow2 overlay.
set -Eeuo pipefail
umask 077
MODE=${1:-bios}
IMAGE=${2:-/project/images/sonora-os-0.1.0-amd64.img}
LOGDIR=${SONORA_TEST_LOGDIR:-/test-results}
[[ "$MODE" == bios || "$MODE" == uefi || "$MODE" == secureboot ]] || { echo 'Use bios, uefi or secureboot' >&2; exit 2; }
mkdir -p "$LOGDIR"
OVERLAY="/tmp/sonora-$MODE.qcow2"
if [[ -e $OVERLAY ]]; then
  [[ ${SONORA_TEST_REUSE_OVERLAY:-0} == 1 ]] || { echo 'Refusing to overwrite an existing test overlay.' >&2; exit 2; }
else
  qemu-img create -f qcow2 -F raw -b "$IMAGE" "$OVERLAY"
fi
RUNTIME_FLAGS=()
if [[ ${SONORA_TEST_ALLOW_REBOOT:-0} != 1 ]]; then RUNTIME_FLAGS=(-no-reboot); fi
FIRMWARE=()
MACHINE=q35
if [[ $MODE == uefi ]]; then
  cp /usr/share/OVMF/OVMF_VARS_4M.fd /tmp/sonora-uefi-vars.fd
  FIRMWARE=(-drive if=pflash,format=raw,readonly=on,file=/usr/share/OVMF/OVMF_CODE_4M.fd -drive if=pflash,format=raw,file=/tmp/sonora-uefi-vars.fd)
elif [[ $MODE == secureboot ]]; then
  cp /usr/share/OVMF/OVMF_VARS_4M.ms.fd /tmp/sonora-secure-vars.fd
  MACHINE=q35,smm=on
  FIRMWARE=(-global driver=cfi.pflash01,property=secure,value=on -drive if=pflash,format=raw,readonly=on,file=/usr/share/OVMF/OVMF_CODE_4M.secboot.fd -drive if=pflash,format=raw,file=/tmp/sonora-secure-vars.fd)
fi
EXTRA_DEVICES=()
if [[ -n ${SONORA_TEST_USB_MUSIC:-} ]]; then
  [[ -f $SONORA_TEST_USB_MUSIC ]] || { echo 'Test USB image does not exist.' >&2; exit 2; }
  EXTRA_DEVICES=(-drive "if=none,id=testmusic,format=raw,readonly=on,file=$SONORA_TEST_USB_MUSIC" -device usb-storage,drive=testmusic,removable=on)
fi
AUDIO_BACKEND=none,id=audio0
if [[ -n ${SONORA_TEST_AUDIO_WAV:-} ]]; then
  AUDIO_BACKEND="wav,id=audio0,path=$SONORA_TEST_AUDIO_WAV,out.frequency=${SONORA_TEST_AUDIO_RATE:-48000},out.channels=2,out.format=s16"
fi
# No host microphone, audio device or physical disk is attached.
exec qemu-system-x86_64 \
 -machine "$MACHINE" -accel tcg,thread=multi -cpu max -smp 2 -m 1536 \
 -drive "file=$OVERLAY,format=qcow2,if=virtio" \
 "${FIRMWARE[@]}" \
 -netdev user,id=lan,hostfwd=tcp:0.0.0.0:19080-:80,hostfwd=tcp:0.0.0.0:19000-:9000,hostfwd=tcp:0.0.0.0:19090-:9090 \
 -device virtio-net-pci,netdev=lan \
 -device qemu-xhci -audiodev "$AUDIO_BACKEND" -device usb-audio,audiodev=audio0 \
 "${EXTRA_DEVICES[@]}" \
 -display none -monitor none -qmp unix:/tmp/sonora-qmp.sock,server=on,wait=off \
 -chardev "socket,id=console,path=/tmp/sonora-serial.sock,server=on,wait=off,logfile=$LOGDIR/sonora-$MODE-serial.log" -serial chardev:console \
 "${RUNTIME_FLAGS[@]}"
