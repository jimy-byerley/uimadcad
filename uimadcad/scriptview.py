import re

from madcad.qt import (
	QWidget, QPlainTextEdit, QVBoxLayout,
	QTextCursor, QSyntaxHighlighter, QFont, QFontMetrics, QColor, QTextOption, QPalette, QPainter,
	Qt, QEvent, QMargins, QSize, QRect, QSizePolicy, QKeySequence,
	)

from . import settings
from .utils import Initializer, ToolBar, button, action, Action, vec_to_color, charformat, vlayout, spacer


class ScriptView(QWidget):
	''' text editor part of the app frame '''
	
	# NOTE:	for unknow reasons, a widget created as child of QPlainTextEdit is rendered only if created in the __init__
	
	bar_margin = 2
	
	def __init__(self, app, cursor=None, parent=None):
		self.app = app
		self.font = QFont(*settings.scriptview['font'])
		
		# set cursor position on openning
		if cursor:
			pass
		elif self.app.active.scriptview:
			cursor = app.active.scriptview.editor.textCursor()
		
		super().__init__(parent)
		self.setMinimumSize(200,100)
		self.setSizePolicy(QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred))
		Initializer.process(self)
		
		# text editor widget
		self.editor = ScriptEdit(self)
		self.linenumbers = ScriptLines(self.font, self.editor)
		assert self.app.document is self.editor.document()
		
		# # toolbars
		self.top = ToolBar('top', [
			self.new_view,
			spacer(5, 0),
			self.previous_location,
			self.next_location,
			spacer(5, 0),
			self.seek_location,
			self.view_selection,
			],
			orientation=Qt.Horizontal, 
			margins=QMargins(3,3,3,0),
			icon_size='small',
			parent=self.editor)
		
		self.bot = ToolBar('right', [
			self.undo,
			self.redo,
			None,
			self.indent_increase,
			self.indent_decrease,
			self.reformat,
			None,
			self.find,
			self.replace,
			self.seek_definition,
			None,
			self.fontsize_increase,
			self.fontsize_decrease,
			self.linewrap,
			self.show_linenumbers,
			],
			orientation=Qt.Horizontal, 
			margins=QMargins(0,3,3,3),
			icon_size='small',
			parent=self.editor)
		
		# global layout
		self.setLayout(vlayout([
			self.top,
			self.editor,
			self.bot,
			], 
			margins=QMargins(0,0,0,0), 
			spacing=0))
		
		# other configurations
		self.setFocusProxy(self.editor)
		self.editor.updateRequest.connect(self._update_line_numbers)
		if cursor:
			self.editor.setTextCursor(cursor)
		
		self._update_colors()
		self._update_active_selection()
		self._retreive_settings()
		self._toolbars_visible(False)
	
	def keyPressEvent(self, event):
		# reimplement top bar shortcuts here because Qt cannot deambiguate which view the shortcut belongs to
		event.accept()
		if event.key() == Qt.Key_Left and event.modifiers() & Qt.AltModifier:
			self.previous_location.trigger()
		elif event.key() == Qt.Key_Right and event.modifiers() & Qt.AltModifier:
			self.next_location.trigger()
		elif event.key() == Qt.Key_Return and event.modifiers() & Qt.AltModifier:
			self.seek_location.setChecked(True)
		elif event.key() == Qt.Key_Down and event.modifiers() & Qt.AltModifier:
			self.view_selection.click()
		else:
			event.ignore()
			return super().keyPressEvent(event)
	
	def showEvent(self, event):	
		self.app.views.add(self)
		if not self.app.active.scriptview:	
			self.app.active.scriptview = self
	
	def hideEvent(self, event):
		self.app.views.remove(self)
		if self.app.active.scriptview is self:
			self.app.active.scriptview = None
		
	def changeEvent(self, event):
		# detect theme change
		if event.type() == QEvent.PaletteChange and settings.scriptview['system_theme']:
			settings.use_qt_colors()
			self._update_colors()
		return super().changeEvent(event)
	
	def resizeEvent(self, event):
		super().resizeEvent(event)
		
		# self.bot.setGeometry(
		# 	self.width() - self.bot.sizeHint().width() - self.bar_margin, 
		# 	max(0, self.height()//2 - self.bot.sizeHint().height()//2),
		# 	self.bot.sizeHint().width(), 
		# 	min(self.height(), self.bot.sizeHint().height()),
		# 	)
		# if self.top.parent() is self:
		# 	self.top.setGeometry(
		# 		self.bar_margin+self.left.width(), 
		# 		self.bar_margin,
		# 		self.width()-self.left.width() - self.bar_margin,
		# 		self.top.sizeHint().height(),
		# 		)
		
		self._update_line_numbers()
	
	def _toolbars_visible(self, enable):
		self.bot.setVisible(enable)

	def _update_colors(self):
		palette = self.editor.palette()
		palette.setColor(QPalette.Base, vec_to_color(settings.scriptview['background']))
		self.editor.setPalette(palette)
		self.highlighter = Highlighter(self.editor.document(), self.font)
	
	def _update_line_numbers(self):
		# update location label
		line, column = cursor_location(self.editor.textCursor())
		self.seek_location.setText('line {}, column {}'.format(line+1, column+1))
		
		# update the line number area
		if self.show_linenumbers.isChecked():
			# compute number of digits
			nlines = max(1, self.editor.blockCount())
			digits = 1
			while nlines >= 10:		
				nlines //= 10
				digits += 1
			# resize area
			charwidth = QFontMetrics(self.font).maxWidth()
			border = charwidth//2
			width = (digits+3)*charwidth
			self.editor.setViewportMargins(width, 0, 0, 0)
			cr = self.editor.contentsRect()	# only this rect has the correct area, with the good margins with the real widget geometry
			self.linenumbers.setGeometry(QRect(cr.left(), cr.top(), width, cr.height()))
			self.linenumbers.width = width - border//2
			self.linenumbers.border = border
			self.linenumbers.update()
		else:
			self.editor.setViewportMargins(0, 0, 0, 0)
		self.editor.update()
	
	def _update_active_selection(self):
		# if self.scene.active_selection:
		if True:
			# text = #TODO
			text = "machin['truc'].bidule"
		
			font = QFont(*settings.scriptview['font'])
			pointsize = font.pointSize()
			self.view_selection.setFont(font)
			self.view_selection.setText(text)
			self.view_selection.resize(pointsize*len(text), pointsize*2)
			self.view_selection.show()
		else:
			self.view_selection.hide()
			
	def _retreive_settings(self):
		self.show_linenumbers.setChecked(settings.scriptview['linenumbers'])
		self.linewrap.setChecked(settings.scriptview['linewrap'])
	
	@action(icon='view-dual')
	def new_view(self):
		''' create a new view widget '''
		self.app.window.insert_view(self, ScriptView(
			self.app, 
			self.editor.textCursor(),
			))
			
	@action(icon='go-previous') #, shortcut='Alt+Left')
	def previous_location(self):
		''' move cursor to previous historical position 
		
			(shortcut: Alt+Left)
		'''
		indev
		
	@action(icon='go-next') #, shortcut='Alt+Right')
	def next_location(self):
		''' move cursor to next historical position 
		
			(shortcut: Alt+Right)
		'''
		indev
	
	@button(flat=True) #, shortcut='Alt+Return')
	def seek_location(self):
		''' cursor position in the script, click to modify 
			
			(shortcut: Alt+Return)
		'''
		indev
		
	@button(flat=True) #, shortcut='Alt+Down')
	def view_selection(self):
		''' zoom the object in selected variable in the active sceneview 
		
			(shortcut: Alt+Down)
		'''
		inbev
		
	@action(icon='go-up', shortcut='Alt+Up')
	def seek_definition(self):
		''' move cursor to the definition of variable under cursor
		
			(mouse: Ctrl+click)
		'''
		indev
		
	
	@action(icon='edit-undo', shortcut='Ctrl+Z')
	def undo(self):
		''' undo previous changes in history '''
		self.app.document.undo()
		
	@action(icon='edit-redo', shortcut='Ctrl+Y')
	def redo(self):
		''' redo next changes in history '''
		self.app.document.redo()
	
	@action(icon='format-indent-more', shortcut='Tab')
	def indent_increase(self):
		''' increase the indentation level of the current or selected lines '''
		cursor = self.editor.textCursor()
		start, stop = sorted([cursor.position(), cursor.anchor()])
		cursor.setPosition(start)
		cursor.movePosition(QTextCursor.StartOfLine)
		cursor.movePosition(QTextCursor.PreviousCharacter)
		cursor.setPosition(stop, QTextCursor.KeepAnchor)
		
		cursor.insertText(cursor.selectedText().replace('\u2029', '\u2029\t'))
		
		cursor = self.editor.textCursor()
		cursor.setPosition(start, cursor.KeepAnchor)
		self.editor.setTextCursor(cursor)
	
	@action(icon='format-indent-less', shortcut='Shift+Tab')
	def indent_decrease(self):
		''' decrease the indentation level of the current or selected lines '''
		cursor = self.editor.textCursor()
		start, stop = sorted([cursor.position(), cursor.anchor()])
		cursor.setPosition(start)
		cursor.movePosition(QTextCursor.StartOfLine)
		cursor.movePosition(QTextCursor.PreviousCharacter)
		cursor.setPosition(stop, QTextCursor.KeepAnchor)
		
		cursor.insertText(cursor.selectedText().replace('\u2029\t', '\u2029'))
		
		cursor = self.editor.textCursor()
		cursor.setPosition(start, cursor.KeepAnchor)
		self.editor.setTextCursor(cursor)
		
	@action(icon='format-justify-center', shortcut='Ctrl+Shift+F')
	def reformat(self):
		''' reformat selected code to get proper nested indentation 
			and split long expressions into multiple lines 
		'''
		indev
		
	@action(icon='format-font-size-more', shortcut='Ctrl++')
	def fontsize_increase(self):
		''' increase the script font size (purely visual) '''
		self.font.setPointSize(self.font.pointSize() + 1)
		self.highlighter = Highlighter(self.editor.document(), self.font)
	
	@action(icon='format-font-size-less', shortcut='Ctrl+-')
	def fontsize_decrease(self):
		''' decrease the script font size (purely visual) '''
		self.font.setPointSize(self.font.pointSize() - 1)
		self.highlighter = Highlighter(self.editor.document(), self.font)
		
	@action(icon='text-wrap', checkable=True, shortcut='F9')
	def linewrap(self, enable):
		''' wrap lines when too long for the script view '''
		if enable:
			self.editor.setWordWrapMode(QTextOption.WordWrap)
		else:
			self.editor.setWordWrapMode(QTextOption.NoWrap)
	
	@action(icon='madcad-line-numbers', checkable=True, shortcut='F10')
	def show_linenumbers(self, visible):
		''' show line numbers aside of script '''
		self.linenumbers.setVisible(visible)
		self._update_line_numbers()
		
	@action(icon='edit-find-symbolic', shortcut='Ctrl+F')
	def find(self):
		''' find occurences of a text sequence '''
		indev
		
	@action(icon='edit-find-replace', shortcut='Ctrl+R')
	def replace(self):
		''' replace a text sequence by an other '''
		indev
	
