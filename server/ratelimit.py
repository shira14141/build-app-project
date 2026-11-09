"""הגנה מניחוש סיסמאות: אחרי X ניסיונות כושלים לאותו שם משתמש - נעילה זמנית.

נשמר בזיכרון של התהליך: מתאפס בהפעלה מחדש, ומתאים לשרת עם תהליך אחד (כמו כאן).
בהרצה עם כמה תהליכים/שרתים צריך להעביר את זה ל-Redis או למסד.
"""
import threading
import time
from collections import defaultdict, deque

from server.config import LOGIN_LOCKOUT_MINUTES, MAX_LOGIN_FAILURES


class LoginLimiter:
    def __init__(self, max_failures=MAX_LOGIN_FAILURES, window_seconds=LOGIN_LOCKOUT_MINUTES * 60):
        self.max_failures = max_failures
        self.window = window_seconds
        self._failures = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, key, now):
        attempts = self._failures[key]
        while attempts and now - attempts[0] > self.window:
            attempts.popleft()
        return attempts

    def retry_after(self, key):
        """כמה שניות נשארו לנעילה (0 = לא נעול)."""
        now = time.monotonic()
        with self._lock:
            attempts = self._prune(key, now)
            if len(attempts) < self.max_failures:
                return 0
            return int(self.window - (now - attempts[0])) + 1

    def record_failure(self, key):
        now = time.monotonic()
        with self._lock:
            self._prune(key, now).append(now)

    def reset(self, key):
        with self._lock:
            self._failures.pop(key, None)


login_limiter = LoginLimiter()
