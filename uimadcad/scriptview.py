from PyQt5.QtCore import (
		Qt, QSize, QRect, QPoint, QPointF, QMargins,
		QEvent, pyqtSignal,
		)
from PyQt5.QtWidgets import (
		QVBoxLayout, QWidget, QHBoxLayout, QStyleFactory, QSplitter, QSizePolicy, QAction, 
		QTextEdit, QPlainTextEdit, QPlainTextDocumentLayout, 
		QPushButton, QLabel, QComboBox, QToolBar,
		QMainWindow, QDockWidget,
		)
from PyQt5.QtGui import (
		QFont, QFontMetrics, 
		QColor, QPalette, 
		QSyntaxHighlighter, QTextCharFormat,
		QIcon, QKeySequence, 
		QTextOption, QTextDocument, QTextCursor,
		QPainter, QPainterPath,
		)
from .common import *
from .interpreter import astinterval
from .settings import ctq
from . import settings
from madcad.nprint import nprint
from bisect import bisect_left
import ast
import re



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
	''' text editor part of the main frame '''
	
	# NOTE:	for unknow reasons, a widget created as child of QPlainTextEdit is rendered only if created in the __init__
	
	def __init__(self, main, parent=None):
		# current widget aspects
		super().__init__(parent)
		#self.setSizePolicy(QSizePolicy(QSizePolicy.Maximum, QSizePolicy.Expanding))
		
		self.main = main
		self.font = QFont(*settings.scriptview['font'])
		
		# text editor widget
		self.editor = TextEdit()
		self.editor.setDocument(main.script)
		self.editor.setWordWrapMode(QTextOption.WrapMode.WordWrap 
									if settings.scriptview['linewrap'] else 
									QTextOption.WrapMode.NoWrap)
		self.editor.setTabStopDistance(settings.scriptview['tabsize'] * QFontMetrics(self.font).averageCharWidth()+1.5)
		
		# text coloring
		self.update_colors()
		
		# visual options
		self.linenumbers = settings.scriptview['linenumbers']
		self.wlinenumbers = LineNumbers(self.font, self.editor)
		
		# execution target
		self.targetcursor = TargetCursor(main, self.editor)
		
		# set cursor position on openning
		if main.active_scriptview:
			self.editor.setTextCursor(main.active_scriptview.editor.textCursor())
		else:
			self.editor.moveCursor(QTextCursor.End)
		
		# toolbar
		self.toolbar = toolbar = QWidget()
		self.label_location = QLabel('line 1, column 1')
		self.label_execution = QLabel('READY')
		self.label_execution.setToolTip('execution state')
		self.trigger_mode = QComboBox()
		self.trigger_mode.addItem('manual')
		self.trigger_mode.addItem('on line change')
		self.trigger_mode.addItem('on each type')
		self.trigger_mode.setFrame(False)
		self.trigger_mode.setCurrentIndex(main.exectrigger)
		self.trigger_mode.setToolTip('execution trigger')
		button_close = QPushButton(QIcon.fromTheme('dialog-close-icon'), '')
		button_close.setToolTip('close view')
		button_close.setFlat(True)
		button_close.setSizePolicy(QSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed))
		button_close.clicked.connect(self.close)
		layout = QHBoxLayout()
		layout.addWidget(self.label_location)
		layout.addWidget(self.label_execution)
		layout.addWidget(self.trigger_mode)
		layout.addWidget(button_close)
		toolbar.setLayout(layout)
		
		self.quick = QToolBar('quick', self.editor)
		self.quick.setOrientation(Qt.Vertical)
		self.quick.addAction(QIcon.fromTheme('document-save'), 'save', main._save)
		self.quick.addAction(QIcon.fromTheme('edit-undo'), 'undo', main.script.undo)
		self.quick.addAction(QIcon.fromTheme('edit-redo'), 'redo', main.script.redo)
		self.quick.addSeparator()
		self.quick.addAction(QIcon.fromTheme('format-indent-more'), 'disable line', main._commentline)
		self.quick.addAction(QIcon.fromTheme('format-indent-less'), 'enable line', main._uncommentline)
		self.quick.addAction(QIcon.fromTheme('view-list-tree'), 'disable line dependencies +', lambda: None)
		self.quick.addAction('def', main._createfunction)
		self.quick.addAction('list', main._createlist)
		self.quick.addSeparator()
		self.quick.addAction(QIcon.fromTheme('go-bottom'), 'target to cursor', main._targettocursor)
		self.quick.addAction(QIcon.fromTheme('media-playback-start'), 'execute', main.execute)
		self.quick.addAction(QIcon.fromTheme('go-jump'), 'edit function', main._enterfunction)
		self.quick.addSeparator()		
		self.quick.addAction(QIcon.fromTheme('view-list-tree'), 'reformat code', main._reformatcode)
		self.quick.addAction(QIcon.fromTheme('edit-find'), 'find +', lambda: None)
		self.quick.hide()
		
		
		# global layout
		layout = QVBoxLayout(spacing=0)
		layout.addWidget(PathBar(main))
		layout.addWidget(self.editor)
		layout.setContentsMargins(QMargins(0,0,0,0))
		self.setLayout(layout)
				
		# setup editor
		self.editor.cursorPositionChanged.connect(self._cursorPositionChanged)
		self.editor.blockCountChanged.connect(self._blockCountChanged)
		self.editor.updateRequest.connect(self.update_linenumbers)
		main.exectarget_changed.connect(self.targetcursor.update)
		main.executed.connect(self._updatezone)
		
		main.views.append(self)
		if not main.active_scriptview:	main.active_scriptview = self
		
	def changeEvent(self, event):
		# detect QDockWidget integration
		if event.type() == event.ParentChange:
			if isinstance(self.parent(), QDockWidget):
				self.parent().setTitleBarWidget(self.toolbar)
				self.layout().removeWidget(self.toolbar)
			else:
				self.layout().addWidget(self.toolbar)
		# detect theme change
		if event.type() == QEvent.PaletteChange and settings.scriptview['system_theme']:
			settings.use_qt_colors()
			self.update_colors()
		return super().changeEvent(event)
	
	def closeEvent(self, event):
		self.main.views.remove(self)
		if self.main.active_scriptview is self:
			self.main.active_scriptview = None
		if isinstance(self.parent(), QDockWidget):
			self.main.mainwindow.removeDockWidget(self.parent())
		else:
			super().close()
			
	def enterEvent(self, event):
		if settings.view['quick_toolbars']:	
			self.quick.show()
		
	def leaveEvent(self, event):
		if not self.editor.hasFocus():	
			self.quick.hide()
	
	def focused(self):
		# set active code view
		self.main.active_scriptview = self
		# update exectrigger and exectarget
		self.main.exectrigger = mode = self.trigger_mode.currentIndex()
		
	def unfocused(self):
		self.quick.hide()
	
	
	def _cursorPositionChanged(self):
		# update location label
		line, column = cursor_location(self.editor.textCursor())
		self.label_location.setText('line {}, column {}'.format(line+1, column+1))
		# interaction with the results
		self._updatezone()
		
	def _updatezone(self):
		main = self.main
		cursor = self.editor.textCursor()
		
		if cursor.hasSelection():
			start, stop = cursor.selectionStart(), cursor.selectionEnd()
			for location in main.interpreter.locations.values():
				zone = astinterval(location)
				if start <= zone[0] <= stop or start <= zone[1] <= stop:
					start = min(start, zone[0])
					stop = max(stop, zone[0])
			below = (start, stop)
		else:
			below = main.posvar(cursor.position())
			if below:
				node = main.interpreter.locations[below]
				if not isinstance(node, ast.FunctionDef):
					below = astinterval(node)
				else:
					below = None
				
		if below:
			main.displayzones[id(self)] = below
		else:
			main.displayzones.pop(id(self), None)
		
		main.updatescript()
		if main.active_sceneview:
			main.active_sceneview.scene.sync()
	
	def _blockCountChanged(self):
		self.update_linenumbers()
		
	def sizeHint(self):
		return QSize(500,200)
	
	def resizeEvent(self, event):
		super().resizeEvent(event)
		self.update_linenumbers()
		size = self.editor.size()
		bar = 15
		width = self.quick.sizeHint().width()
		self.quick.setGeometry(QRect(size.width()-bar-width, 0, width, size.height()-bar))

	def update_linenumbers(self):
		# update the line number area
		if self.linenumbers:
			nlines = max(1, self.editor.blockCount())
			digits = 1
			while nlines >= 10:		
				nlines /= 10
				digits += 1
			charwidth = QFontMetrics(self.font).maxWidth()
			border = charwidth/2
			width = (digits+3)*charwidth
			self.editor.setViewportMargins(width, 0, 0, 0)
			cr = self.editor.contentsRect()	# only this rect has the correct area, with the good margins with the real widget geometry
			self.wlinenumbers.setGeometry(QRect(cr.left(), cr.top(), width, cr.height()))
			self.wlinenumbers.width = width - border/2
			self.wlinenumbers.border = border
			self.wlinenumbers.setVisible(True)
			self.wlinenumbers.update()
		else:
			self.wlinenumbers.setVisible(False)
			self.editor.setViewportMargins(0, 0, 0, 0)
		self.editor.update()
		
	def update_colors(self):
		palette = self.editor.palette()
		palette.setColor(QPalette.Base, ctq(settings.scriptview['background']))
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
		top = view.blockBoundingGeometry(block).translated(view.contentOffset()).top()
		charwidth = QFontMetrics(self.font).maxWidth()
		while block.isValid() and top <= zone.bottom():
			if block.isVisible() and top >= zone.top():
				height = view.blockBoundingRect(block).height()
				painter.setFont(self.font)
				painter.drawText(0, top, self.width-2*charwidth, height, Qt.AlignRight, str(block.blockNumber()+1))
				top += height
			block = block.next()

