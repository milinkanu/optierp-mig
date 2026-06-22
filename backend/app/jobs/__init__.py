"""Background jobs run by the APScheduler registry (``app.core.scheduler``).

Each job function takes no request context: it opens its own session and resolves
the company/actor it needs. Registered by dotted path in ``SCHEDULED_JOBS``.
"""
