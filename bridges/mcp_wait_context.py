"""Per-request cancellation/budget for stdio waits, without task side effects."""
from contextvars import ContextVar
from dataclasses import dataclass, field
import threading
import time


class WaitCancelled(RuntimeError):
    pass


class WaitBudgetExpired(RuntimeError):
    pass


@dataclass
class WaitContext:
    cancelled: threading.Event = field(default_factory=threading.Event)
    http_timeout_seconds: float = 5.0
    deadline: float | None = None

    def limit(self, seconds):
        deadline=time.monotonic()+max(0,seconds)
        self.deadline=min(self.deadline,deadline) if self.deadline is not None else deadline

    def check(self):
        if self.cancelled.is_set():
            raise WaitCancelled('客户端取消了读等待；执行者任务未取消')
        if self.deadline is not None and time.monotonic()>=self.deadline:
            raise WaitBudgetExpired('single follow-up request budget expired')

    def sleep(self, seconds):
        self.check()
        if self.deadline is not None:seconds=min(seconds,max(0,self.deadline-time.monotonic()))
        if self.cancelled.wait(max(0.0, seconds)):
            self.check()


CURRENT_WAIT: ContextVar[WaitContext | None] = ContextVar('talk_mcp_wait', default=None)


def check_cancelled():
    current = CURRENT_WAIT.get()
    if current is not None:
        current.check()


def http_timeout(value):
    current = CURRENT_WAIT.get()
    if current is not None:
        current.check()
        remaining=current.deadline-time.monotonic() if current.deadline is not None else float('inf')
        return min(value, current.http_timeout_seconds, max(.001,remaining))
    return value


def wait_sleep(seconds, fallback=time.sleep):
    current = CURRENT_WAIT.get()
    if current is not None:
        current.sleep(seconds)
    else:
        fallback(seconds)
