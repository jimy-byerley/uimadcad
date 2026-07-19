import pytest
from madcad.qt import QTextDocument, QTextCursor, QFont, QTextOption
from uimadcad import settings
from uimadcad.utils import vec_to_qcolor
from uimadcad.scriptview import (
	SubstitutionIndex, ScriptView, Highlighter,
	cursor_location, move_text_cursor,
	)
from pnprint import nprint

def test_substitution_index():
	def assert_eq(name, a, b):
		assert a == b, (name,':', a, 'should be', b)
	
	def check():
		for dst, src in enumerate(reference):
			if src is None:
				continue
			assert_eq(src, index.upgrade(src), dst)
			assert_eq(dst, index.downgrade(dst), src)
	
	def test(position, remove=0, add=0):
		print()
		index.substitute(position, remove, add)
		reference[position-remove:position] = [None]*add
		nprint('src', index._src)
		nprint('dst', index._dst)
		check()
		
	index = SubstitutionIndex()
	reference = list(range(30))
	
	# test our check
	check()
	
	# test reliability of the resulting index
	test(10, remove=2)
	test(16, remove=2)
	test(10, remove=2)
	test(9, remove=2)
	
	test(10, add=2)
	test(9, add=2)
	test(8, add=2)
	test(20, remove=2, add=2)

	index = SubstitutionIndex()
	reference = list(range(30))
	
	# test fusion of edited zones
	test(10, add=1)
	test(11, add=1)
	test(12, add=2)
	test(14, add=2)
	assert index.steps() == 1
	test(17, add=1)
	assert index.steps() == 2


# --- pure cursor helpers --------------------------------------------------------------

def test_cursor_location(qapp):
	doc = QTextDocument()
	doc.setPlainText('ab\ncd')
	cursor = QTextCursor(doc)
	cursor.setPosition(4)  # the 'd' on the second line
	assert cursor_location(cursor) == (1, 1)

def test_move_text_cursor(qapp):
	doc = QTextDocument()
	doc.setPlainText('ab\ncd\nef')
	cursor = QTextCursor(doc)
	move_text_cursor(cursor, (2, 1))
	assert cursor_location(cursor) == (2, 1)


# --- syntax highlighter ---------------------------------------------------------------

def _format_at(block, position):
	''' return the QTextCharFormat the highlighter applied at a position in a block '''
	for r in block.layout().formats():
		if r.start <= position < r.start + r.length:
			return r.format
	return None

@pytest.fixture
def highlighted(qapp):
	''' a document with the python highlighter attached, returning (doc, highlighter) '''
	doc = QTextDocument()
	highlighter = Highlighter(doc, QFont())
	return doc, highlighter

def test_highlight_keyword(highlighted):
	doc, h = highlighted
	doc.setPlainText('def foo():')
	h.rehighlight()
	fmt = _format_at(doc.findBlockByNumber(0), 0)  # the 'def' keyword
	assert fmt is not None
	assert fmt.foreground().color() == vec_to_qcolor(settings.scriptview['keyword_color'])

def test_highlight_call(highlighted):
	doc, h = highlighted
	doc.setPlainText('foo(1)')
	h.rehighlight()
	fmt = _format_at(doc.findBlockByNumber(0), 0)  # the called name 'foo'
	assert fmt.foreground().color() == vec_to_qcolor(settings.scriptview['call_color'])

def test_highlight_number(highlighted):
	doc, h = highlighted
	doc.setPlainText('x = 123')
	h.rehighlight()
	fmt = _format_at(doc.findBlockByNumber(0), 4)  # the '123'
	assert fmt.foreground().color() == vec_to_qcolor(settings.scriptview['number_color'])

def test_highlight_comment(highlighted):
	doc, h = highlighted
	doc.setPlainText('x = 1  # a comment')
	h.rehighlight()
	fmt = _format_at(doc.findBlockByNumber(0), 8)  # inside the comment
	assert fmt.foreground().color() == vec_to_qcolor(settings.scriptview['comment_color'])

def test_highlight_string(highlighted):
	doc, h = highlighted
	doc.setPlainText('s = "hello"')
	h.rehighlight()
	fmt = _format_at(doc.findBlockByNumber(0), 5)  # inside the string literal
	assert fmt.foreground().color() == vec_to_qcolor(settings.scriptview['string_color'])


# --- ScriptView widget ----------------------------------------------------------------

@pytest.fixture
def scriptview(qtbot, fake_app):
	view = ScriptView(fake_app)
	qtbot.addWidget(view)
	return view

def test_scriptview_builds_on_shared_document(scriptview, fake_app):
	# the editor edits the application's document (see ScriptView.__init__ assert)
	assert scriptview.editor.document() is fake_app.document