class PathBar(QWidget):
	def __init__(self, main, parent=None):
		super().__init__(parent)
		self.main = main
		
		# path widget
		self.wpath = PathWidget()
		#self.wpath.setFont(QFont(*settings.scriptview['font']))
		main.scope_changed.connect(self.update_path)
		self.wpath.clicked.connect(self.move_cursor)
		
		# return button
		btn = QPushButton(QIcon.fromTheme('draw-arrow-back'), '')
		btn.setToolTip('return to upper context')
		#btn.setFlat(True)
		btn.setSizePolicy(QSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed))
		btn.setContentsMargins(QMargins(0,0,0,0))
		btn.resize(QSize(10,10))
		btn.clicked.connect(main._returnfunction)
		
		layout = QHBoxLayout(spacing=0)
		layout.setContentsMargins(QMargins(6,0,6,0))
		layout.addSpacing(16)
		#lbl = QLabel()
		#lbl.setPixmap(QIcon.fromTheme('code-function').pixmap(16,16))
		#layout.addWidget(lbl)
		#layout.addSpacing(5)
		layout.addWidget(self.wpath)
		layout.addWidget(btn)
		self.setLayout(layout)
		self.setSizePolicy(QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed))
		
		self.update_path()
		
	def update_path(self):
		self.wpath.path = [scope[4]	for scope in self.main.scopes]
		if self.wpath.path:
			self.show()
			self.wpath.update()
		else:
			self.hide()
		
	def move_cursor(self, index):
		editor = self.main.active_scriptview.editor
		cursor = editor.textCursor()
		cursor.setPosition(self.main.scopes[index][5])
		editor.setTextCursor(cursor)
		editor.ensureCursorVisible()
		
		
