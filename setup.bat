@echo off
REM ═══════════════════════════════════════════════════════════════
REM  CivicLens — Windows setup (local GPU training)
REM  Idempotent: safe to re-run; will fix broken installs.
REM ═══════════════════════════════════════════════════════════════

setlocal

echo.
echo ============================================================
echo   CivicLens Backend Setup (Windows)
echo ============================================================
echo.

REM ── Find a compatible Python (3.10, 3.11, or 3.12) ─────────
set "PY="

py -3.11 --version >nul 2>&1
if not errorlevel 1 ( set "PY=py -3.11" & goto :python_found )

py -3.12 --version >nul 2>&1
if not errorlevel 1 ( set "PY=py -3.12" & goto :python_found )

py -3.10 --version >nul 2>&1
if not errorlevel 1 ( set "PY=py -3.10" & goto :python_found )

for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo %PYVER% | findstr /r "^3\.1[012]\." >nul
if not errorlevel 1 ( set "PY=python" & goto :python_found )

echo.
echo [ERROR] Compatible Python not found (need 3.10, 3.11, or 3.12).
echo         Detected: %PYVER%
echo.
echo PyTorch does not publish wheels for Python 3.13 or 3.14 yet.
echo Install Python 3.11 from:
echo    https://www.python.org/downloads/release/python-3119/
echo During install, tick "Add Python 3.11 to PATH".
echo.
pause
exit /b 1

:python_found
for /f "tokens=*" %%v in ('%PY% --version 2^>^&1') do set PYVERFULL=%%v
echo [1/7] Using %PY%  ^(%PYVERFULL%^)

REM ── Create / reuse venv ─────────────────────────────────────
if exist venv (
    echo [2/7] venv already exists - will reuse.
) else (
    echo [2/7] Creating virtual environment ...
    %PY% -m venv venv
    if errorlevel 1 (
        echo [ERROR] Failed to create venv.
        pause & exit /b 1
    )
)

echo [3/7] Activating venv ...
call venv\Scripts\activate.bat

echo [4/7] Upgrading pip ...
python -m pip install --upgrade pip wheel setuptools >nul

REM ── PyTorch with CUDA 12.1 ─────────────────────────────────
REM Detect GPU
nvidia-smi >nul 2>&1
if errorlevel 1 (
    echo.
    echo [5/7] No NVIDIA GPU detected - installing CPU-only PyTorch
    echo        (training will be slow; inference still works^)
    pip install torch==2.2.2 torchvision==0.17.2 --index-url https://download.pytorch.org/whl/cpu --upgrade
) else (
    echo [5/7] NVIDIA GPU detected - installing PyTorch 2.2.2 with CUDA 12.1
    pip install torch==2.2.2 torchvision==0.17.2 --index-url https://download.pytorch.org/whl/cu121 --upgrade
)
if errorlevel 1 (
    echo [ERROR] PyTorch install failed.
    pause & exit /b 1
)

REM ── CRITICAL: Force numpy to 1.x BEFORE other packages ─────
REM PyTorch 2.2.2 was compiled against NumPy 1.x. If any other
REM package pulls in NumPy 2.x, training crashes with:
REM   "RuntimeError: Numpy is not available"
REM Pin it first, then --no-upgrade-strategy so later installs don't upgrade it.
echo [6/7] Pinning NumPy 1.26.4 (required by PyTorch) ...
pip uninstall -y numpy >nul 2>&1
pip install "numpy==1.26.4"
if errorlevel 1 (
    echo [ERROR] NumPy install failed.
    pause & exit /b 1
)

REM ── Rest of dependencies ───────────────────────────────────
echo [7/7] Installing backend + ML dependencies ...
pip install -r backend\requirements.txt --upgrade-strategy only-if-needed
if errorlevel 1 (
    echo [ERROR] Backend deps failed.
    pause & exit /b 1
)
pip install -r ml\requirements.txt --upgrade-strategy only-if-needed
if errorlevel 1 (
    echo [ERROR] ML deps failed.
    pause & exit /b 1
)

REM ── Re-pin numpy in case something bumped it ───────────────
pip install "numpy==1.26.4" --force-reinstall --no-deps >nul

REM ── Copy .env ──────────────────────────────────────────────
if not exist backend\.env (
    copy backend\.env.example backend\.env >nul
    echo       Created backend\.env
)

REM ── Verify CUDA + NumPy compat ─────────────────────────────
echo.
echo ============================================================
echo   Verifying setup
echo ============================================================
python -c "import numpy; print('NumPy:  ', numpy.__version__); assert numpy.__version__.startswith('1.'), 'NUMPY VERSION MISMATCH'; import torch; print('PyTorch:', torch.__version__); print('CUDA available:', torch.cuda.is_available()); print('GPU:    ', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'none'); print('CUDA:   ', torch.version.cuda); x = torch.from_numpy(numpy.zeros(4)); print('NumPy<->PyTorch bridge: OK')"
if errorlevel 1 (
    echo.
    echo [ERROR] Setup verification failed. See output above.
    pause & exit /b 1
)

echo.
echo ============================================================
echo   Setup complete!
echo ============================================================
echo.
echo Next steps:
echo   1. Prepare dataset:    prep_dataset.bat
echo   2. Train the model:    train.bat
echo   3. Run the backend:    run_backend.bat
echo   4. Open in browser:    http://localhost:8000/dashboard/
echo.
pause
