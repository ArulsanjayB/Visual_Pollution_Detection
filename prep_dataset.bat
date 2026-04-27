@echo off
REM ═══════════════════════════════════════════════════════════════
REM  Prepare the dataset: augment minority classes + train/val/test split
REM  Place combined_dataset_final.zip in the project root first.
REM ═══════════════════════════════════════════════════════════════

cd /d "%~dp0"

if not exist venv\Scripts\activate.bat (
    echo [ERROR] venv not found. Run setup.bat first.
    pause & exit /b 1
)

if not exist combined_dataset_final.zip (
    echo [ERROR] combined_dataset_final.zip not found in project root.
    echo         Place your dataset zip here:
    echo            %CD%\combined_dataset_final.zip
    pause & exit /b 1
)

call venv\Scripts\activate.bat

echo.
echo ============================================================
echo   Preparing dataset (this takes 3-5 minutes)
echo   - Unzipping raw images
echo   - Augmenting minority classes (vehicles, debris)
echo   - Train/Val/Test split (70/20/10)
echo ============================================================
echo.

cd ml
python data_prep.py --zip_path ..\combined_dataset_final.zip --output_dir ..\dataset

echo.
echo ============================================================
echo Dataset ready at: dataset\yolo_dataset\
echo Next: train.bat
echo ============================================================
pause
