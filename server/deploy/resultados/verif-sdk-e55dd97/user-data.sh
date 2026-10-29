#!/bin/bash
# Verificación de la rama SDK en un clon limpio (git archive). c6a.xlarge, AL2023. Apagado forzoso a los 60 min.
CHISPA_S3=__CHISPA_S3__
shutdown -h +60
BASE=/opt/v; REPO=$BASE/repo; RES=$BASE/res; mkdir -p $REPO $RES; exec > >(tee -a $RES/log.txt) 2>&1
export HOME=/root
cierre() { echo "== listo $(date -u +%FT%TZ)"; cd $BASE && tar czf res.tgz -C $BASE res; aws s3 cp --only-show-errors $BASE/res.tgz $CHISPA_S3/resultados.tgz; aws s3 cp --only-show-errors $RES/log.txt $CHISPA_S3/log.txt; shutdown -h now; }
trap cierre EXIT
suite() { local n=$1; shift; echo "== $n $(date -u +%T)"; ( "$@" ) > $RES/$n.log 2>&1; local rc=$?
  local p=$(grep -c -- '^--- PASS\|^ok ' $RES/$n.log); local f=$(grep -c -- '^--- FAIL\|^FAIL' $RES/$n.log); local s=$(grep -c -- '^--- SKIP' $RES/$n.log)
  printf '%s\t%s\tpass=%s\tfail=%s\tskip=%s\n' "$n" "$([ $rc = 0 ] && echo OK || echo FALLO rc=$rc)" "$p" "$f" "$s" | tee -a $RES/resumen.tsv; }
dnf install -y -q gcc git tar gzip python3.11 python3.11-pip
cd /tmp && curl -fsSL https://go.dev/dl/go1.27.1.linux-amd64.tar.gz | tar xz -C /usr/local && export PATH=/usr/local/go/bin:$PATH
mkdir -p /opt/ort && curl -fsSL https://github.com/microsoft/onnxruntime/releases/download/v1.31.1/onnxruntime-linux-x64-1.31.1.tgz | tar xz -C /opt/ort --strip-components=1
ORTLIB=$(ls /opt/ort/lib/libonnxruntime.so.1.31.1 2>/dev/null || ls /opt/ort/lib/libonnxruntime.so* | head -1); echo "ORT: $ORTLIB"
python3.11 -m venv $BASE/venv; PY=$BASE/venv/bin/python
$PY -m pip install -q -U pip; $PY -m pip install -q torch --index-url https://download.pytorch.org/whl/cpu; $PY -m pip install -q numpy scikit-learn transformers tokenizers sentencepiece protobuf huggingface_hub pyyaml pyarrow onnx onnxruntime==1.31.1 pytest
aws s3 cp --only-show-errors $CHISPA_S3/codigo.tgz $BASE/codigo.tgz && tar xzf $BASE/codigo.tgz -C $REPO
cd $REPO; export GOFLAGS=-mod=mod GOTOOLCHAIN=local GONOSUMDB='github.com/juan52878911/*' GOPROXY=file://$REPO/gomod-proxy,https://proxy.golang.org CGO_ENABLED=1
echo "== commit"; cat $REPO/COMMIT 2>/dev/null
$PY - <<'P'
from huggingface_hub import snapshot_download as s; print(s("intfloat/multilingual-e5-small", allow_patterns=["*.json","*.model","*.txt"]))
P
E5=$(ls -d $HOME/.cache/huggingface/hub/models--intfloat--multilingual-e5-small/snapshots/* | head -1)
$PY $REPO/runtime/tok/exportar.py "$E5" /tmp/e5.chispa-tok > $RES/tok-export.log 2>&1 || echo "export tok falló"
export CHISPA_TOK=/tmp/e5.chispa-tok; ls -la $CHISPA_TOK
suite gofmt bash -c 'l=$(gofmt -l server format runtime sdk/go sdk/movil 2>&1); echo "$l"; [ -z "$l" ]'
for d in server format/chispa3 runtime/l1 runtime/tok runtime/torre sdk/go; do n=$(echo $d | tr / _)
  suite vet_$n bash -c "cd $REPO/$d && go vet ./..."
  suite race_$n bash -c "cd $REPO/$d && go test -race -count=1 -v ./..."
done
suite ort_server bash -c "cd $REPO/server && go get github.com/yalue/onnxruntime_go@latest && CHISPA_ORT_LIB=$ORTLIB go test -tags ort -count=1 -v ./..."
suite python_sdk bash -c "cd $REPO/sdk/python && $PY -m pytest -q tests 2>&1 || $PY -m unittest discover -s tests -v"
unset LD_LIBRARY_PATH
suite e2e bash -c "cd $REPO && PATH=$BASE/venv/bin:\$PATH PYTHON=$PY CHISPA_ORT_LIB=$ORTLIB CHISPA_TOK=/tmp/e5.chispa-tok bash server/e2e/correr.sh"
echo "== resumen"; cat $RES/resumen.tsv
