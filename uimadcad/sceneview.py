from PyQt5.QtCore import (
		Qt, QSize, QRect, QPoint, QPointF,
		QEvent, pyqtSignal,
		)
from PyQt5.QtWidgets import (
		QWidget, QStyleFactory, QSizePolicy, QHBoxLayout, 
		QPlainTextEdit, QComboBox, QDockWidget, QPushButton,
		)
from PyQt5.QtGui import (
		QFont, QFontMetrics, 
		QColor, QPalette,
		QIcon, QKeySequence, 
		QTextOption, QTextDocument, QTextCursor,
		QPainter, QPainterPath,
		)

from madcad.mathutils import vec3, fvec3, fmat4, Box, boundingbox, inf, length, inverse
from madcad.rendering import Scene, View, Display
from madcad.displays import SolidDisplay, WebDisplay
from madcad.mesh import Mesh, Web, Wire
import madcad.settings

from .detailview import DetailView
from .interpreter import Interpreter, InterpreterError, astinterval
from . import tricks

from copy import deepcopy, copy
from nprint import nprint


QEventGLContextChange = 215	# opengl context change event type, not yet defined in PyQt5

class SceneView(View):
	''' dockable and reparentable scene view widget, bases on madcad.Scene '''
	def __init__(self, main, scene=None, **kwargs):
		self.main = main
		self.initnum = 0
		
		if scene:
			pass
		elif main.active_sceneview:
			scene = main.active_sceneview.scene
		elif main.scenes:
			scene = main.scenes[0]
		else:
			scene = Scene()
			main.scenes.append(scene)
		super().__init__(scene, **kwargs)
		
		self.setMinimumSize(100,100)
		self.setSizePolicy(QSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum))
		
		main.views.append(self)
		if not main.active_sceneview:	main.active_sceneview = self
	
		self.statusbar = SceneStatusBar(self)
	
	def closeEvent(self, event):
		super().closeEvent(event)
		# WARNING: due to some Qt bugs, a removed Scene can be closed multiple times, and the added scenes are never closed nor displayed
		#self.main.views.remove(self)
		for i,view in enumerate(self.main.views):
			if view is self:
				self.main.views.pop(i)
		event.accept()
		
	def focusInEvent(self, event):
		super().focusInEvent(event)
		self.main.active_sceneview = self
	
	def changeEvent(self, event):
		# detect QDockWidget integration
		if event.type() == event.ParentChange:
			if isinstance(self.parent(), QDockWidget):
				self.parent().setTitleBarWidget(self.statusbar)
		return super().changeEvent(event)
	
	# DEPRECATED
	def objcontrol(self, rdri, subi, evt):
		''' overwrite the Scene method, to implement the edition behaviors '''
		grp,rdr = self.stack[rdri]
		
		# an editor exists for this object
		if grp in self.main.editors:
			self.tool = rdr.control(self, grp, subi, evt)
			if not evt.isAccepted():
				if evt.button() == Qt.LeftButton and evt.type() == QEvent.MouseButtonDblClick:
					self.main.finishedit(grp)
					evt.accept()
					return
		
		# the events is submitted to the custom controls first
		if hasattr(rdr, 'control'):
			self.tool = rdr.control(self, rdri, subi, evt)
			if evt.isAccepted():	
				return
		
		if evt.button() == Qt.LeftButton:
			if evt.type() == QEvent.MouseButtonRelease and hasattr(rdr, 'select'):
				self.main.select((grp,subi))
				evt.accept()
			elif evt.type() == QEvent.MouseButtonDblClick:
				self.main.select((grp,subi))
				self.main.edit(grp)
				evt.accept()
		
		elif evt.button() == Qt.RightButton and evt.type() == QEvent.MouseButtonRelease:
			obj = self.main.scene[grp]
			if isinstance(obj, (Mesh,Web,Wire)) and isinstance(rdr, (SolidDisplay,WebDisplay)):
				ident = (grp,subi)
				self.main.select(ident, True)
				self.showdetail(ident, evt.pos())
		
	
	def showdetail(self, ident, position=None):
		''' display a detail window for the ident given (grp,sub) '''
		if ident in self.main.details:
			detail = self.main.details[ident]
		else:
			detail = DetailView(self.main, ident)
		
		if position:
			if position.x() < self.width()//2:	offsetx = -350
			else:								offsetx = 50
			detail.move(self.mapToGlobal(position) + QPoint(offsetx,0))
		
		detail.show()
		detail.activateWindow()
		
	def separate_scene(self):
		#self.scene = self.scene.duplicate(self.scene.ctx)
		self.scene = Scene
		self.main.scenes.append(self.scene)
		self.initializeGL()
	
	# DEPRECATED
	def localptfrom(self, pos, center):
		center = vec3(center)
		solid = self.main.active_solid
		if not solid:	return self.ptfrom(pos, center)
		wcenter = solid.orientation * center + solid.position
		wpt = self.ptfrom(pos, wcenter)
		return inverse(solid.orientation) * (wpt - solid.position)
	
	# DEPRECATED
	def localptat(self, pos):
		solid = self.main.active_solid
		if not solid:	return self.ptat(pos)
		wpt = self.ptat(pos)
		return inverse(solid.orientation) * (wpt - solid.position)
		


