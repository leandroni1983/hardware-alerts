#!/usr/bin/env python3
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from notifier import telegram_bot

env = telegram_bot.load_env('config/telegram.env')
print('Loaded env keys:', env.keys())
token = env.get('TELEGRAM_TOKEN')
chat = env.get('TELEGRAM_CHAT_ID')
print('Token present:', bool(token), 'Chat:', chat)
try:
    res = telegram_bot.send_message(token, str(chat), 'Prueba rápida: mensaje de test (sin markdown)')
    print('Send result:', res)
except Exception as e:
    print('Send failed:', type(e), e)
