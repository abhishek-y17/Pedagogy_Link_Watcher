"""_try_switch_to_english: flip the KEA ASP.NET language dropdown to English."""

from neet_pipeline.monitor.headless import _try_switch_to_english


class FakePage:
    def __init__(self, has_english_option=True, current="K", select_raises=False):
        self._has_opt = has_english_option
        self._value = current
        self._select_raises = select_raises
        self.selected = None
        self.waited = False

    def query_selector(self, sel):
        if sel == "#ddlLanguage option[value='E']":
            return object() if self._has_opt else None
        return None

    def eval_on_selector(self, sel, _js):
        return self._value

    def select_option(self, sel, value):
        if self._select_raises:
            raise RuntimeError("detached")
        self.selected = value
        self._value = value

    def wait_for_function(self, _js, timeout=None):
        self.waited = True

    def wait_for_timeout(self, _ms):
        pass

    def wait_for_load_state(self, state, timeout=None):
        self.waited = True


def test_switches_when_dropdown_present_and_on_kannada():
    page = FakePage(current="K")
    _try_switch_to_english(page, 30000)
    assert page.selected == "E"
    assert page.waited is True


def test_noop_when_already_english():
    page = FakePage(current="E")
    _try_switch_to_english(page, 30000)
    assert page.selected is None
    assert page.waited is False


def test_noop_when_no_language_dropdown():
    page = FakePage(has_english_option=False)
    _try_switch_to_english(page, 30000)
    assert page.selected is None


def test_swallows_errors():
    page = FakePage(select_raises=True)
    _try_switch_to_english(page, 30000)  # must not raise