# 	def seek_line(self, lineno):
# 		''' set cursor and scroll to lineno '''
# 		block = self.editor.document().findBlockByLineNumber(lineno-1)
# 		cursor = QTextCursor(block)
# 		cursor.movePosition(QTextCursor.EndOfLine)
# 		self.editor.setTextCursor(cursor)
# 		self.editor.ensureCursorVisible()
# 	
# 	def seek_position(self, position):
# 		''' set cursor and scroll to position '''
# 		cursor = QTextCursor(self.editor.document())
# 		cursor.setPosition(position)
# 		self.editor.setTextCursor(cursor)
# 		self.editor.ensureCursorVisible()


class ScriptEdit(QPlainTextEdit):
	''' text editor widget for ScriptView, only here to change some QPlainTextEdit behaviors '''
	
	def __init__(self, view: ScriptView):
		super().__init__(view)
		
		self.setDocument(view.app.document)
		self.setWordWrapMode(QTextOption.WrapMode.WordWrap 
									if settings.scriptview['linewrap'] else 
									QTextOption.WrapMode.NoWrap)
		self.setTabStopDistance(settings.scriptview['tabsize'] * QFontMetrics(view.font).averageCharWidth()+1.5)
		self.setCursorWidth(QFontMetrics(view.font).averageCharWidth())
		self.setCenterOnScroll(True)
	
	def focusInEvent(self, event):
		self.parent().app.active.scriptview = self.parent()
		self.parent()._toolbars_visible(True)
		super().focusInEvent(event)
		
	def focusOutEvent(self, event):
		self.parent()._toolbars_visible(False)
		super().focusOutEvent(event)
	
	def keyPressEvent(self, event):
		cursor = self.textCursor()
		if cursor.hasSelection():
			if event.key() == Qt.Key.Key_Tab:		self.parent().indent_increase.trigger()
			elif event.key() == Qt.Key.Key_Backtab:	self.parent().indent_decrease.trigger()
			else:	super().keyPressEvent(event)
		else:		super().keyPressEvent(event)
	

