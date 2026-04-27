@echo off
REM ═══════════════════════════════════════════════════════════════
REM  Train YOLOv8 on your local NVIDIA GPU
REM  Prerequisite: setup.bat, then prep_dataset.bat
REM ═══════════════════════════════════════════════════════════════

cd /d "%~dp0"

if not exist venv\Scripts\activate.bat (
    echo [ERROR] venv not found. Run setup.bat first.
    pause & exit /b 1
)

if not exist dataset\yolo_dataset\dataset.yaml (
    echo [ERROR] dataset.yaml not found.
    echo         Run prep_dataset.bat first.
    pause & exit /b 1
)

call venv\Scripts\activate.bat

REM Safety check: verify numpy is 1.x before training
python -c "import numpy; assert numpy.__version__.startswith('1.'), 'bad numpy'" 2>nul
if errorlevel 1 (
    echo [WARN] NumPy 2.x detected - reinstalling 1.26.4 before training ...
    pip install "numpy==1.26.4" --force-reinstall --no-deps >nul
)

echo.
echo ============================================================
echo   Training YOLOv8 on local GPU
echo   Default: yolov8s, 60 epochs, auto batch size
echo.
echo   For a faster run on 6GB laptop GPUs, use yolov8n:
echo     cd ml
echo     ..\venv\Scripts\python.exe train.py --model yolov8n --epochs 60
echo ============================================================
echo.

cd ml
python train.py --data ..\dataset\yolo_dataset\dataset.yaml --model yolov8s --epochs 60

REM Check if training actually succeeded
if errorlevel 1 (
    cd ..
    echo.
    echo ============================================================
    echo   [ERROR] Training failed. See output above for details.
    echo ============================================================
    pause
    exit /b 1
)
cd ..

if not exist ml\runs\visual_pollution_v1\weights\best.pt (
    echo.
    echo ============================================================
    echo   [ERROR] best.pt was not produced. Training likely failed.
    echo ============================================================
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   Training complete!
echo ============================================================
echo Weights saved to: ml\runs\visual_pollution_v1\weights\best.pt
echo.
echo The backend auto-loads this file on startup.
echo Next: run_backend.bat
echo ============================================================
pause
