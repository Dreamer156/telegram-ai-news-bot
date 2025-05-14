@echo off
TITLE Telegram AI News Poster Bot Runner
SETLOCAL

REM --- Конфигурация ---
SET VENV_DIR=venv
SET PYTHON_EXE=python
SET REQUIREMENTS_FILE=requirements.txt
SET BOT_SCRIPT=app/bot.py

echo.
echo CHECKPOINT 1: Starting Telegram AI News Poster Bot setup...
echo.

REM --- Проверка наличия Python ---
echo CHECKPOINT 2: Checking for Python...
REM Показываем вывод команды python --version
echo Trying to run: %PYTHON_EXE% --version
%PYTHON_EXE% --version
IF ERRORLEVEL 1 (
    echo Error: Python command [%PYTHON_EXE%] failed or Python is not found/not added to PATH.
    echo Please install Python (3.7+) and ensure it's in your system PATH.
    pause
    EXIT /B 1
)
echo Python found.

REM --- Создание/проверка виртуального окружения ---
echo CHECKPOINT 3: Checking/Creating virtual environment in .\%VENV_DIR% ...
IF NOT EXIST "%VENV_DIR%\Scripts\activate.bat" (
    echo Virtual environment not found.
    echo Creating virtual environment...
    %PYTHON_EXE% -m venv %VENV_DIR%
    IF ERRORLEVEL 1 (
        echo Error: Failed to create virtual environment.
        echo Please check your Python installation and permissions.
        pause
        EXIT /B 1
    )
    echo Virtual environment created successfully.
) ELSE (
    echo Virtual environment found.
)

REM --- Активация виртуального окружения ---
echo CHECKPOINT 4: Activating virtual environment...
CALL "%VENV_DIR%\Scripts\activate.bat"
IF ERRORLEVEL 1 (
    echo Error: Failed to activate virtual environment.
    pause
    EXIT /B 1
)
echo Virtual environment activated.

REM --- Установка/обновление зависимостей ---
echo CHECKPOINT 5: Checking/Installing dependencies from %REQUIREMENTS_FILE%...
IF NOT EXIST "%REQUIREMENTS_FILE%" (
    echo Error: %REQUIREMENTS_FILE% not found!
    pause
    EXIT /B 1
)
REM Следующая команда может выводить много текста
pip install -r %REQUIREMENTS_FILE%
IF ERRORLEVEL 1 (
    echo Error: Failed to install dependencies.
    echo Please check %REQUIREMENTS_FILE% and your internet connection.
    pause
    EXIT /B 1
)
echo Dependencies are up to date.

REM --- Запуск бота ---
echo CHECKPOINT 6: Preparing to start the bot script %BOT_SCRIPT%...
IF NOT EXIST "%BOT_SCRIPT%" (
    echo Error: Bot script %BOT_SCRIPT% not found!
    pause
    EXIT /B 1
)
echo.
echo Starting the Telegram bot (%BOT_SCRIPT%)...
echo Press Ctrl+C in this window to stop the bot.
%PYTHON_EXE% %BOT_SCRIPT%
REM Если Python скрипт упадет, батник дойдет сюда

echo.
echo CHECKPOINT 7: Bot script has finished or was stopped.
ENDLOCAL
echo Script execution finished. Press any key to exit...
pause 