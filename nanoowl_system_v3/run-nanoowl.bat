@echo off
setlocal

REM --- PATHS ---
set "PROJECT=C:\Users\Kelton\nanoowl_system_v3\nanoowl_v3_fixed"
set "CONDA=C:\Users\Kelton\miniforge3"
set "ENV=ryzen-ai-1.7.0"

REM --- Activate conda ---
call "%CONDA%\Scripts\activate.bat"
call conda activate %ENV%

cd /d "%PROJECT%"

REM --- Launch each service in its own window ---
start "NanoOWL - Camera0" cmd /k "call conda activate %ENV% && python jetson\camera_worker.py --camera-id 0"
start "NanoOWL - Detect" cmd /k "call conda activate %ENV% && python jetson\detection_worker.py"
start "NanoOWL - Web"    cmd /k "call conda activate %ENV% && python pi_server.py"

echo.
echo NanoOWL launched from: %PROJECT%
echo Close each window to stop, or make a stop script.
pause