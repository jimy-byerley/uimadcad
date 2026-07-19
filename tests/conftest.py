''' shared pytest fixtures and configuration for the uimadcad GUI test suite

	The tests drive real Qt widgets through pytest-qt, but headless: no display is
	required.  We do not force a particular Qt binding — the app selects one through its
	`madcad.qt` shim (PyQt5 here, the declared runtime dependency), and we simply align
	pytest-qt to whatever the shim resolved.
'''
import os
import types

# force the offscreen Qt platform so the test suite never pops real windows, whatever the
# developer's environment sets. Must happen before any Qt library initializes its platform
# plugin. Set UIMADCAD_TEST_QPA to run against a visible platform for debugging.
os.environ["QT_QPA_PLATFORM"] = os.environ.get("UIMADCAD_TEST_QPA", "offscreen")

import pytest
import madcad.qt

# detect the binding the app's shim actually resolved (e.g. 'PyQt5') and tell pytest-qt
# to use the same one, so the test harness and the app never load two bindings at once
QT_BINDING = madcad.qt.QObject.__module__.split('.')[0]
os.environ.setdefault("QT_API", QT_BINDING.lower())

from madcad.qt import Qt, QApplication, QTextDocument, QPlainTextDocumentLayout

# pymadcad shares one OpenGL context between its scenes; this must be set before the
# QApplication is created (pytest-qt creates it lazily in the `qapp` fixture)
QApplication.setAttribute(Qt.AA_ShareOpenGLContexts, True)

from uimadcad import settings
from uimadcad.app import Active
from uimadcad.interpreter import Interpreter
from uimadcad.scriptview import SubstitutionIndex


def pytest_report_header(config):
	return "qt binding (detected from madcad.qt): {}".format(QT_BINDING)


@pytest.fixture(scope="session", autouse=True)
def _theme(qapp):
	''' populate the color settings.

		Several widgets (e.g. ScriptView) read settings keys such as
		`selection_background`/`hover_background` that only exist once the color scheme is
		resolved from the running QApplication. '''
	settings.use_qt_colors()


@pytest.fixture
def document(qapp):
	''' a QTextDocument wired like the one `Madcad` builds for the editor '''
	doc = QTextDocument()
	doc.setDocumentLayout(QPlainTextDocumentLayout(doc))
	return doc


@pytest.fixture
def fake_app(qapp, document):
	''' a lightweight stand-in for `uimadcad.app.Madcad`.

		It exposes only the attributes the isolated widgets actually read, so a widget can
		be built without spinning up the whole controller (which needs an OpenGL SceneView).
		Tests may attach extra attributes as needed. '''
	return types.SimpleNamespace(
		interpreter = Interpreter('untitled'),
		active = Active(),
		document = document,
		reindex = SubstitutionIndex(),
		views = set(),
		scenes = [],
		window = None,
		)


@pytest.fixture
def sample_script(tmp_path):
	''' write a small known madcad script to a temp file and return its path '''
	path = tmp_path / 'model.py'
	path.write_text(
		"from madcad import *\n"
		"a = 2 + 3\n"
		"b = vec3(1, 0, 0)\n"
		"c = box(vec3(0), vec3(1))\n"
		)
	return path


@pytest.fixture
def madcad_app(qapp, sample_script):
	''' a real `uimadcad.app.Madcad` built on a temp file.

		Constructing the main window creates a SceneView, so this fixture requires an
		OpenGL context: use it only in `@pytest.mark.gl` tests. '''
	from uimadcad.app import Madcad
	app = Madcad(str(sample_script))
	yield app
	# clear focus while the widgets are still alive: ScriptEdit.focusOutEvent reads
	# self.parent()._toolbars_visible, and if the focus-out is delivered during teardown
	# (or while a later test pumps the event loop) the parent's ScriptView wrapper may
	# already be gone, raising AttributeError inside the Qt loop
	focused = qapp.focusWidget()
	if focused is not None:
		focused.clearFocus()
	qapp.processEvents()
	# stop the background execution thread and destroy the window
	try:
		app.thread.close()
	except Exception:
		pass
	if app.window is not None:
		app.window.close()
		app.window.deleteLater()
	qapp.processEvents()


# --- OpenGL availability guard --------------------------------------------------------

@pytest.fixture(scope="session")
def gl_available(qapp):
	''' whether an OpenGL context can be created in this environment (cached once) '''
	try:
		from madcad.qt import QOpenGLContext, QOffscreenSurface
		ctx = QOpenGLContext()
		if not ctx.create():
			return False
		surface = QOffscreenSurface()
		surface.create()
		ok = ctx.makeCurrent(surface)
		ctx.doneCurrent()
		return bool(ok)
	except Exception:
		return False


@pytest.fixture(autouse=True)
def _gl_guard(request):
	''' skip tests marked `gl` when no OpenGL context is available '''
	if request.node.get_closest_marker('gl') and not request.getfixturevalue('gl_available'):
		pytest.skip('requires an OpenGL context (none available in this environment)')