class PathWidget(QWidget):
	clicked = pyqtSignal(int)
	
	def __init__(self, path=None, parent=None):
		super().__init__(parent)
		self.setSizePolicy(QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed))
		self.path = path or ()
		
		self.metric = QFontMetrics(self.font())
		self.separator = sep = QPainterPath()
		h = self.metric.height()
		sep.moveTo(0, 0.25*h)
		sep.lineTo(0.25*h, 0.55*h)
		sep.lineTo(0.25*h, 0.55*h)
		sep.lineTo(0, 0.85*h)
		sep.translate(0.4,0)
		
		self.zones = []
		
	def sizeHint(self):
		return QSize(100,self.metric.height())
		
	def paintEvent(self, event):
		painter = QPainter(self)
		painter.setRenderHint(painter.Antialiasing)
		font = QFontMetrics(self.font())
		palette = self.palette()
		h = font.height()
		
		pen = painter.pen()
		pen.setJoinStyle(Qt.BevelJoin)
		pen.setWidth(0.1*h)
		pen.setColor(palette.color(QPalette.ButtonText))
		painter.setPen(pen)
		self.zones = []
		x = 2
		for e in self.path:
			painter.drawPath(self.separator.translated(QPoint(x,0)))
			x += h*0.8
			painter.drawText(x, font.height() - font.descent(), e)
			x += font.horizontalAdvance(e) + h*0.6
			self.zones.append(x)
			
	def mouseReleaseEvent(self, evt):
		if evt.button() == Qt.LeftButton:
			x = evt.pos().x()
			self.clicked.emit(bisect_left(self.zones, x))
			evt.accept()


