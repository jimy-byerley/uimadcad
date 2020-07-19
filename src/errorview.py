from PyQt5.QtCore import Qt, QSize
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QSizePolicy, 
							QCheckBox, QLabel, QPushButton, QPlainTextEdit,
							)
from PyQt5.QtGui import QColor, QPalette, QFont, QFontMetrics, QTextOption, QIcon
import traceback
from common import *

class ErrorView(QWidget):
	tabsize = 4
	font = QFont('NotoMono', 7)
	
	def __init__(self, main, exception=None, parent=None):
		super().__init__(parent)
		self._text = QPlainTextEdit()
		self._label = QLabel('(no exception)')
		self._keepchk = QCheckBox('keep apart')
		self._sourcebtn = QPushButton('source +')
		self.main = main
		self.exception = exception
		
		# ui layout
		lower = QWidget()
		layout = QHBoxLayout()
		layout.setContentsMargins(0,0,0,0)
		layout.addWidget(self._keepchk)
		layout.addWidget(self._sourcebtn)
		layout.addWidget(self._label)
		lower.setLayout(layout)
		layout = QVBoxLayout()
		layout.setContentsMargins(0,0,0,0)
		layout.addWidget(self._text)
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
		self._text.setTabStopDistance(self.tabsize * QFontMetrics(self.font).maxWidth())
		self._text.setCurrentCharFormat(charformat(font=self.font))
		# configure the label
		self._label.setFont(self.font)
		# configure the button
		self._sourcebtn.setSizePolicy(QSizePolicy(QSizePolicy.Fixed, QSizePolicy.Minimum))
		#self._sourcebtn.clicked.connect(self.showsource)	# TODO: retreive find the stack frame for the execution module, then we would have the line number
		
		if exception:
			self.set(exception)
	
	def set(self, exception):
		''' set the exception to display '''
		# set labels
		self.setWindowTitle(type(exception).__name__)
		self._label.setText('<b style="color:#ff5555">{}:</b> {}'.format(
								type(exception).__name__, str(exception)))
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
		if isinstance(exception, SyntaxError):
			cursor.insertText('  File \"{}\", line {}\n'.format(exception.filename, exception.lineno), fmt_traceback)
			offset = exception.offset
			while offset > 0 and exception.text[offset-1].isalnum():	offset -= 1
			cursor.insertText('    '+exception.text[:offset], fmt_code)
			cursor.insertText(exception.text[offset:], fmt_error)
		else:
			tb = traceback.extract_tb(exception.__traceback__)
			i = next((i for i in range(len(tb)) if tb[i].filename == self.main.interpreter.persistent.__name__), 0)
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

	

		
