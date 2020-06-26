from PyQt5.QtCore import Qt, QSize
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QSizePolicy, QCheckBox, QLabel, QPlainTextEdit
from PyQt5.QtGui import QFont, QColor, QFontMetrics, QTextOption
import traceback
from common import *

class ErrorView(QWidget):
	tabsize = 4
	font = QFont('NotoMono', 7)
	
	def __init__(self, main, error=None, parent=None):
		super().__init__(parent)
		self._text = QPlainTextEdit()
		self._label = QLabel('(no error)')
		self._keepchk = QCheckBox('keep apart')
		self.main = main
		
		# ui layout
		lower = QWidget()
		layout = QHBoxLayout()
		layout.addWidget(self._keepchk)
		layout.addWidget(self._label)
		lower.setLayout(layout)
		layout = QVBoxLayout()
		layout.addWidget(self._text)
		layout.addWidget(lower)
		self.setLayout(layout)
		
		# configure the window (if this widget is)
		self.setWindowFlags(Qt.WindowStaysOnTopHint)
		self.setWindowOpacity(0.6)
		self.resize(QSize(480,150) * self.font.pointSize()/7)
		# configure the text options
		self._text.setSizePolicy(QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding))
		self._text.setTextInteractionFlags(Qt.TextBrowserInteraction)
		self._text.setWordWrapMode(QTextOption.WrapMode.NoWrap)
		self._text.setTabStopDistance(self.tabsize * QFontMetrics(self.font).maxWidth())
		self._text.setCurrentCharFormat(charformat(font=self.font))
		# configure the label
		self._label.setFont(self.font)
		
		if error:
			self.set(error)
	
	def set(self, error):
		''' set the exception to display '''
		# set texts
		self.setWindowTitle(type(error).__name__)
		self._text.setPlainText(
			''.join(traceback.TracebackException.from_exception(error).format())
			)
		self._label.setText('<b style="color:#ff5555">{}:</b> {}'.format(type(error).__name__, str(error)))
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

	

		