class TargetCursor(QWidget):
	''' target cursor display for the text view 
		version fixed to text
	'''
	background = QColor(10,10,10)
	targetcolor = QColor(40,100,40)
	font = QFont('NotoMono', 7)
	text = '>>  target'
	
	def __init__(self, main, parent):
		super().__init__(parent)
		self.setAttribute(Qt.WA_TransparentForMouseEvents)	# keep all the mouse events for the text view, (none will reach this widget :-/)
		self.main = main
		fontmetrics = QFontMetrics(self.font)
		h = fontmetrics.height()
		w = fontmetrics.horizontalAdvance(self.text)
		self.shape = s = QPainterPath()
		s.moveTo(h, 0)
		s.lineTo(h, 0)
		s.lineTo(h+w+h, 0)
		s.lineTo(h+w, h)
		s.lineTo(0, h)
		self.box = s.boundingRect().toRect()
		self.textstart = QPointF(h, 0.8*h)
		self.cursoroffset = QPointF(2*h, 0)
	
	def sizeHint(self):
		return self.parent().size()
	
	def update(self):
		self.setGeometry(self.parent().contentsRect())
		super().update()
	
	#def mouseMoveEvent(self, event):
		#print('coucou')
		#cursor = self.parent().cursorForPosition(event.pos() + self.pos())
		#self.main.exectarget = cursor.blockNumber()
		#self.update()
		#event.ignore()
	
	def paintEvent(self, event):
		cursor = QTextCursor(self.main.script)
		cursor.setPosition(self.main.exectarget)
		pos = (		self.parent().cursorRect(cursor).topRight()
				+	QPointF(self.parent().viewportMargins().left(), 0) 
				+	self.cursoroffset
				)
		if event.rect().contains(pos.toPoint()):
			painter = QPainter(self)
			painter.setRenderHint(painter.Antialiasing)
			painter.fillPath(self.shape.translated(pos), self.targetcolor)
			painter.setPen(self.background)
			painter.setFont(self.font)
			painter.drawText(self.textstart + pos, self.text)


class TargetCursor2(QWidget):
	''' target cursor for text view
		version with the label not fixed to text
	'''
	background = QColor(10,10,10)
	targetcolor = QColor(40,100,40)
	text = '>>  target'
	
	def __init__(self, main, parent):
		super().__init__(parent)
		self.main = main
		fontmetrics = QFontMetrics(self.font())
		h = fontmetrics.height()
		w = fontmetrics.horizontalAdvance(self.text)
		self.shape = s = QPainterPath()
		s.moveTo(h, 0)
		s.lineTo(h, 0)
		s.lineTo(h+w+h, 0)
		s.lineTo(h+w, h)
		s.lineTo(0, h)
		self.box = s.boundingRect().toRect()
		self.textstart = QPointF(h, 0.75*h)
		self.cursoroffset = QPointF(2*h, 0)
	
	def sizeHint(self):
		return self.box().size()
	
	def update(self):
		cursor = QTextCursor(self.main.script)
		cursor.setPosition(self.main.exectarget)
		pos = (		self.parent().cursorRect(cursor).topRight() 
				+	self.parent().contentOffset() 
				+	QPointF(self.parent().viewportMargins().left(), 0) 
				+	self.cursoroffset
				).toPoint()
		self.setGeometry(self.box.translated(pos))
		super().update()
	
	def mouseMoveEvent(self, event):
		cursor = self.parent().cursorForPosition(event.pos() + self.pos())
		self.main.exectarget = cursor.blockNumber()
		self.update()
			
	def paintEvent(self, event):
		painter = QPainter(self)
		painter.fillPath(self.shape, self.targetcolor)
		painter.setPen(self.background)
		painter.drawText(self.textstart, self.text)

