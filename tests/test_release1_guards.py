import asyncio

from data_quality import QualityState, quality
from memory_guard import pressured
from task_supervisor import TaskSupervisor


def test_data_quality_transitions():
    assert quality(100, 95, 10, 30, 'x').state is QualityState.FRESH
    assert quality(100, 80, 10, 30, 'x').state is QualityState.STALE
    assert quality(100, None, 10, 30, 'x', 'timeout').state is QualityState.FAILED


def test_memory_guard_is_safe_without_cgroup():
    assert isinstance(pressured(), bool)


def test_task_supervisor_collects_and_cancels():
    async def run():
        sup = TaskSupervisor('test')
        gate = asyncio.Event()
        sup.create(gate.wait(), 'waiter')
        assert len(sup.tasks) == 1
        await sup.cancel(timeout=1)
        assert not sup.tasks
    asyncio.run(run())
