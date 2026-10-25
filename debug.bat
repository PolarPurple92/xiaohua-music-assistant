@echo off
rem Same as run.bat but keeps the console window for troubleshooting.
setlocal
set "ROOT=%~dp0"
set "PY=%ROOT%python\python.exe"
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

title XiaoHua MIDI - debug console
"%PY%" "%ROOT%app\interface.py" %*
set "RC=%ERRORLEVEL%"
echo.
echo [exit code %RC%]  log: %XIAOHUA_LOG%
pause
endlocal
