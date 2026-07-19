''' tests for the main window and its status panel.

	The status widgets (ExecutionPanel, MultiRing, Ring) are GL-free and use `fake_app`.
	The full MainWindow always builds a SceneView through its layout preset, so those tests
	need an OpenGL context and are marked `gl`. '''
import pytest
from madcad.qt import Qt, QColor

from uimadcad.mainwindow import ExecutionPanel, MultiRing, Ring
from uimadcad.utils import Action


def make_exception():
	try:
		raise RuntimeError('kaboom')
	except RuntimeError as err:
		return err


# --- status panel (GL-free) -----------------------------------------------------------

@pytest.fixture
def panel_app(fake_app):
	# ExecutionPanel wires a stop button from app.stop; provide a stand-in action
	fake_app.stop = Action(lambda: None, name='stop')
	return fake_app

@pytest.fixture
def panel(qtbot, panel_app):
	p = ExecutionPanel(panel_app)
	qtbot.addWidget(p)
	return p

def test_panel_registers_errorview_as_active(panel, panel_app):
	assert panel_app.active.errorview is panel.errorview

def test_panel_set_success(panel):
	panel.set_success()
	assert 'succeed' in panel.status.text()
	assert not panel.stop.isEnabled()

def test_panel_set_progress(panel):
	panel.set_progress({'main': 0.5})
	assert '50%' in panel.status.text()
	assert panel.stop.isEnabled()

def test_panel_set_exception(panel):
	panel.set_exception(make_exception())
	assert panel.errorview.exception is not None
	assert panel.ring.color == QColor(255, 0, 0)


# --- progress rings (GL-free, exercised through grab()) -------------------------------

def test_multiring_paints(qtbot):
	ring = MultiRing(120)
	qtbot.addWidget(ring)
	ring.progress = [0.3, 0.7]
	ring.progressing = True
	ring.resize(120, 120)
	assert not ring.grab().isNull()  # grab() runs paintEvent

def test_ring_paints(qtbot):
	ring = Ring(120)
	qtbot.addWidget(ring)
	ring.progress = 0.4
	ring.progressing = True
	ring.resize(120, 120)
	assert not ring.grab().isNull()


# --- full main window (needs OpenGL) --------------------------------------------------

@pytest.mark.gl
def test_default_layout_has_scene_and_script(madcad_app):
	from uimadcad.mainwindow import DockedView
	docks = madcad_app.window.findChildren(DockedView)
	assert len(docks) >= 2

@pytest.mark.gl
def test_layout_minimal(madcad_app):
	from uimadcad.mainwindow import DockedView
	from uimadcad.sceneview import SceneView
	window = madcad_app.window
	window.layout_minimal.trigger()
	# _layout_clear() only removes the previous docks (removeDockWidget keeps them as
	# children but detaches them), so count the ones still attached to a dock area
	docked = [d for d in window.findChildren(DockedView)
		if window.dockWidgetArea(d) != Qt.NoDockWidgetArea]
	assert len(docked) == 1
	assert isinstance(docked[0].widget(), SceneView)

@pytest.mark.gl
def test_new_scriptview_adds_dock(madcad_app):
	from uimadcad.mainwindow import DockedView
	window = madcad_app.window
	before = len(window.findChildren(DockedView))
	window.new_scriptview.trigger()
	assert len(window.findChildren(DockedView)) == before + 1

@pytest.mark.gl
def test_open_panel_toggle(madcad_app):
	window = madcad_app.window
	window.open_panel.setChecked(True)
	assert not window.panel.isHidden()
	window.open_panel.setChecked(False)
	assert window.panel.isHidden()
