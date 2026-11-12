#!/bin/bash
# Create only a new synthetic USB music image, without attaching a loop device.
set -Eeuo pipefail
IMAGE=${1:?Usage: make-test-usb.sh new-test-usb.img tone1.wav [tone2.wav ...]}
shift
[[ $# -ge 1 ]] || { echo 'At least one synthetic test WAV is required.' >&2; exit 2; }
[[ ! -e $IMAGE ]] || { echo 'Refusing to overwrite an existing image.' >&2; exit 2; }
for f in "$@"; do [[ -f $f ]] || { echo "Missing test file: $f" >&2; exit 2; }; done
truncate -s 128M "$IMAGE"
printf 'label: dos\nstart=2048,type=c\n' | sfdisk "$IMAGE" >/dev/null
mformat -i "$IMAGE@@1048576" -F -v SONORA_TEST ::
for f in "$@"; do mcopy -i "$IMAGE@@1048576" "$f" ::/; done
mdir -i "$IMAGE@@1048576" ::/
