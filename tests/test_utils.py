''' tests for uimadcad.utils: conversions, small helpers, the decorator machinery that
	turns methods into toolbar actions/buttons, and the Qt-thread task queue. '''
import threading

import pytest
from madcad.mathutils import vec3, vec4
from madcad.qt import QObject, QColor, QSize, QFont, QPalette, QWidget, QBoxLayout, QDockWidget, QSplitter

from uimadcad import utils
from uimadcad.utils import (
	qcolor_to_vec, vec_to_qcolor, qsize_to_vec, vec_to_qsize, mix_qcolor,
	dedent, singleton, catchtime, charformat, palette_simple,
	action, button, Initializer, Action, Button,
	vlayout, hlayout, boxlayout, spacer, widget, dock, Splitter,
	qtschedule, qtinvoke,
	)


# --- conversions ----------------------------------------------------------------------

def test_qcolor_vec_roundtrip():
	color = QColor(255, 128, 0, 255)
	v = qcolor_to_vec(color)
	assert v.x == pytest.approx(1.0)
	assert v.y == pytest.approx(128/255)
	assert v.z == pytest.approx(0.0)
	assert v.w == pytest.approx(1.0)
	back = vec_to_qcolor(v)
	assert (back.red(), back.green(), back.blue(), back.alpha()) == (255, 128, 0, 255)

def test_vec_to_qcolor_from_vec3_adds_alpha():
	back = vec_to_qcolor(vec3(1, 0, 0))
	assert (back.red(), back.green(), back.blue(), back.alpha()) == (255, 0, 0, 255)

def test_qsize_vec_roundtrip():
	size = QSize(30, 40)
	v = qsize_to_vec(size)
	assert (v.x, v.y) == (30, 40)
	back = vec_to_qsize(v)
	assert (back.width(), back.height()) == (30, 40)

def test_mix_qcolor():
	mid = mix_qcolor(QColor(0, 0, 0), QColor(100, 200, 40), 0.5)
	assert (mid.red(), mid.green(), mid.blue()) == (50, 100, 20)


# --- small helpers --------------------------------------------------------------------

def test_dedent_removes_common_indentation():
	text = "\n    line1\n    line2\n"
	assert dedent(text) == "line1\nline2"

def test_singleton_runs_once():
	calls = []
	@singleton
	def compute():
		calls.append(1)
		return 42
	assert compute() == 42
	assert compute() == 42
	assert len(calls) == 1

def test_catchtime_accumulates():
	ticks = iter([10.0, 13.5])
	chrono = catchtime(time=lambda: next(ticks))
	with chrono:
		pass
	assert chrono() == pytest.approx(3.5)


# --- Qt helpers -----------------------------------------------------------------------

def test_charformat_sets_attributes(qapp):
	fmt = charformat(italic=True, weight=QFont.Bold, foreground=QColor(255, 0, 0))
	assert fmt.fontItalic() is True
	assert fmt.fontWeight() == QFont.Bold
	assert fmt.foreground().color().red() == 255

def test_palette_simple_builds_palette(qapp):
	palette = palette_simple(base=vec3(0), text=vec3(1))
	assert isinstance(palette, QPalette)
	# window background maps to base (black), window text to ~text (white)
	assert palette.color(QPalette.Window).red() == 0
	assert palette.color(QPalette.WindowText).red() > 200


# --- layout builders ------------------------------------------------------------------

def test_layout_builders(qapp):
	a, b = QWidget(), QWidget()
	v = vlayout([a, b])
	assert isinstance(v, QBoxLayout)
	assert v.direction() == QBoxLayout.TopToBottom
	assert v.count() == 2
	assert hlayout([QWidget()]).direction() == QBoxLayout.LeftToRight

def test_layout_margins_and_spacing(qapp):
	layout = boxlayout([QWidget()], spacing=7, margins=3)
	assert layout.spacing() == 7
	assert layout.contentsMargins().left() == 3

def test_spacer_and_widget(qapp):
	sp = spacer(12, 5)
	assert sp.minimumWidth() == 12 and sp.minimumHeight() == 5
	w = widget(vlayout([QWidget()]))
	assert isinstance(w, QWidget) and w.layout() is not None

def test_dock_and_splitter(qapp):
	d = dock(QWidget(), 'title')
	assert isinstance(d, QDockWidget)
	assert d.windowTitle() == 'title'
	s = Splitter([QWidget(), QWidget()])
	assert isinstance(s, QSplitter) and s.count() == 2


# --- decorator machinery (@action / @button + Initializer) ----------------------------

class DecoratedHolder(QObject):
	''' minimal object exercising the action/button decorators like the real widgets do '''
	def __init__(self):
		super().__init__()
		self.triggered_count = 0
		self.toggle_state = None
		Initializer.process(self)

	@action(shortcut='Ctrl+T')
	def do_thing(self):
		''' does the thing '''
		self.triggered_count += 1

	@button(checked=False)
	def toggle_thing(self, state):
		''' toggles the thing '''
		self.toggle_state = state


def test_action_built_from_method(qapp):
	holder = DecoratedHolder()
	assert isinstance(holder.do_thing, Action)
	# name derived from the method name, description from the docstring
	assert holder.do_thing.text() == 'do thing'
	assert 'does the thing' in holder.do_thing.toolTip()
	assert holder.do_thing.shortcut().toString() == 'Ctrl+T'
	assert holder.do_thing.isCheckable() is False

def test_action_trigger_calls_method(qapp):
	holder = DecoratedHolder()
	holder.do_thing.trigger()
	holder.do_thing.trigger()
	assert holder.triggered_count == 2

def test_button_checked_is_checkable_and_toggles(qapp):
	holder = DecoratedHolder()
	assert isinstance(holder.toggle_thing, Button)
	assert holder.toggle_thing.isCheckable() is True
	holder.toggle_thing.setChecked(True)
	assert holder.toggle_thing.isChecked() is True
	assert holder.toggle_state is True


# --- Qt-thread task queue -------------------------------------------------------------

def test_qtschedule_appends_and_runs(qapp):
	utils.qttasks.clear()
	ran = []
	qtschedule(lambda: ran.append('done'))
	assert len(utils.qttasks) == 1
	# drain the queue the same way qtmain's timer would
	while utils.qttasks:
		utils.qttasks.popleft()()
	assert ran == ['done']

def test_qtinvoke_marshals_and_returns(qapp, qtbot):
	''' qtinvoke is meant to be called from a worker thread; it blocks until the callback
		runs on the Qt thread and returns its value. Here the main thread plays the role of
		the Qt loop by draining the task queue. '''
	utils.qttasks.clear()
	result = {}
	def worker():
		result['value'] = qtinvoke(lambda: 6 * 7)
	thread = threading.Thread(target=worker)
	thread.start()

	def pump():
		while utils.qttasks:
			utils.qttasks.popleft()()
		return not thread.is_alive()
	qtbot.waitUntil(pump, timeout=3000)
	thread.join(1)
	assert result['value'] == 42
