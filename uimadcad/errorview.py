from PyQt5.QtCore import Qt, QSize
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QSizePolicy, 
							QCheckBox, QLabel, QPushButton, QPlainTextEdit,
							)
from PyQt5.QtGui import QColor, QPalette, QFont, QFontMetrics, QTextOption, QIcon
import traceback
import textwrap
from madcad.nprint import nprint, nformat

from .common import *
from . import settings
from PyQt5.QtWidgets import QSplitter

class ErrorView(QWidget):
	tabsize = 4
	
	def __init__(self, main, exception=None, parent=None):
		super().__init__(parent)
		self._text = QPlainTextEdit()
		self._scope = QPlainTextEdit()
		self._label = QLabel('(no exception)')
		self._keepchk = QCheckBox('keep apart')
		self._sourcebtn = QPushButton('source')
		self._showscope = QPushButton('scope')
		self.main = main
		self.exception = exception
		self.font = QFont(*settings.scriptview['font'])
		
		self._keepchk.setSizePolicy(QSizePolicy(QSizePolicy.Maximum, QSizePolicy.Maximum))
				
		# ui layout
		lower = QWidget()
		layout = QHBoxLayout()
		layout.setContentsMargins(0,0,0,0)
		layout.addWidget(self._keepchk)
		layout.addWidget(self._sourcebtn)
		layout.addWidget(self._showscope)
		layout.addWidget(self._label)
		lower.setLayout(layout)
		
		splitter = QSplitter(self)
		splitter.setOrientation(Qt.Vertical)
		splitter.addWidget(self._text)
		splitter.addWidget(self._scope)
		
		layout = QVBoxLayout()
		layout.setContentsMargins(0,0,0,0)
		layout.addWidget(splitter)
		layout.addWidget(lower)
		self.setLayout(layout)
		
		# configure the window (if this widget is)
		self.setWindowFlags(Qt.WindowStaysOnTopHint)
		self.setWindowOpacity(0.8)
		self.resize(QSize(480,150) * self.font.pointSize()/7)
		self.setWindowIcon(QIcon.fromTheme('dialog-warning'))
		# configure the text options
		self._text.setSizePolicy(QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding))
		self._text.setTextInteractionFlags(Qt.TextBrowserInteraction)
		self._text.setWordWrapMode(QTextOption.WrapMode.NoWrap)
		self._text.setCurrentCharFormat(charformat(font=self.font))
		self._text.setTabStopDistance(settings.scriptview['tabsize'] * QFontMetrics(self.font).maxWidth())
		self._text.cursorPositionChanged.connect(lambda: self.showscope(self._showscope.isChecked()))
		
		self._scope.setVisible(False)
		self._scope.setTextInteractionFlags(Qt.TextBrowserInteraction)
		self._scope.setWordWrapMode(QTextOption.WrapMode.NoWrap)
		self._scope.setCurrentCharFormat(charformat(font=self.font))
		self._scope.setTabStopDistance(settings.scriptview['tabsize'] * QFontMetrics(self.font).maxWidth()+1.5)
		# configure the label
		self._label.setFont(self.font)
		self._label.setWordWrap(True)
		self._label.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
		# configure the button
		self._sourcebtn.setSizePolicy(QSizePolicy(QSizePolicy.Fixed, QSizePolicy.Minimum))
		self._sourcebtn.clicked.connect(self.showsource)
		
		self._showscope.setSizePolicy(QSizePolicy(QSizePolicy.Fixed, QSizePolicy.Minimum))
		self._showscope.setCheckable(True)
		self._showscope.clicked.connect(self.showscope)
		
		if exception:
			self.set(exception)
	
	def set(self, exception):
		''' set the exception to display '''
		self.exception = exception
		# set labels
		self.setWindowTitle(type(exception).__name__)
		self._label.setText('<b style="color:#ff5555">{}:</b> {}'.format(
								type(exception).__name__, str(exception).replace('<', '&lt;').replace('>', '&gt;')))
		#'\n'.join(textwrap.wrap(str(exception), 24))) 
		# set text
		doc = self._text.document()
		doc.clear()
		cursor = QTextCursor(doc)
		palette = self._text.palette()
		fmt_traceback = charformat(font=self.font, foreground=palette.color(QPalette.Text))
		fmt_code = charformat(font=self.font, foreground=mixcolors(
						palette.color(QPalette.Text), 
						palette.color(QPalette.Background),
						0.5))
		fmt_error = charformat(font=self.font, background=mixcolors(
						QColor(255,100,100),
						palette.color(QPalette.Background),
						0.2))
		if type(exception) == SyntaxError and exception.filename == self.main.interpreter.name:
			cursor.insertText('  File \"{}\", line {}\n'.format(exception.filename, exception.lineno), fmt_traceback)
			offset = exception.offset
			while offset > 0 and exception.text[offset-1].isalnum():	offset -= 1
			cursor.insertText('    '+exception.text[:offset], fmt_code)
			cursor.insertText(exception.text[offset:], fmt_error)
		else:
			tb = traceback.extract_tb(exception.__traceback__)
			i = next((i for i in range(len(tb)) if tb[i].filename == self.main.interpreter.name), 0)
			for line in traceback.format_list(tb)[i:]:
				if line.startswith('    '):
					cursor.insertText(line, fmt_code)
				else:
					endline = line.find('\n')
					cursor.insertText(line[:endline], fmt_traceback)
					cursor.insertText(line[endline:], fmt_code)
		
		# scroll on the end of the error message (most of the time the most interesting part)
		cursor = self._text.textCursor()
		cursor.movePosition(QTextCursor.End)
		self._text.setTextCursor(cursor)
		self._text.ensureCursorVisible()
		self.setVisible(True)
		
		if type(self.exception) == SyntaxError and self.exception.filename == self.main.interpreter.name:
			self.line = self.exception.lineno
		else:
			step = self.exception.__traceback__
			self.line = -1
			while step:
				if step.tb_frame.f_code.co_filename == self.main.interpreter.name:
					self.line = step.tb_frame.f_lineno
					break
				step = step.tb_next
				
		self._sourcebtn.setVisible(self.line >= 0)
		
	def showsource(self):
		if self.line >= 0:
			self.main.active_scriptview.seek_line(self.line-1)
			self.main.active_scriptview.editor.activateWindow()
			self.main.active_scriptview.editor.setFocus()
		else:
			print('no source to display in this traceback')
			
	def showscope(self, enable):
		if enable and self.exception.__traceback__:
			n = self._text.textCursor().blockNumber() //2
			print(self._text.textCursor().blockNumber() , n)
			
			step = self.exception.__traceback__
			for i in range(n+1):
				if step.tb_next:
					step = step.tb_next
			scope = step.tb_frame.f_locals
		
			self._scope.document().clear()
			cursor = QTextCursor(self._scope.document())
			palette = self.palette()
			familly, size = settings.scriptview['font']
			
			fmt_value = charformat(
							font=QFont(familly, size), 
							foreground=palette.text())
			fmt_key = charformat(
							font=QFont(familly, size*1.2, weight=QFont.Bold), 
							foreground=palette.link())
			
			if isinstance(scope, dict):
				for key in scope:
					formated = nformat(repr(scope[key]))
					# one line format
					if not '\n' in formated:	
						cursor.insertText((key+':').ljust(16), fmt_key)
						cursor.insertText(formated+'\n', fmt_value)
					# multiline format
					else:
						cursor.insertText(key+':', fmt_key)
						cursor.insertText(('\n'+formated).replace('\n', '\n    ')+'\n', fmt_value)
		self._scope.setVisible(enable)
	
	@property
	def keep(self):	
		''' whether the error window is marked to be keept as-is '''
		return self._keepchk.isChecked()
		
	def keyPressEvent(self, evt):
		if evt.key() == Qt.Key_Escape:		self.close()
		
	def closeEvent(self, evt):
		if self.main.active_errorview is self:
			self.main.active_errorview = None
		evt.accept()

	

		
