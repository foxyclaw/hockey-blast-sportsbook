import os
port = int(os.environ.get("PORT", 5002))
bind = f"127.0.0.1:{port}"
workers = 4
threads = 2
timeout = 120
accesslog = "-"
errorlog = "-"
loglevel = "info"
preload_app = True  # load app in master before forking — required for APScheduler

def post_fork(server, worker):
    """Shut down the scheduler in worker processes — it only runs in the master."""
    try:
        from app.jobs.grade_results import _scheduler
        if _scheduler is not None and _scheduler.running:
            _scheduler.shutdown(wait=False)
    except Exception:
        pass
