from PyQt5.QtCore import Qt, QSize, QPoint
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QSizePolicy, 
							QCheckBox, QLabel, QPushButton, QTextEdit,
							QAction,
							)
from PyQt5.QtGui import QColor, QPalette, QFont, QFontMetrics, QTextOption, QIcon, QKeySequence
from nprint import nformat

from .common import *


class DetailView(QWidget):
	tabsize = 5
	fmt_value = charformat(
					font=QFont('NotoMono', 7), 
					foreground=QColor(255,255,255))
	fmt_key = charformat(
					font=QFont('NotoMono', 9, weight=QFont.Bold), 
					foreground=QColor(100, 200, 255))
	
	
	def __init__(self, main, ident, parent=None):
		super().__init__(parent)
		# setup ui
		self._text = QTextEdit()
		self._bar = QWidget()
		self._btnfold = QPushButton('fold all +', self._bar)
		self._btnpin = QCheckBox('keep visible', self._bar)
		layout = QVBoxLayout()
		layout.setContentsMargins(0,0,0,0)
		layout.addWidget(self._btnfold)
		layout.addWidget(self._btnpin)
		self._bar.setLayout(layout)
		layout = QHBoxLayout()
		layout.setContentsMargins(0,0,0,0)
		layout.addWidget(self._text)
		layout.addWidget(self._bar)
		self.setLayout(layout)
		
		esc = QAction('close', self, shortcut=QKeySequence('Escape'))
		esc.triggered.connect(self.close)
		self.addAction(esc)
		
		font = self.fmt_value.font()
		
		# register to main
		self.main = main
		self.ident = ident
		main.details[ident] = self
		main.views.append(self)
		
		# set window and ui settings
		self.setWindowFlags(Qt.Tool | Qt.WindowStaysOnTopHint)
		self.setWindowTitle('{}//   {}'.format(*ident))
		self.setWindowIcon(QIcon.fromTheme('madcad-grpinfo'))
		self.setSizePolicy(QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding))
		self.resize(QSize(300,80) * font.pointSize()/7)
		
		self._text.setTextInteractionFlags(Qt.TextBrowserInteraction)
		self._text.setWordWrapMode(QTextOption.WrapMode.NoWrap)
		self._text.setTabStopDistance(self.tabsize * QFontMetrics(font).maxWidth())
		
		# get the content
		self.sync()
	
	def foldall(self, fold=False):
		indev
		
	def sync(self, updated=None):
		''' sync the displayed informations with the main scene '''
		main = self.main
		grp, sub = self.ident
		# remove the current view if the referenced group doesn't exist
		if grp not in main.scene or not hasattr(main.scene[grp], 'groups') or sub >= len(main.scene[grp].groups):
			self.close()
			return
		# update the text view
		infos = main.scene[grp].groups[sub]
		self.info(infos)
		# add a marker to the scene
		#self.scenekey = '{}-detail{}'.format(grp,sub)
		#main.scene[self.scenekey] = DetailMarker(indev)
		#main.poses[self.scenekey] = main.poses[grp]
	
	def closeEvent(self, evt):
		evt.accept()
		# discard the used label
		if self.ident in self.main.details:
			del self.main.details[self.ident]
		# remove the group marker
		#if self.scenekey in self.main.scene:
			#del self.main.scene[scenekey]
			#self.main.updatescene()
		# unregister from views
		for i,view in enumerate(self.main.views):
			if view is self:
				self.main.views.pop(i)
	
	def dispose(self):
		''' close the detail window if it has not been pinned '''
		if not self._btnpin.isChecked():
			self.close()
	
	def info(self, infos):
		''' set the displayed informations '''
		cursor = QTextCursor(self._text.document())
		if isinstance(infos, dict):
			for key in sorted(list(infos)):
				formated = nformat(repr(infos[key]))
				# one line format
				if not '\n' in formated:	
					cursor.insertText((key+':').ljust(16), self.fmt_key)
					cursor.insertText(formated+'\n', self.fmt_value)
				# multiline format
				else:
					cursor.insertText(key+':', self.fmt_key)
					cursor.insertText(('\n'+formated).replace('\n', '\n    ')+'\n', self.fmt_value)
		else:
			cursor.insertText(nformat(repr(infos)), self.fmt_value)

