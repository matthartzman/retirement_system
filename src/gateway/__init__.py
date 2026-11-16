"""Multi-user gateway: accounts, mandatory two-factor login, sessions, CSRF, admin and audit.

Design: ``documentation/future/multi-user-server-gateway-design.md``. Phase 3 plugs the reverse
proxy to each user's worker into ``upstream.Upstream``.
"""
