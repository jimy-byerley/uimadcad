from PyQt5.QtCore import (
		Qt, QSize, QRect, QPoint, QPointF,
		QEvent, pyqtSignal,
		)
from PyQt5.QtWidgets import (
		QVBoxLayout, QWidget, QHBoxLayout, QStyleFactory, QSplitter, QSizePolicy, QAction,
		QTextEdit, QPlainTextEdit, QPlainTextDocumentLayout, 
		QPushButton, QLabel, QComboBox,
		QMainWindow, QDockWidget,
		)
from PyQt5.QtGui import (
		QFont, QFontMetrics, 
		QColor, QPalette,
		QIcon, QKeySequence, 
		QTextOption, QTextDocument, QTextCursor,
		QPainter, QPainterPath,
		)
from .common import *
from nprint import nprint


class TextEdit(QPlainTextEdit):
	''' text editor widget for ScriptView, only here to change some QPlainTextEdit behaviors '''		
	def focusInEvent(self, event):
		self.parent().focused()
		super().focusInEvent(event)

class ScriptView(QWidget):
	''' text editor part of the main frame '''
	tabsize = 4
	wordwrap = QTextOption.WrapMode.NoWrap
	font = QFont('NotoMono', 7)
	currenthighlight = QColor(128,128,128)
	zonehighlight = QColor(50, 50, 0)
	edithighlight = QColor(20, 80, 0)
	background = QColor(0,0,0)
	
	def __init__(self, main, parent=None):
		# NOTE:	for unknow reasons, a widget created as child of QPlainTextEdit is rendered only if created in the __init__

		super().__init__(parent)
		self.main = main
		self.editor = TextEdit()
		self.editor.setDocument(main.script)
		self.editor.setWordWrapMode(self.wordwrap)
		self.editor.setTabStopDistance(self.tabsize * QFontMetrics(self.font).maxWidth())
		# default widget colors
		palette = self.editor.palette()
		palette.setColor(QPalette.Base, self.background)
		self.editor.setPalette(palette)
		self.highlighter = Highlighter(self.editor.document(), self.font)
		self.linenumbers = False
		self.wlinenumbers = LineNumbers(self.font, self.editor)
		#self.enable_linenumbers(True)
		self.targetcursor = TargetCursor(main, self.editor)
		
		# statusbar
		statusbar = QWidget()
		self.label_location = QLabel('line 1, column 1')
		self.label_execution = QLabel('READY')
		self.trigger_mode = QComboBox()
		self.trigger_mode.addItem('manual')
		self.trigger_mode.addItem('on line change')
		self.trigger_mode.addItem('on each type')
		self.trigger_mode.setFrame(False)
		self.trigger_mode.setCurrentIndex(main.exectrigger)
		button_close = QPushButton(QIcon.fromTheme('dialog-close-icon'), '')
		button_close.setSizePolicy(QSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed))
		button_close.setStyleSheet('''QPushButton {
    border-style: outset;
    border-width: 0px;
}''')
		button_close.clicked.connect(self.close)
		layout = QHBoxLayout()
		#layout.addWidget(QLabel('<b>Script</b>'))
		layout.addWidget(self.label_location)
		layout.addWidget(self.label_execution)
		layout.addWidget(self.trigger_mode)
		layout.addWidget(button_close)
		statusbar.setLayout(layout)
		self.statusbar = statusbar
		
		# global layout
		layout = QVBoxLayout()
		layout.addWidget(self.editor)
		self.setLayout(layout)
				
		# setup editor
		self.editor.cursorPositionChanged.connect(self._cursorPositionChanged)
		self.editor.blockCountChanged.connect(self._blockCountChanged)
		self.editor.updateRequest.connect(self.update_linenumbers)
		main.exectarget_changed.connect(self.targetcursor.update)
		main.executed.connect(self._executed)
		
		main.views.append(self)
		if not main.active_scriptview:	main.active_scriptview = self
	
	def focused(self):
		# set active code view
		self.main.active_scriptview = self
		# update exectrigger and exectarget
		self.main.exectrigger = mode = self.trigger_mode.currentIndex()
		
	def changeEvent(self, event):
		# detect QDockWidget integration
		if event.type() == event.ParentChange:
			if isinstance(self.parent(), QDockWidget):
				self.parent().setTitleBarWidget(self.statusbar)
				self.layout().removeWidget(self.statusbar)
			else:
				self.layout().addWidget(self.statusbar)
		return super().changeEvent(event)
	
	def closeEvent(self, event):
		self.main.views.remove(self)
	
	def _cursorPositionChanged(self):
		# update location label
		cursor = self.editor.textCursor()
		line, column = cursor_location(cursor)
		self.label_location.setText('line {}, column {}'.format(line+1, column+1))
		# interaction with the results
		self.main.cursorat(cursor.position())
	
	def _executed(self):
		self.main.cursorat(self.editor.textCursor().position())
	
	def _blockCountChanged(self):
		self.update_linenumbers()
	
	def resizeEvent(self, event):
		super().resizeEvent(event)
		self.update_linenumbers()

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
			width = (digits+1)*charwidth
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
	
	def close(self):
		self.main.views.remove(self)
		if isinstance(self.parent(), QDockWidget):
			self.main.removeDockWidget(self.parent())
		else:
			super().close()

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
		while block.isValid() and top <= zone.bottom():
			if block.isVisible() and top >= zone.top():
				height = view.blockBoundingRect(block).height()
				painter.setFont(self.font)
				painter.drawText(0, top, self.width, height, Qt.AlignRight, str(block.blockNumber()+1))
				top += height
			block = block.next()

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


from PyQt5.QtGui import QSyntaxHighlighter, QTextCharFormat, QColor
import re

class Highlighter(QSyntaxHighlighter):
	''' python syntax highlighter for QTextDocument '''
	def __init__(self, document, font):
		super().__init__(document)
		self.format = QTextCharFormat()
		self.format.setForeground(QColor(255,100,0))
		self.fmt_default = charformat(foreground=QColor(255,255,255), font=font)
		self.fmt_keyword = charformat(foreground=QColor(50,210,150), font=font)
		self.fmt_call = charformat(foreground=QColor(200,255,150), font=font)
		self.fmt_constant = charformat(foreground=QColor(50,100,255), font=font)
		self.fmt_string = charformat(foreground=QColor(100,200,255), font=font)
		self.fmt_comment = charformat(foreground=QColor(150,150,150), font=font, italic=True)
		self.fmt_operator = charformat(foreground=QColor(50,100,150), font=font)
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
			
	keywords = {'and', 'or', 'if', 'elif', 'else', 'for', 'while', 'in', 'not', 'def', 'class', 'yield', 'with', 'try', 'except', 'raise', 'return', 'from', 'import', 'as'}
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

