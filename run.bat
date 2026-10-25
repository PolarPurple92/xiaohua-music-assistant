@echo off
rem XiaoHua MIDI Player (modernised) - portable launcher
rem Logs: .\logs\app.log     Diagnostics: run doctor.bat
setlocal
set "ROOT=%~dp0"
set "PY=%ROOT%python\pythonw.exe"
if not exist "%PY%" set "PY=%ROOT%python\python.exe"

if not exist "%ROOT%lib\ttkbootstrap" (
  echo [ERROR] lib folder is missing or incomplete.
  echo         Re-copy the whole folder, or rebuild with build_portable.py
  pause
  exit /b 1
)

set "PYTHONPATH=%ROOT%app;%ROOT%lib"
set "PATH=%ROOT%lib;%ROOT%python;%ROOT%vendor\Audiveris;%PATH%"

set "DATA=%ROOT%data"
if not exist "%DATA%" mkdir "%DATA%"
if not exist "%DATA%\soundfonts" mkdir "%DATA%\soundfonts"
rem 自带的音色库不复制，直接通过 XIAOHUA_SOUNDFONTS_EXTRA 只读扫描（省一份体积）

set "XIAOHUA_SCREENSHOTS=%DATA%\screenshots"
set "XIAOHUA_XML=%DATA%\xml_outputs"
set "XIAOHUA_MIDI=%DATA%\midi_outputs"
set "XIAOHUA_SHEETS=%DATA%\sheet_images"
set "XIAOHUA_SOUNDFONTS=%DATA%\soundfonts"
set "XIAOHUA_SOUNDFONTS_EXTRA=%ROOT%vendor\soundfonts"
set "XIAOHUA_PREPROCESSED=%DATA%\preprocessed"
set "XIAOHUA_HOMR_WORK=%DATA%\homr_work"
set "XIAOHUA_STAGING=%DATA%\staging"
set "XIAOHUA_BRIEF=%DATA%\briefs"
set "XIAOHUA_AUDIVERIS_TEMP=%DATA%\temp_audiveris"
set "XIAOHUA_CONFIG=%DATA%\config.json"
set "XIAOHUA_LOG=%ROOT%logs\app.log"
if exist "%ROOT%vendor\Audiveris\Audiveris.exe" set "XIAOHUA_AUDIVERIS=%ROOT%vendor\Audiveris\Audiveris.exe"

start "" "%PY%" "%ROOT%app\interface.py" %*
endlocal
