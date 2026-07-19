''' integration tests for the controller (uimadcad.app.Madcad).

	Building a Madcad instance creates the main window (and thus a SceneView), so every
	test here needs an OpenGL context and is marked `gl`. '''
import pytest


@pytest.mark.gl
def test_load_file_populates_document(madcad_app, sample_script):
	assert 'box' in madcad_app.document.toPlainText()
	assert madcad_app.active.file == str(sample_script)

@pytest.mark.gl
def test_save_writes_document_to_file(madcad_app):
	madcad_app.document.setPlainText('a = 1\n')
	madcad_app.save.trigger()
	with open(madcad_app.active.file) as f:
		assert f.read() == 'a = 1\n'
	# saving marks the document as clean
	assert not madcad_app.document.isModified()

@pytest.mark.gl
def test_execute_populates_scope(madcad_app, qtbot):
	madcad_app.document.setPlainText('x = 2 + 3\n')
	madcad_app.execute.trigger()

	def executed():
		scope = madcad_app.interpreter.scopes.get(madcad_app.interpreter.filename, {})
		return 'x' in scope
	qtbot.waitUntil(executed, timeout=5000)

	assert madcad_app.interpreter.scopes[madcad_app.interpreter.filename]['x'] == 5
	assert madcad_app.interpreter.exception is None

@pytest.mark.gl
def test_execute_reports_exception(madcad_app, qtbot):
	madcad_app.document.setPlainText('y = 1/0\n')
	madcad_app.execute.trigger()
	qtbot.waitUntil(lambda: madcad_app.interpreter.exception is not None, timeout=5000)
	assert isinstance(madcad_app.interpreter.exception, ZeroDivisionError)

@pytest.mark.gl
def test_clear_resets_interpreter(madcad_app):
	previous = madcad_app.interpreter
	madcad_app.clear.trigger()
	assert madcad_app.interpreter is not previous
	assert madcad_app.interpreter.scopes == {}

@pytest.mark.gl
def test_check_change_reloads_from_disk(madcad_app):
	# enable auto-reload (checkable action wired to `toggled`)
	madcad_app.trigger_on_file_change.setChecked(True)
	# simulate an external edit with a newer modification time
	with open(madcad_app.active.file, 'w') as f:
		f.write('reloaded = 1\n')
	madcad_app.active.date = 0  # force the on-disk file to look newer than what we loaded
	madcad_app.check_change()
	assert 'reloaded' in madcad_app.document.toPlainText()
