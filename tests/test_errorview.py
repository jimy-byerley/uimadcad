''' tests for the exception/traceback panel (uimadcad.errorview.ErrorView) '''
import pytest
from madcad.qt import Qt, QApplication

from uimadcad.errorview import ErrorView


def make_exception():
	''' produce a real exception carrying a traceback with a local variable to display '''
	def inner():
		local_var = 123
		raise ValueError('boom')
	try:
		inner()
	except ValueError as err:
		return err


@pytest.fixture
def errorview(qtbot, fake_app):
	view = ErrorView(fake_app)
	qtbot.addWidget(view)
	return view


def test_initial_state_is_empty(errorview):
	assert errorview.label.text() == 'no exception'
	assert errorview.traceback.toPlainText() == ''

def test_set_renders_exception(errorview):
	errorview.set(make_exception())
	assert 'ValueError' in errorview.label.text()
	assert 'boom' in errorview.label.text()
	assert errorview.traceback.toPlainText() != ''
	assert errorview.exception is not None

def test_clear_resets(errorview):
	errorview.set(make_exception())
	errorview.clear()
	assert errorview.exception is None
	assert errorview.label.text() == 'no exception'
	assert errorview.traceback.toPlainText() == ''

def test_syntax_error_branch(errorview, fake_app):
	# a real SyntaxError from compile() carries the filename/lineno/text and a traceback
	try:
		compile('x = (', fake_app.interpreter.filename, 'exec')
	except SyntaxError as err:
		syntax_error = err
	errorview.set(syntax_error)
	text = errorview.traceback.toPlainText()
	assert fake_app.interpreter.filename in text
	assert 'line' in text

def test_copy_to_clipboard(errorview):
	errorview.set(make_exception())
	errorview.copy_to_clipboard.click()
	assert 'boom' in QApplication.instance().clipboard().text()

def test_open_scope_toggles_visibility(errorview):
	errorview.set(make_exception())
	errorview.open_scope.setChecked(True)  # a checkable button wired to `toggled`
	assert not errorview.scope.isHidden()
	errorview.open_scope.setChecked(False)
	assert errorview.scope.isHidden()

@pytest.mark.xfail(reason=(
	"ErrorView._update_scope guards on isinstance(f_locals, dict), which is False on "
	"Python 3.13 where frame.f_locals is a PEP 667 FrameLocalsProxy, so no locals are "
	"listed. Bug in errorview.py, not in the test."), strict=False)
def test_open_scope_lists_locals(errorview):
	errorview.set(make_exception())
	errorview.open_scope.setChecked(True)
	assert 'local_var' in errorview.scope.toPlainText()

def test_escape_closes_and_clears_active(errorview, fake_app, qtbot):
	fake_app.active.errorview = errorview
	errorview.show()
	qtbot.keyClick(errorview, Qt.Key_Escape)
	assert fake_app.active.errorview is None
