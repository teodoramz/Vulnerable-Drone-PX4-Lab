import pytest

from app.ring_buffer import RingBuffer


def test_append_and_len():
    rb: RingBuffer[int] = RingBuffer(capacity=3)
    assert len(rb) == 0
    rb.append(1)
    rb.append(2)
    assert len(rb) == 2
    assert rb.all() == [1, 2]


def test_eviction_is_fifo_oldest_first():
    rb: RingBuffer[int] = RingBuffer(capacity=3)
    for i in range(1, 6):  # 1..5, capacity 3 -> only 3,4,5 survive
        rb.append(i)
    assert len(rb) == 3
    assert rb.all() == [3, 4, 5]


def test_recent_returns_last_n_oldest_first_order():
    rb: RingBuffer[int] = RingBuffer(capacity=10)
    for i in range(1, 8):
        rb.append(i)
    assert rb.recent(3) == [5, 6, 7]
    assert rb.recent(100) == [1, 2, 3, 4, 5, 6, 7]
    assert rb.recent(0) == []


def test_recent_with_predicate_filters_before_limiting():
    rb: RingBuffer[int] = RingBuffer(capacity=10)
    for i in range(1, 11):
        rb.append(i)
    evens = rb.recent(2, predicate=lambda x: x % 2 == 0)
    assert evens == [8, 10]


def test_capacity_must_be_positive():
    with pytest.raises(ValueError):
        RingBuffer(capacity=0)
    with pytest.raises(ValueError):
        RingBuffer(capacity=-1)
