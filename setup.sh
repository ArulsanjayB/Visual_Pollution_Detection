#!/bin/bash
# CivicLens — Linux/macOS setup (local GPU training on Linux with NVIDIA)
set -e

echo ""
echo "============================================================"
echo "  CivicLens Backend Setup (Linux/macOS)"
echo "============================================================"
echo ""

PYTHON=""
for p in python3.11 python3.12 python3.10 python3; do
    if command -v $p >/dev/null 2>&1; then
        VER=$($p --version 2>&1 | grep -oE "3\.[0-9]+")
        if [[ "$VER" =~ ^3\.(10|11|12)$ ]]; then
            PYTHON=$p; break
        fi
    fi
done
if [ -z "$PYTHON" ]; then
    echo "[ERROR] Python 3.10/3.11/3.12 required. Found: $(python3 --version 2>&1 || echo none)"
    exit 1
fi
echo "[1/6] Using $PYTHON ($($PYTHON --version 2>&1))"

if [ -d venv ]; then
    echo "[2/6] venv exists — skipping"
else
    echo "[2/6] Creating venv ..."
    $PYTHON -m venv venv
fi

echo "[3/6] Activating venv ..."
source venv/bin/activate

echo "[4/6] Upgrading pip ..."
pip install --upgrade pip wheel setuptools >/dev/null

echo "[5/6] Installing PyTorch ..."
if command -v nvidia-smi >/dev/null 2>&1; then
    echo "       NVIDIA GPU detected — installing CUDA 12.1 build"
    pip install torch==2.2.2 torchvision==0.17.2 --index-url https://download.pytorch.org/whl/cu121
else
    echo "       No GPU — installing CPU-only build"
    pip install torch==2.2.2 torchvision==0.17.2 --index-url https://download.pytorch.org/whl/cpu
fi

echo "[6/6] Installing backend + ML deps ..."
pip install -r backend/requirements.txt
pip install -r ml/requirements.txt

[ -f backend/.env ] || cp backend/.env.example backend/.env

echo ""
echo "GPU verification:"
python -c "import torch; print('  PyTorch:', torch.__version__); print('  CUDA:', torch.cuda.is_available()); print('  GPU:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'none')"

echo ""
echo "Setup complete. Next:  ./prep_dataset.sh  ./train.sh  ./run_backend.sh"