class FunctionCursor(QWidget):
	''' target cursor display for the text view 
		version fixed to text
	'''
	background = QColor(10,10,10)
	targetcolor = QColor(40,100,40)
	font = QFont('NotoMono', 7)
	text = 'function'
	
	def __init__(self, main, parent):
		super().__init__(parent)
		self.setAttribute(Qt.WA_TransparentForMouseEvents)	# keep all the mouse events for the text view, (none will reach this widget :-/)
		self.main = main
		fontmetrics = QFontMetrics(self.font)
		h = fontmetrics.height()
		w = fontmetrics.horizontalAdvance(self.text)
		self.shape = s = QPainterPath()
		s.moveTo(0.5*h, 0)
		s.lineTo(0, 0.5*h)
		s.lineTo(0.5*h, h)
		s.lineTo(h+w+h, h)
		s.lineTo(h+w+h, 0)
		s.lineTo(0.5*h, 0)
		self.textstart = QPointF(h, 0.8*h)
		self.cursoroffset = QPointF(0.5*h, 0)
	
	def sizeHint(self):
		return self.parent().size()
	
	def update(self):
		self.setGeometry(self.parent().contentsRect())
		super().update()
	
	#def mouseMoveEvent(self, event):
		#print('coucou')
		#cursor = self.parent().cursorForPosition(event.pos() + self.pos())
		#self.main.exectarget = cursor.blockNumber()
		#self.update()
		#event.ignore()
	
	def paintEvent(self, event):
		cursor = QTextCursor(self.main.script)
		cursor.setPosition(self.main.exectarget)
		pos = (		self.parent().cursorRect(cursor).topRight()
				+	QPointF(self.parent().viewportMargins().left(), 0) 
				+	self.cursoroffset
				)
		if event.rect().contains(pos.toPoint()):
			painter = QPainter(self)
			painter.setRenderHint(painter.Antialiasing)
			painter.fillPath(self.shape.translated(pos), self.targetcolor)
			painter.setPen(self.background)
			painter.setFont(self.font)
			painter.drawText(self.textstart + pos, self.text)


class Highlighter(QSyntaxHighlighter):
	''' python syntax highlighter for QTextDocument '''
	def __init__(self, document, font):
		super().__init__(document)
		s = settings.scriptview
		self.fmt_default = charformat(foreground=ctq(s['normal_color']), font=font)
		self.fmt_keyword = charformat(foreground=ctq(s['keyword_color']), font=font, weight=QFont.ExtraBold)
		self.fmt_call = charformat(foreground=ctq(s['call_color']), font=font)
		self.fmt_constant = charformat(foreground=ctq(s['number_color']), font=font)
		self.fmt_string = charformat(foreground=ctq(s['string_color']), font=font)
		self.fmt_comment = charformat(foreground=ctq(s['comment_color']), font=font, italic=True, weight=QFont.Thin)
		self.fmt_operator = charformat(foreground=ctq(s['operator_color']), font=font)
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
			
	keywords = {'pass', 'and', 'or', 'if', 'elif', 'else', 'for', 'while', 'break', 'continue', 'is', 'in', 'not', 'def', 'lambda', 'class', 'yield', 'async', 'await', 'with', 'try', 'except', 'finally', 'raise', 'from', 'import', 'as', 'with', 'return', 'assert'}
	constants = {'None', 'True', 'False'}
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

