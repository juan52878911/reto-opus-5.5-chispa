#!/usr/bin/env bash
# Upgrade kindling inside the Lima VM `kling-arm` (v0.10.0-34 -> v0.17.0-162-g9925612b).
# Mirrors `make deploy GOARCH=arm64` of kindling (core) + `make -C ext/mcp deploy`, but
# over `limactl copy` instead of ssh/scp. Backups: *.v010.bak next to each file.
# Run from macOS. Idempotent-ish: re-running rebuilds and reinstalls.
set -euo pipefail

VM=${VM:-kling-arm}
REPO=${REPO:-$HOME/Documents/GitHub/kindling}
REV=${REV:-9925612b}          # what the Mac CLI 0.17.0-162 was built from (main)
WT=/tmp/kindling-v017
OUT=/tmp/kv017-out

# 1. Build in a detached worktree (never touch the repo's checked-out branch).
[ -d "$WT" ] || git -C "$REPO" worktree add --detach "$WT" "$REV"
V=$(git -C "$WT" describe --tags --always)
rm -rf "$OUT"; mkdir -p "$OUT/lib"
L="-s -w -X main.Version=$V"
( cd "$WT" && export CGO_ENABLED=0 GOOS=linux GOARCH=arm64
  go build -trimpath -ldflags "$L" -o "$OUT/kling"        ./cmd/kling
  go build -trimpath -ldflags "$L" -o "$OUT/kling-guest"  ./cmd/kling-guest
  go build -trimpath -ldflags "$L" -o "$OUT/kling-chispa" ./cmd/kling-chispa
  cd ext/mcp
  go build -trimpath -ldflags "$L" -o "$OUT/kling-mcp"    ./cmd/kling-mcp
  go build -trimpath -ldflags "$L" -o "$OUT/kling-bridge" ./cmd/kling-bridge )
cp "$WT"/scripts/{81-base-image.sh,71-build-glibc-base.sh,minimal-init.sh,lib-ext4-shrink.sh} \
   "$WT"/packaging/kling.service "$WT"/ext/mcp/scripts/80-mcp-image.sh "$OUT/lib/"
for b in base llm chispa android; do cp "$WT/scripts/builders/$b" "$OUT/lib/builder-$b"; done
cp "$WT/ext/mcp/scripts/builders/mcp" "$OUT/lib/builder-mcp"

# 2. Copy into the VM.
limactl shell "$VM" -- mkdir -p /tmp/kv017
limactl copy -r "$OUT/." "$VM:/tmp/kv017/"

# 3. Back up, install, restart. KillMode=process: running microVMs survive the restart.
#    v0.17's unit reads host config from /etc/default/kling (the old unit had it inline).
#    v0.15+ requires jailer (already at /usr/local/bin/jailer, user kindling in group kvm).
limactl shell "$VM" -- bash -lc '
set -e; L=/usr/local/lib/kindling; D=/tmp/kv017
[ -f /usr/local/bin/kling.v010.bak ] || {
  sudo cp -p /usr/local/bin/kling /usr/local/bin/kling.v010.bak
  sudo cp -p /usr/local/bin/kling-mcp /usr/local/bin/kling-mcp.v010.bak
  for f in kling-guest kling-bridge 71-build-glibc-base.sh 80-mcp-image.sh 81-base-image.sh minimal-init.sh; do
    sudo cp -p $L/$f $L/$f.v010.bak; done
  sudo cp -a $L/builders $L/builders.v010.bak
  sudo cp -p /etc/systemd/system/kling.service /etc/systemd/system/kling.service.v010.bak.disabled; }
sudo install -m755 $D/kling     /usr/local/bin/kling
sudo install -m755 $D/kling-mcp /usr/local/bin/kling-mcp
sudo install -m755 $D/kling-guest $D/kling-chispa $D/kling-bridge $L/
for f in 71-build-glibc-base.sh 80-mcp-image.sh 81-base-image.sh minimal-init.sh lib-ext4-shrink.sh; do
  sudo install -m755 $D/lib/$f $L/$f; done
for b in base llm chispa android mcp; do sudo install -m755 $D/lib/builder-$b $L/builders/$b; done
sudo install -m644 $D/lib/kling.service /etc/systemd/system/kling.service
[ -f /etc/default/kling ] || printf "%s\n" "# Config de kling propia de este host" \
  "KLING_SOCKET_USER=juanbedoya" "KLING_RUN_AS=kindling" | sudo tee /etc/default/kling >/dev/null
sudo systemctl daemon-reload
sudo systemctl restart kling && sleep 2 && systemctl is-active kling
sudo systemctl restart kling-gateway && systemctl is-active kling-gateway
rm -rf /tmp/kv017
kling version; kling status'

# 4. Rebuild our image so it carries the v0.17 guest agent.
limactl shell "$VM" -- bash -lc '
echo "{}" > /tmp/spec.json
kling image build arena-base -builder base -base min -spec /tmp/spec.json
kling image recipe arena-base'

# 5. Smoke test: VON template restores and serves.
limactl shell "$VM" -- bash -lc '
kling run -from von-qwen-q4 -name t
ip=$(kling inspect t | grep "\"ip\"" | cut -d\" -f4)
curl -s -m 10 "$ip:8000/v1/models" | head -c 200; echo
kling rm t'

# Rollback: sudo cp /usr/local/bin/kling.v010.bak /usr/local/bin/kling (same for the
# others), restore kling.service.v010.bak.disabled, daemon-reload, restart kling.
# git -C "$REPO" worktree remove "$WT"   # when done
