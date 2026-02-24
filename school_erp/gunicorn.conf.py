import multiprocessing

bind = "0.0.0.0:5000"
workers = max(2, multiprocessing.cpu_count() // 2)
threads = 4
timeout = 120
graceful_timeout = 30
keepalive = 5
accesslog = "-"
errorlog = "-"
worker_tmp_dir = "/dev/shm"
