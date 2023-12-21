from PyQt5.QtCore import Qt, QSize, QPoint, QMargins
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QSizePolicy, 
							QCheckBox, QLabel, QPushButton, QTextEdit,
							QShortcut,
							)
from PyQt5.QtGui import QColor, QPalette, QFont, QFontMetrics, QTextOption, QIcon, QKeySequence
from madcad.nprint import nformat
from madcad import Mesh, Web, note_label

from .common import *
from . import settings



class DetailView(QWidget):
	def __init__(self, scene, key, parent=None):
		from . import sceneview
		super().__init__(parent)
		# setup ui
		self._text = QTextEdit()
		layout = QHBoxLayout()
		layout.addWidget(self._text)
		layout.setContentsMargins(QMargins(0,0,0,0))
		self.setLayout(layout)
		self._text.setSizePolicy(QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding))
		
		self._esc = QShortcut(QKeySequence('Escape'), self)
		self._esc.activated.connect(self.close)
		
		font = QFont(*settings.scriptview['font'])
		
		# register to main
		self.scene = scene
		self.key = key
		scene.main.details[key] = self
		scene.main.views.append(self)
		
		# set window and ui settings
		self.setWindowTitle(sceneview.format_scenekey(self.scene, key))
		self.setWindowFlags(Qt.Tool | Qt.WindowStaysOnTopHint)
		self.setWindowIcon(QIcon.fromTheme('madcad-grpinfo'))
		self.setSizePolicy(QSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum))
		self.resize(QSize(300,10) * font.pointSize()/7)
		
		self._text.setTextInteractionFlags(Qt.TextBrowserInteraction)
		self._text.setWordWrapMode(QTextOption.WrapMode.NoWrap)
		self._text.setTabStopDistance(settings.scriptview['tabsize'] * QFontMetrics(font).maxWidth()+1.5)
		
		scene.main.executed.connect(self.sync)
		
		# get the content
		self.sync()
	
	def foldall(self, fold=False):
		indev
		
	def sync(self, updated=None):
		''' sync the displayed informations with the main scene '''
		try:				disp = self.scene.item(self.key)
		except IndexError:	disp = None
		except KeyError:	disp = None
		
		if disp and hasattr(disp, 'source') and isinstance(disp.source, (Mesh,Web)):
			sub = self.key[-1]
			markerkey = ('marker', self.key)
			self.info(disp.source.groups[sub])
			self.scene.additions[markerkey] = note_label(disp.source.group(sub), text=str(sub), style='circle')
			if len(self.key) > 2:
				self.scene.poses[markerkey] = self.scene.item(self.key)
			self.scene.sync()
		else:
			self.close()
	
	def closeEvent(self, event):
		self.scene.main.views.remove(self)
		del self.scene.main.details[self.key]
		del self.scene.additions[('marker',self.key)]
		self.scene.sync()
		if isinstance(self.parent(), QDockWidget):
			self.scene.main.mainwindow.removeDockWidget(self.parent())
		else:
			super().close()
	
	def info(self, infos):
		''' set the displayed informations '''
		self._text.document().clear()
		cursor = QTextCursor(self._text.document())
		palette = self.palette()
		familly, size = settings.scriptview['font']
		
		fmt_value = charformat(
						font=QFont(familly, size), 
						foreground=palette.text())
		fmt_key = charformat(
						font=QFont(familly, int(size*1.2), weight=QFont.Bold), 
						foreground=palette.link())
		
		if isinstance(infos, dict):
			for key in sorted(list(infos)):
				formated = nformat(repr(infos[key]))
				# one line format
				if not '\n' in formated:	
					cursor.insertText((key+':').ljust(16), fmt_key)
					cursor.insertText(formated+'\n', fmt_value)
				# multiline format
				else:
					cursor.insertText(key+':', fmt_key)
					cursor.insertText(('\n'+formated).replace('\n', '\n    ')+'\n', fmt_value)
		else:
			cursor.insertText(nformat(repr(infos)), fmt_value)