class ScriptLines(QWidget):
	''' line number display for the text view '''
	def __init__(self, font, parent):
		super().__init__(parent)
		self.font = font
		self.width = 0
	def sizeHint(self):
		return QSize(self.width, 0)
	def paintEvent(self, event):
		# paint numbers from the first visible block to the last visible
		zone = event.rect()
		painter = QPainter(self)
		view = self.parent()
		block = view.firstVisibleBlock()
		top = int(view.blockBoundingGeometry(block).translated(view.contentOffset()).top())
		charwidth = QFontMetrics(self.font).maxWidth()
		while block.isValid() and top <= zone.bottom():
			if block.isVisible() and top >= zone.top():
				height = int(view.blockBoundingRect(block).height())
				painter.setFont(self.font)
				painter.drawText(0, top, self.width-2*charwidth, height, Qt.AlignRight, str(block.blockNumber()+1))
				top += height
			block = block.next()


class Highlighter(QSyntaxHighlighter):
	''' python syntax highlighter for QTextDocument '''
	def __init__(self, document, font):
		super().__init__(document)
		# default font applies everywhere the highlighter doesn't pass, like empty lines
		document.setDefaultFont(font)
		# precompute formatting for every case
		s = settings.scriptview
		self.fmt_default = charformat(foreground=vec_to_color(s['normal_color']), font=font)
		self.fmt_keyword = charformat(foreground=vec_to_color(s['keyword_color']), font=font, weight=QFont.ExtraBold)
		self.fmt_call = charformat(foreground=vec_to_color(s['call_color']), font=font)
		self.fmt_constant = charformat(foreground=vec_to_color(s['number_color']), font=font)
		self.fmt_string = charformat(foreground=vec_to_color(s['string_color']), font=font)
		self.fmt_comment = charformat(foreground=vec_to_color(s['comment_color']), font=font, italic=True, weight=QFont.Thin)
		self.fmt_operator = charformat(foreground=vec_to_color(s['operator_color']), font=font)
		# state machine description
		self.states = {
			# normal context
			-1: [self.fmt_default,
				(re.compile(r'([a-zA-Z]\w*)\('), self.match_function),
				(re.compile(r'([a-zA-Z]\w*)'), self.match_word),
				(re.compile(r'#.*$'), self.match_comment),
				(re.compile(r'[+-]?\d+\.?\d*(e[+-]\d+)?'), self.fmt_constant),
				(re.compile(r'[+\-\*/@<>=!~&\|]+'), self.fmt_operator),
				
				(re.compile(r"^\s*'''"), self.match_commentstart1), 
				(re.compile(r"^\s*'"),   self.match_commentstart2), 
				(re.compile(r'^\s*"""'), self.match_commentstart3), 
				(re.compile(r'^\s*"'),   self.match_commentstart4), 
				(re.compile(r"'''"), self.match_stringstart1), 
				(re.compile(r"'"),   self.match_stringstart2), 
				(re.compile(r'"""'), self.match_stringstart3), 
				(re.compile(r'"'),   self.match_stringstart4), 
				],
			# string
			0: [self.fmt_string, (re.compile("'''"), self.match_stringend)],
			1: [self.fmt_string, (re.compile("'"),   self.match_stringend)],
			2: [self.fmt_string, (re.compile('"""'), self.match_stringend)],
			3: [self.fmt_string, (re.compile('"'),   self.match_stringend)],
			# comment
			4: [self.fmt_comment, (re.compile("'''"), self.match_commentend)],
			5: [self.fmt_comment, (re.compile("'"),   self.match_commentend)],
			6: [self.fmt_comment, (re.compile('"""'), self.match_commentend)],
			7: [self.fmt_comment, (re.compile('"'),   self.match_commentend)],
			}
	
	keywords = {'pass', 'and', 'or', 'if', 'elif', 'else', 'match', 'case', 'for', 'while', 'break', 'continue', 'is', 'in', 'not', 'def', 'lambda', 'class', 'yield', 'async', 'await', 'with', 'try', 'except', 'finally', 'raise', 'from', 'import', 'as', 'with', 'return', 'assert'}
	constants = {'None', 'True', 'False', 'Ellipsis'}
	def match_word(self, match):
		word = match.group(1)
		if word in self.keywords:
			self.setFormat(match.start(1), match.end(1)-match.start(0), self.fmt_keyword)
		elif word in self.constants:
			self.setFormat(match.start(0), match.end(0)-match.start(0), self.fmt_constant)
		else:
			self.setFormat(match.start(0), match.end(0)-match.start(0), self.fmt_default)
		return match.end(1)
	def match_function(self, match):
		self.setFormat(match.start(1), match.end(1)-match.start(1), self.fmt_call)
		return match.end(1)
	def match_comment(self, match):
		self.setFormat(match.start(0), match.end(0)-match.start(0), self.fmt_comment)
		return match.end(0)
		
	def match_stringstart1(self, match):
		self.setFormat(match.start(0), match.end(0)-match.start(0), self.fmt_string)
		self.setCurrentBlockState(0)
		return match.end(0)
	def match_stringstart2(self, match):
		self.setFormat(match.start(0), match.end(0)-match.start(0), self.fmt_string)
		self.setCurrentBlockState(1)
		return match.end(0)
	def match_stringstart3(self, match):
		self.setFormat(match.start(0), match.end(0)-match.start(0), self.fmt_string)
		self.setCurrentBlockState(2)
		return match.end(0)
	def match_stringstart4(self, match):
		self.setFormat(match.start(0), match.end(0)-match.start(0), self.fmt_string)
		self.setCurrentBlockState(3)
		return match.end(0)
	def match_stringend(self, match):
		self.setFormat(match.start(0), match.end(0)-match.start(0), self.fmt_string)
		self.setCurrentBlockState(-1)
		return match.end(0)
		
	def match_commentstart1(self, match):
		self.setFormat(match.start(0), match.end(0)-match.start(0), self.fmt_comment)
		self.setCurrentBlockState(4)
		return match.end(0)
	def match_commentstart2(self, match):
		self.setFormat(match.start(0), match.end(0)-match.start(0), self.fmt_comment)
		self.setCurrentBlockState(5)
		return match.end(0)
	def match_commentstart3(self, match):
		self.setFormat(match.start(0), match.end(0)-match.start(0), self.fmt_comment)
		self.setCurrentBlockState(6)
		return match.end(0)
	def match_commentstart4(self, match):
		self.setFormat(match.start(0), match.end(0)-match.start(0), self.fmt_comment)
		self.setCurrentBlockState(7)
		return match.end(0)
	def match_commentend(self, match):
		self.setFormat(match.start(0), match.end(0)-match.start(0), self.fmt_comment)
		self.setCurrentBlockState(-1)
		return match.end(0)
	
	def highlightBlock(self, text):
		# state machine execution on a block of text (a line of code)
		self.setCurrentBlockState(self.previousBlockState())
		start = 0
		end = len(text)
		while start < end:
			patterns = iter(self.states[self.currentBlockState()])
			default = next(patterns)
			self.setFormat(start, 1, default)
			for pattern, func in patterns:
				match = pattern.match(text, start)
				if match:
					if callable(func):
						start = func(match)-1
					else:
						self.setFormat(match.start(0), match.end(0)-match.start(0), func)
						start = match.end(0)-1
					break
			start += 1


def cursor_location(cursor):
	return cursor.blockNumber(), cursor.positionInBlock()

def move_text_cursor(cursor, location, movemode=QTextCursor.MoveAnchor):
	line, column = location
	if cursor.blockNumber() < line:		cursor.movePosition(cursor.NextBlock, movemode, line-cursor.blockNumber())
	if cursor.blockNumber() < line:		cursor.movePosition(cursor.PreviousBlock, movemode, cursor.blockNumber()-line)
	if cursor.columnNumber() < column:	cursor.movePosition(cursor.NextCharacter, movemode, column-cursor.columnNumber())
	if cursor.columnNumber() > column:	cursor.movePosition(cursor.PreviousCharacter, movemode, cursor.columnNumber()-column)
