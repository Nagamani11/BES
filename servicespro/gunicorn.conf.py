import os
import multiprocessing

# Server Socket
bind = f"0.0.0.0:{os.getenv('PORT', '8000')}"
backlog = 2048

# Worker Processes
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "sync"
timeout = 60  # Increased from default 30s
keepalive = 2
threads = 4 if worker_class == "gthread" else 1

# Logging
accesslog = "-"  # Stdout
errorlog = "-"   # Stderr
loglevel = "info"
capture_output = True

# Security
limit_request_line = 4094
limit_request_fields = 100
limit_request_field_size = 8190

# Debugging
reload = False
preload_app = True

# Worker Hooks


def worker_int(worker):
    worker.log.warning("Worker received INT/QUIT signal")


def worker_abort(worker):
    worker.log.critical("Worker received ABRT signal")
