@echo off
IF NOT EXIST .env (
    echo Copy .env.example to .env and set your TELEGRAM_BOT_TOKEN first.
    exit /b 1
)
pip install -r requirements.txt
python main.py
pause
