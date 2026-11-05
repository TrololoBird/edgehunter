import asyncio

from data_quality import QualityState, quality
from memory_guard import pressured
from task_supervisor import TaskSupervisor
from signal_priority import SignalBatcher
from tools.replay_acceptance import holm_bonferroni


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


def test_signal_batcher_orders_after_window():
    b = SignalBatcher(window_ms=0)
    out = b.add([('slow', {'p_edge': 0.1}), ('strong', {'p_edge': 0.9})])
    assert [x[0] for x in out] == ['strong', 'slow']


def test_holm_correction_is_step_down():
    assert holm_bonferroni([0.001, 0.02, 0.8]) == [0.003, 0.04, 0.8]
