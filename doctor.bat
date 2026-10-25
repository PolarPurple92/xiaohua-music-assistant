@echo off
setlocal
set "ROOT=%~dp0"
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
if exist "%ROOT%vendor\Audiveris\Audiveris.exe" set "XIAOHUA_AUDIVERIS=%ROOT%vendor\Audiveris\Audiveris.exe"

title XiaoHua MIDI - doctor
"%ROOT%python\python.exe" "%ROOT%doctor.py"
echo.
pause
endlocal
