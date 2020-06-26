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
		self.text = QPlainTextEdit()
		self.label = QLabel('(no error)')
		self.keepchk = QCheckBox('keep apart')
		self.main = main
		
		lower = QWidget()
		layout = QHBoxLayout()
		layout.addWidget(self.keepchk)
		layout.addWidget(self.label)
		lower.setLayout(layout)
		layout = QVBoxLayout()
		layout.addWidget(self.text)
		layout.addWidget(lower)
		self.setLayout(layout)
		
		self.setWindowFlags(Qt.WindowStaysOnTopHint)
		self.setWindowOpacity(0.6)
		self.resize(QSize(480,150) * self.font.pointSize()/7)
		
		self.text.setSizePolicy(QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding))
		self.text.setTextInteractionFlags(Qt.TextBrowserInteraction)
		self.text.setWordWrapMode(QTextOption.WrapMode.NoWrap)
		self.text.setTabStopDistance(self.tabsize * QFontMetrics(self.font).maxWidth())
		self.text.setCurrentCharFormat(charformat(font=self.font))
		self.label.setFont(self.font)
		
		if error:
			self.set(error)
	
	def set(self, error):
		self.setWindowTitle(type(error).__name__)
		self.text.setPlainText(
			''.join(traceback.TracebackException.from_exception(error).format())
			)
		self.label.setText('<b style="color:#ff5555">{}:</b> {}'.format(type(error).__name__, str(error)))
		cursor = self.text.textCursor()
		cursor.movePosition(QTextCursor.End)
		self.text.setTextCursor(cursor)
		self.text.ensureCursorVisible()
		self.setVisible(True)
	
	@property
	def keep(self):	
		return self.keepchk.isChecked()
		
	def keyPressEvent(self, evt):
		if evt.key() == Qt.Key_Escape:		self.close()
		
	def closeEvent(self, evt):
		if self.main.active_errorview is self:
			self.main.active_errorview = None
		evt.accept()

	

		
