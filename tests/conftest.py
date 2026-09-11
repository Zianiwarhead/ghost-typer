"""Mock keyboard so engine tests never press real keys."""
import core.engine as engine_mod


class DummyKeyboard:
    def __init__(self):
        self.typed = []
        self.pressed_keys = []

    def type(self, s):
        self.typed.append(s)

    def press(self, key):
        self.pressed_keys.append(("press", str(key)))

    def release(self, key):
        self.pressed_keys.append(("release", str(key)))

    def pressed(self, key):
        class _Ctx:
            def __enter__(self_inner):
                return None

            def __exit__(self_inner, *a):
                return False
        return _Ctx()


def patch_engine(monkeypatch):
    dummy = DummyKeyboard()
    monkeypatch.setattr(engine_mod, "Controller", lambda: dummy)
    return dummy