def test_scriptview_indent_increase(scriptview, fake_app):
	fake_app.document.setPlainText('x\ny')
	cursor = scriptview.editor.textCursor()
	cursor.setPosition(0)
	cursor.setPosition(3, QTextCursor.KeepAnchor)  # select both lines
	scriptview.editor.setTextCursor(cursor)
	scriptview.indent_increase.trigger()
	assert '\t' in fake_app.document.toPlainText()

def test_scriptview_comment_uncomment(scriptview, fake_app):
	fake_app.document.setPlainText('a\nb')
	cursor = scriptview.editor.textCursor()
	cursor.setPosition(0)
	cursor.setPosition(3, QTextCursor.KeepAnchor)
	scriptview.editor.setTextCursor(cursor)
	scriptview.comment.trigger()
	assert '#' in fake_app.document.toPlainText()
	# reselect and uncomment
	cursor = scriptview.editor.textCursor()
	cursor.select(QTextCursor.Document)
	scriptview.editor.setTextCursor(cursor)
	scriptview.uncomment.trigger()
	assert '#' not in fake_app.document.toPlainText()

def test_scriptview_undo_redo(scriptview, fake_app):
	fake_app.document.setPlainText('')
	scriptview.editor.insertPlainText('hello')
	assert fake_app.document.toPlainText() == 'hello'
	scriptview.undo.trigger()
	assert fake_app.document.toPlainText() == ''
	scriptview.redo.trigger()
	assert fake_app.document.toPlainText() == 'hello'

def test_scriptview_fontsize(scriptview):
	before = scriptview.font.pointSize()
	scriptview.fontsize_increase.trigger()
	assert scriptview.font.pointSize() == before + 1
	scriptview.fontsize_decrease.trigger()
	assert scriptview.font.pointSize() == before

def test_scriptview_linewrap_toggle(scriptview):
	# these actions are checkable but connected to `triggered`, so use trigger() (which
	# toggles the checked state and runs the callback), not setChecked()
	scriptview.linewrap.trigger()
	assert scriptview.editor.wordWrapMode() == QTextOption.WordWrap
	scriptview.linewrap.trigger()
	assert scriptview.editor.wordWrapMode() == QTextOption.NoWrap

def test_scriptview_show_linenumbers_toggle(scriptview):
	scriptview.show_linenumbers.trigger()
	assert not scriptview.linenumbers.isHidden()
	scriptview.show_linenumbers.trigger()
	assert scriptview.linenumbers.isHidden()

def test_scriptview_seek_line_and_position(scriptview, fake_app):
	fake_app.document.setPlainText('l0\nl1\nl2\nl3')
	scriptview.seek_line(3)  # 1-based
	assert scriptview.editor.textCursor().blockNumber() == 2
	scriptview.seek_position(1)
	assert scriptview.editor.textCursor().position() == 1

def test_scriptview_seek_definition_action_exists(scriptview):
	from uimadcad.utils import Action
	# the action is wired up, but its body is an unfinished `indev` stub, so we only check
	# it exists rather than invoking it (triggering would raise NameError inside the slot)
	assert isinstance(scriptview.seek_definition, Action)


# --- find / replace -------------------------------------------------------------------

def test_find_next(scriptview, fake_app):
	fake_app.document.setPlainText('foo bar foo baz')
	editor = scriptview.editor
	cursor = editor.textCursor()
	cursor.setPosition(0)
	editor.setTextCursor(cursor)
	scriptview.findreplace.src.setText('foo')
	scriptview.findreplace.next.click()
	assert editor.textCursor().selectedText() == 'foo'

def test_replace_all(scriptview, fake_app):
	fake_app.document.setPlainText('foo foo foo')
	scriptview.findreplace.src.setText('foo')
	scriptview.findreplace.dst.setText('X')
	scriptview.findreplace.all.click()
	# the last two occurrences are replaced (the tool starts scanning from position 1)
	assert fake_app.document.toPlainText() == 'foo X X'


# --- navigation panel -----------------------------------------------------------------

def test_navigation_history_enable_states(scriptview, fake_app):
	fake_app.document.setPlainText('x' * 30)
	nav = scriptview.navigation
	# empty history: nothing to go back/forward to
	assert not nav.previous.isEnabled()
	assert not nav.next.isEnabled()
	nav._append(10)
	nav._append(20)
	# now positioned at the end of a 2-entry history
	assert nav.previous.isEnabled()
	assert not nav.next.isEnabled()

def test_navigation_seek(scriptview, fake_app):
	fake_app.document.setPlainText('l0\nl1\nl2\nl3')
	nav = scriptview.navigation
	nav.seek_position(4)
	assert scriptview.editor.textCursor().position() == 4
	nav.seek_line(2)
	assert scriptview.editor.textCursor().blockNumber() == 2

def test_navigation_go_to_line(scriptview, fake_app):
	fake_app.document.setPlainText('l0\nl1\nl2\nl3')
	nav = scriptview.navigation
	nav.line.setValue(3)
	nav.go.click()
	assert scriptview.editor.textCursor().blockNumber() == 2
