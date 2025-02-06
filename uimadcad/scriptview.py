import re

from madcad.qt import (
	QWidget, QPlainTextEdit, QVBoxLayout,
	QTextCursor, QSyntaxHighlighter, QFont, QFontMetrics, QColor, QTextOption, QPalette, QPainter,
	Qt, QEvent, QMargins, QSize, QRect,
	)

from . import settings
from .utils import Initializer, ToolBar, button, vec_to_color, charformat


class TextEdit(QPlainTextEdit):
	''' text editor widget for ScriptView, only here to change some QPlainTextEdit behaviors '''
	
	def focusInEvent(self, event):
		self.parent().focused()
		super().focusInEvent(event)
		
	def focusOutEvent(self, event):
		self.parent().unfocused()
		super().leaveEvent(event)
		
	def keyPressEvent(self, event):
		cursor = self.textCursor()
		if cursor.hasSelection():
			if event.key() == Qt.Key.Key_Tab:		self.indent_increase(cursor)
			elif event.key() == Qt.Key.Key_Backtab:	self.indent_decrease(cursor)
			else:	super().keyPressEvent(event)
		else:		super().keyPressEvent(event)
	
	def indent_increase(self, cursor=None):
		if not cursor:	cursor = self.textCursor()
		start, stop = sorted([cursor.position(), cursor.anchor()])
		cursor.setPosition(start)
		cursor.movePosition(QTextCursor.StartOfLine)
		cursor.movePosition(QTextCursor.PreviousCharacter)
		cursor.setPosition(stop, QTextCursor.KeepAnchor)
		
		cursor.insertText(cursor.selectedText().replace('\u2029', '\u2029\t'))
		
		cursor = self.textCursor()
		cursor.setPosition(start, cursor.KeepAnchor)
		self.setTextCursor(cursor)
	
	def indent_decrease(self, cursor=None):
		if not cursor:	cursor = self.textCursor()
		start, stop = sorted([cursor.position(), cursor.anchor()])
		cursor.setPosition(start)
		cursor.movePosition(QTextCursor.StartOfLine)
		cursor.movePosition(QTextCursor.PreviousCharacter)
		cursor.setPosition(stop, QTextCursor.KeepAnchor)
		
		cursor.insertText(cursor.selectedText().replace('\u2029\t', '\u2029'))
		
		cursor = self.textCursor()
		cursor.setPosition(start, cursor.KeepAnchor)
		self.setTextCursor(cursor)
	

class ScriptView(QWidget):
	''' text editor part of the app frame '''
	
	# NOTE:	for unknow reasons, a widget created as child of QPlainTextEdit is rendered only if created in the __init__
	
	def __init__(self, app, parent=None):
		super().__init__(parent)
		Initializer.init(self)
		
		self.app = app
		self.font = QFont(*settings.scriptview['font'])
		
		app.views.append(self)
		if not app.active.scriptview:	app.active.scriptview = self
		
		# text editor widget
		self.editor = TextEdit()
		self.editor.setDocument(app.document)
		self.editor.setWordWrapMode(QTextOption.WrapMode.WordWrap 
									if settings.scriptview['linewrap'] else 
									QTextOption.WrapMode.NoWrap)
		self.editor.setTabStopDistance(settings.scriptview['tabsize'] * QFontMetrics(self.font).averageCharWidth()+1.5)
		self.linenumbers = LineNumbers(self.font, self.editor)
		
		# text coloring
		self.update_colors()
		# set cursor position on openning
		if app.active.scriptview:
			self.editor.setTextCursor(app.active.scriptview.editor.textCursor())
		else:
			self.editor.moveCursor(QTextCursor.End)
		
		# # toolbars
		# self.top = ToolBar([
		# 	self.cursor_location,
		# 	self.executed_state,
		# 	self.settings,
		# 	])
		# self.right = ToolBar([
		# 	self.open,
		# 	self.undo,
		# 	self.redo,
		# 	None,
		# 	self.editor.indent_increase,
		# 	self.editor.indent_decrease,
		# 	self.reformat,
		# 	None,
		# 	self.find,
		# 	self.replace,
		# 	None,
		# 	Menu('font size', [
		# 		self.fontsize_increase,
		# 		self.fontsize_decrease,
		# 		]),
		# 	])
		
		# global layout
		layout = QVBoxLayout(spacing=0)
		layout.addWidget(self.editor)
		layout.setContentsMargins(QMargins(0,0,0,0))
		self.setLayout(layout)
		
		
	def changeEvent(self, event):
		# detect theme change
		if event.type() == QEvent.PaletteChange and settings.scriptview['system_theme']:
			settings.use_qt_colors()
			self.update_colors()
		return super().changeEvent(event)
	
	def closeEvent(self, event):
		self.app.views.remove(self)
		if self.app.active.scriptview is self:
			self.app.active.scriptview = None
		if isinstance(self.parent(), QDockWidget):
			self.app.mainwindow.removeDockWidget(self.parent())
		else:
			super().close()
			
