# single worker + threads: NO multi-process because supervisor must be single-instance
bind = "127.0.0.1:8000"
workers = 1
threads = 8
worker_class = "gthread"
timeout = 120
accesslog = "-"
errorlog = "-"