class SceneStatusBar(QWidget):
	''' statusbar for a sceneview, containing scene management tools '''
	def __init__(self, sceneview, parent=None):
		super().__init__(parent)
		self.sceneview = sceneview
		
		self.scenes = QComboBox()
		self.scenes.setFrame(False)
		
		def btn(icon, callback=None):
			b = QPushButton(QIcon.fromTheme(icon), '')
			b.setSizePolicy(QSizePolicy(QSizePolicy.Maximum, QSizePolicy.Maximum))
			b.setFlat(True)
			if callback:
				b.clicked.connect(callback)
			return b
		
		btn_compose = btn('madcad-compose')
		self.composition = SceneList(sceneview.main, btn_compose)
		btn_compose.clicked.connect(self.show_composition)
			
		layout = QHBoxLayout()
		layout.addWidget(self.scenes)
		layout.addWidget(btn('list-add', sceneview.separate_scene))
		layout.addWidget(QWidget())
		layout.addWidget(btn_compose)
		layout.addWidget(btn('dialog-close-icon', sceneview.close))
		self.setLayout(layout)
		
		self.scenes_changed()
	
	def scenes_changed(self):
		menu = self.scenes
		for i in reversed(range(menu.count())):
			menu.removeItem(i)
		for i in range(len(self.sceneview.main.scenes)):
			menu.addItem('scene {}'.format(i))
	
	def show_composition(self):
		self.composition.show()
		self.composition.activateWindow()
		self.composition.setFocus()


class SceneList(QPlainTextEdit):
	''' text view to specify objects main.currentenv we want to append to main.scene '''
	def __init__(self, main, parent=None):
		super().__init__(parent)
		self.setWindowFlags(Qt.Window | Qt.Tool | Qt.FramelessWindowHint)
		
		self.main = main
		self.document().contentsChange.connect(self._contentsChange)
		margins = self.viewportMargins()
		height = (
			QFontMetrics(self.currentCharFormat().font()).height()
			+ margins.top() + margins.bottom()
			+ 2*self.contentOffset().y()
			)
		self.setMinimumHeight(height)
		self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
		
	def _contentsChange(self, item):
		self.main.forceddisplays = set(self.toPlainText().split())
		self.main.updatescene()
		self.resize(self.width(), self.document().defaultFont().pointSize()*(self.document().lineCount()+1)*2)

	def focusOutEvent(self, evt):
		super().focusOutEvent(evt)
		self.setVisible(False)
			
	def setVisible(self, visible):
		super().setVisible(visible)
		parent = self.parent()
		if visible and parent:
			psize = parent.size()
			self.resize(100, self.document().defaultFont().pointSize()*(self.document().lineCount()+1)*2)
			self.move(parent.mapToGlobal(QPoint(0,0)) + QPoint(
					psize.width()-self.width(), 
					psize.height(),
					))

