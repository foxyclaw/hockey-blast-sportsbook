import os
port = int(os.environ.get("PORT", 5002))
bind = f"127.0.0.1:{port}"
workers = 4
threads = 2
timeout = 120
accesslog = "-"
errorlog = "-"
loglevel = "info"
# Scheduler runs in each worker independently (simpler than preload_app + post_fork).
# APScheduler with IntervalTrigger is idempotent — multiple workers checking is fine.
workers = 1  # single worker to avoid duplicate scheduler jobs
