''' tests for the 3d viewport (uimadcad.sceneview).

	The Scene/SceneView pull OpenGL through pymadcad's renderer, so every test here needs an
	OpenGL context and is marked `gl` (skipped automatically when none is available). '''
import pytest
from madcad.mathutils import fquat, fvec3
from madcad.rendering.d3 import Perspective, Orthographic, Turntable, Orbit

from uimadcad.sceneview import SceneComposer

pytestmark = pytest.mark.gl


@pytest.fixture
def view(madcad_app):
	# the default layout already created a focused SceneView
	sceneview = madcad_app.active.sceneview
	assert sceneview is not None
	return sceneview


def test_scene_sync_displays_object(view, madcad_app, qtbot):
	madcad_app.document.setPlainText('from madcad import *\nc = box(vec3(0), vec3(1))\n')
	madcad_app.execute.trigger()

	def displayed():
		view.scene.sync()
		try:
			return view.scene.root['c'] is not None
		except (KeyError, IndexError):
			return False
	qtbot.waitUntil(displayed, timeout=5000)  # a display for 'c' appears in the scene graph


def test_display_toggle_updates_scene_options(view):
	state = view.display_points.isChecked()
	view.display_points.trigger()  # checkable action wired to `triggered` -> _apply_scene_options
	assert view.display_points.isChecked() == (not state)
	assert view.scene.options['display_points'] == view.display_points.isChecked()


def test_projection_switch(view):
	was_perspective = isinstance(view.projection, Perspective)
	view.projection_switch.trigger()
	assert isinstance(view.projection, Perspective) != was_perspective
	assert isinstance(view.projection, (Perspective, Orthographic))


# orient() has a separate branch per navigation type. Each branch gets its own test with the
# navigation pinned explicitly, so both are exercised regardless of the ambient
# `controls.navigation` setting (the default is Turntable, but a user config may force Orbit,
# which previously masked a bug in the Turntable branch).

def test_standard_view_orient_turntable(view):
	view.navigation = Turntable()
	view.orient(fquat(fvec3(0.3, 0.0, 0.7)))
	# yaw/pitch get derived from the target orientation
	assert isinstance(view.navigation.yaw, float)
	assert isinstance(view.navigation.pitch, float)
	# triggering standard views must also stay error-free with this navigation
	view.view_mz.trigger()
	view.view_px.trigger()


def test_standard_view_orient_orbit(view):
	view.navigation = Orbit()
	view.orient(fquat(fvec3(0.3, 0.0, 0.7)))
	assert view.navigation.orientation is not None
	view.view_mz.trigger()
	view.view_px.trigger()


def test_format_key(view):
	assert view.scene.format_key(('a', 'b')) == 'a.b'
	assert view.scene.format_key(('a', 0)) == 'a[0]'


def test_selection_clear_resets_active(view):
	view.scene.selection_clear()
	assert view.scene.active_selection is None
	assert view.scene.active_path is None


def test_scene_has_composer(view):
	assert isinstance(view.scene.composer, SceneComposer)
