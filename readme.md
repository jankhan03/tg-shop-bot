для локального запуска:

cd tg-shop-bot 
source .venv/bin/activate

запуск сервера:

1.1) uvicorn server.main:app --reload --port 8000

в новом окне:

2.1) cd tg-shop-bot 
2.2) source .venv/bin/activate
2.3) cloudflared tunnel --url http://localhost:8000
    поменять ссылку в .env 

в новом окне:

3.1) cd tg-shop-bot 
3.2) source .venv/bin/activate
3.3) python -m bot.bot