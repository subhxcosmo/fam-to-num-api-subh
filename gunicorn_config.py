# Gunicorn config for Render
bind = "0.0.0.0:10000"
workers = 1
worker_class = "sync"
threads = 1
timeout = 120
keepalive = 2
accesslog = "-"
errorlog = "-"
loglevel = "info"
