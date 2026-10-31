@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
if errorlevel 1 goto folder_error
py -3 -c "import sys; sys.exit(sys.version_info < (3,11))" >nul 2>&1
if errorlevel 1 goto try_python
py -3 start_review.py %*
goto finished
:try_python
python -c "import sys; sys.exit(sys.version_info < (3,11))" >nul 2>&1
if errorlevel 1 goto no_python
python start_review.py %*
goto finished
:no_python
echo Python 3.11+ was not found. Install it from https://www.python.org/downloads/
echo During installation enable "Add python.exe to PATH".
echo Then reopen this file. See OPEN-ME.txt for setup instructions.
pause
exit /b 1
:folder_error
echo Cannot open the review folder. Extract the ZIP to a local folder first.
echo See OPEN-ME.txt for instructions.
pause
exit /b 1
:finished
if not errorlevel 1 exit /b 0
echo.
echo Startup stopped. Read the message above and OPEN-ME.txt.
pause
exit /b 1
