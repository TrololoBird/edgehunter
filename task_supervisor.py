"""Common task ownership helper for long-lived asyncio components."""
import asyncio
import logging

log = logging.getLogger(__name__)


class TaskSupervisor:
    def __init__(self, owner: str):
        self.owner = owner
        self.tasks = set()

    def create(self, coro, name: str):
        task = asyncio.create_task(coro, name=f'{self.owner}:{name}')
        self.tasks.add(task)
        task.add_done_callback(self._done)
        return task

    def _done(self, task):
        self.tasks.discard(task)
        if task.cancelled():
            return
        try:
            exc = task.exception()
        except asyncio.CancelledError:
            return
        if exc:
            log.error('owned task failed owner=%s task=%s: %r', self.owner, task.get_name(), exc, exc_info=exc)

    async def cancel(self, timeout: float = 30.0):
        pending = list(self.tasks)
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.wait_for(asyncio.gather(*pending, return_exceptions=True), timeout=timeout)
