from core.controller import SessionController


def test_soft_stop_keeps_resume():
    c = SessionController()
    c.save_session("hello world", {"name": "Normal"})
    c.update_index(5, 11)
    assert c.has_resume() is True
    info = c.get_resume_info()
    assert info["index"] == 5 and info["total"] == 11
    assert c.get_remaining_text() == " world"
    # Soft stop keeps it
    c.stop_session(soft=True)
    assert c.has_resume() is True
    # Hard stop clears it
    c.stop_session(soft=False)
    assert c.has_resume() is False


def test_no_resume_when_finished_or_empty():
    c = SessionController()
    assert c.has_resume() is False
    c.save_session("hi", {"name": "x"})
    c.update_index(2, 2)
    assert c.has_resume() is False
    c.update_index(0, 2)
    assert c.has_resume() is False


def test_mark_own_emit_does_not_crash():
    c = SessionController()
    c.mark_own_emit()
    c.mark_own_emit('q')
    c.mark_own_emit('key:backspace')
    assert len(c._own_emits) == 3
