# gunicorn.conf.py
worker_class = 'eventlet'
workers = 1 # Para o App Engine Standard, um worker por instância é geralmente o ideal.
bind = '0.0.0.0:8080' # Garante que o Gunicorn ouve na porta correta para o App Engine.
timeout = 120 # Aumenta o tempo limite para as ligações de longa duração do Socket.IO.