# 	def enterEvent(self, event):
# 		if self.editor.hasFocus():
# 			# TODO show toolbars
# 			pass
# 		
# 	def leaveEvent(self, event):
# 		if not self.editor.hasFocus():	
# 			# TODO hide toolbars
# 			pass
# 	
	def focused(self):
		# set active code view
		self.app.active.scriptview = self
		
	def unfocused(self):
		# TODO hide toolbars
		pass
	
	
	def _cursorPositionChanged(self):
		# update location label
		line, column = cursor_location(self.editor.textCursor())
		self.label_location.setText('line {}, column {}'.format(line+1, column+1))
		# interaction with the results
		self._updatezone()
		
	def _updatezone(self):
		app = self.app
		cursor = self.editor.textCursor()
		
		if cursor.hasSelection():
			start, stop = cursor.selectionStart(), cursor.selectionEnd()
			for location in app.interpreter.locations.values():
				zone = astinterval(location)
				if start <= zone[0] <= stop or start <= zone[1] <= stop:
					start = min(start, zone[0])
					stop = max(stop, zone[0])
			below = (start, stop)
		else:
			below = app.posvar(cursor.position())
			if below:
				node = app.interpreter.locations[below]
				if not isinstance(node, ast.FunctionDef):
					below = astinterval(node)
				else:
					below = None
				
		if below:
			app.displayzones[id(self)] = below
		else:
			app.displayzones.pop(id(self), None)
		
		app.updatescript()
		if app.active_sceneview:
			app.active_sceneview.scene.sync()
	
	def _blockCountChanged(self):
		self.update_linenumbers()
		
	def sizeHint(self):
		return QSize(500,200)
	
	def resizeEvent(self, event):
		super().resizeEvent(event)

		# update the line number area
		nlines = max(1, self.editor.blockCount())
		digits = 1
		while nlines >= 10:		
			nlines //= 10
			digits += 1
		charwidth = QFontMetrics(self.font).maxWidth()
		border = charwidth//2
		width = (digits+3)*charwidth
		self.editor.setViewportMargins(width, 0, 0, 0)
		cr = self.editor.contentsRect()	# only this rect has the correct area, with the good margins with the real widget geometry
		self.linenumbers.setGeometry(QRect(cr.left(), cr.top(), width, cr.height()))
		self.linenumbers.width = width - border//2
		self.linenumbers.border = border
		self.linenumbers.update()
		self.editor.update()
		
	def show_linenumbers(self, visible):
		self.wlinenumbers.setVisible(visible)
		if visible:
			self.editor.setViewportMargins(width, 0, 0, 0)
		else:
			self.editor.setViewportMargins(0, 0, 0, 0)
		
		
	def update_colors(self):
		palette = self.editor.palette()
		palette.setColor(QPalette.Base, vec_to_color(settings.scriptview['background']))
		self.editor.setPalette(palette)
		self.highlighter = Highlighter(self.editor.document(), self.font)
		
		
	def fontsize_increase(self):
		self.font.setPointSize(self.font.pointSize() + 1)
		self.highlighter = Highlighter(self.editor.document(), self.font)
	
	def fontsize_decrease(self):
		self.font.setPointSize(self.font.pointSize() - 1)
		self.highlighter = Highlighter(self.editor.document(), self.font)
		
	def seek_line(self, lineno):
		''' set cursor and scroll to lineno '''
		block = self.editor.document().findBlockByLineNumber(lineno-1)
		cursor = QTextCursor(block)
		cursor.movePosition(QTextCursor.EndOfLine)
		self.editor.setTextCursor(cursor)
		self.editor.ensureCursorVisible()
	
	def seek_position(self, position):
		''' set cursor and scroll to position '''
		cursor = QTextCursor(self.editor.document())
		cursor.setPosition(position)
		self.editor.setTextCursor(cursor)
		self.editor.ensureCursorVisible()


class LineNumbers(QWidget):
	''' line number display for the text view '''
	def __init__(self, font, parent):
		super().__init__(parent)
		self.font = font
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
		s = settings.scriptview
		self.fmt_default = charformat(foreground=vec_to_color(s['normal_color']), font=font)
		self.fmt_keyword = charformat(foreground=vec_to_color(s['keyword_color']), font=font, weight=QFont.ExtraBold)
		self.fmt_call = charformat(foreground=vec_to_color(s['call_color']), font=font)
		self.fmt_constant = charformat(foreground=vec_to_color(s['number_color']), font=font)
		self.fmt_string = charformat(foreground=vec_to_color(s['string_color']), font=font)
		self.fmt_comment = charformat(foreground=vec_to_color(s['comment_color']), font=font, italic=True, weight=QFont.Thin)
		self.fmt_operator = charformat(foreground=vec_to_color(s['operator_color']), font=font)
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
			
	keywords = {'pass', 'and', 'or', 'if', 'elif', 'else', 'match', 'for', 'while', 'break', 'continue', 'is', 'in', 'not', 'def', 'lambda', 'class', 'yield', 'async', 'await', 'with', 'try', 'except', 'finally', 'raise', 'from', 'import', 'as', 'with', 'return', 'assert'}
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
	
	def highlightBlock_(self, text):
		#print('highlightBlock', type(text), text)
		self.setFormat(0, len(text), self.fmt_default)
		for pattern, func in self.patterns:
			start = 0
			while True:
				match = pattern.search(text, start)
				if match:
					start = func(match)+1
				else:
					break
	
	def highlightBlock(self, text):
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
