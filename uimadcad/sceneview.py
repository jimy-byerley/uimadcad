from PyQt5.QtCore import (
		Qt, QSize, QRect, QPoint, QPointF,
		QEvent, pyqtSignal, QObject,
		QAbstractListModel,
		)
from PyQt5.QtWidgets import (
		QWidget, QStyleFactory, QSizePolicy, QHBoxLayout, 
		QPlainTextEdit, QComboBox, QDockWidget, QPushButton,
		QPlainTextDocumentLayout,
		)
from PyQt5.QtGui import (
		QFont, QFontMetrics, 
		QColor, QPalette,
		QIcon, QKeySequence, 
		QTextOption, QTextDocument, QTextCursor,
		QPainter, QPainterPath,
		)

from madcad.mathutils import vec3, fvec3, fmat4, Box, boundingbox, inf, length, inverse
from madcad.rendering import Display, displayable
from madcad.displays import SolidDisplay, WebDisplay
from madcad.mesh import Mesh, Web, Wire
import madcad

from .detailview import DetailView
from .interpreter import Interpreter, InterpreterError, astinterval
from . import tricks

from copy import deepcopy, copy
from nprint import nprint


QEventGLContextChange = 215	# opengl context change event type, not yet defined in PyQt5

class Scene(madcad.rendering.Scene, QObject):
	changed = pyqtSignal()
	
	def __init__(self, main, *args, **kwargs):
		madcad.rendering.Scene.__init__(self, *args, **kwargs)
		QObject.__init__(self)
		self.main = main
		self.forceddisplays = set()
		self.composition = QTextDocument()
		self.composition.setDocumentLayout(QPlainTextDocumentLayout(self.composition))
		
		self.main.scenes.append(self)
		self.main.executed.connect(self.sync)
		self.main.scenesmenu.layoutChanged.emit()
	
	def __del__(self):
		try:	self.main.scenes.remove(self)
		except ValueError:	pass
	
	def sync(self):
		# objects selection in env, and already present objs
		main = self.main
		newscene = {}
		
		# display objects that are requested by the user, or that are never been used (lastly generated)
		for name,obj in main.interpreter.current.items():
			if displayable(obj) and (	name in self.forceddisplays 
									or	name in main.neverused):
				newscene[name] = obj
		# display objects in the display zones
		for zs,ze in main.displayzones:
			for name,node in main.interpreter.locations.items():
				if name not in newscene:
					ts,te = astinterval(node)
					temp = main.interpreter.current[name]
					if zs <= ts and te <= ze and displayable(temp):
						newscene[name] = temp
		# update the scene
		self.update(newscene)
		# trigger the signal for dependent widgets
		self.changed.emit()

	

class SceneView(madcad.rendering.View):
	''' dockable and reparentable scene view widget, bases on madcad.Scene '''
	def __init__(self, main, scene=None, **kwargs):
		self.main = main
		
		if scene:
			pass
		elif main.active_sceneview:
			scene = main.active_sceneview.scene
			self.navigation = deepcopy(main.active_sceneview.navigation)
		elif main.scenes:
			scene = main.scenes[0]
		else:
			scene = Scene(main)
		super().__init__(scene, **kwargs)
		
		self.setMinimumSize(100,100)
		self.setSizePolicy(QSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum))
		
		main.views.append(self)
		if not main.active_sceneview:	main.active_sceneview = self
	
		self.statusbar = SceneViewBar(self)
		self.scene.changed.connect(self.update)
	
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
		return detail
		
	def separate_scene(self):
		#self.scene = self.scene.duplicate(self.scene.ctx)
		self.scene = Scene(self.main, ctx=self.scene.ctx)
		self.preload()
		self.scene.sync()
		

class SceneViewBar(QWidget):
	''' statusbar for a sceneview, containing scene management tools '''
	def __init__(self, sceneview, parent=None):
		super().__init__(parent)
		self.sceneview = sceneview
		
		self.scenes = scenes = QComboBox()
		scenes.setFrame(False)
		def callback(i):
			self.sceneview.scene = self.sceneview.main.scenes[i]
			self.sceneview.update()
		scenes.activated.connect(callback)
		scenes.setModel(sceneview.main.scenesmenu)
		
		def btn(icon, callback=None):
			b = QPushButton(QIcon.fromTheme(icon), '')
			b.setSizePolicy(QSizePolicy(QSizePolicy.Maximum, QSizePolicy.Maximum))
			b.setFlat(True)
			if callback:
				b.clicked.connect(callback)
			return b
			
		def callback():
			sceneview.separate_scene()
			scenes.setCurrentIndex(len(sceneview.main.scenes)-1)
		
		btn_compose = btn('madcad-compose')
		self.composition = SceneComposition(sceneview.scene, parent=btn_compose)
		btn_compose.clicked.connect(self.show_composition)
		
		layout = QHBoxLayout()
		layout.addWidget(self.scenes)
		layout.addWidget(btn('list-add', callback))
		layout.addWidget(QWidget())
		layout.addWidget(btn_compose)
		layout.addWidget(btn('dialog-close-icon', sceneview.close))
		self.setLayout(layout)
	
	def show_composition(self):
		self.composition.show()
		self.composition.activateWindow()
		self.composition.setFocus()
		
class SceneList(QAbstractListModel):
	''' model for the scene list of the scene status bar '''
	def __init__(self, main):
		super().__init__(parent=main)
		self.main = main
	
	# implement the interface
	def data(self, index, role):
		if role == Qt.DisplayRole:	
			return 'scene {}'.format(index.row())
	def rowCount(self, parent=None):
		return len(self.main.scenes)


class SceneComposition(QPlainTextEdit):
	''' text view to specify objects main.currentenv we want to append to main.scene '''
	def __init__(self, scene, parent=None):
		super().__init__(parent)
		self.setWindowFlags(Qt.Popup | Qt.Tool | Qt.FramelessWindowHint)
		
		self.scene = scene
		self.setDocument(scene.composition)
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
		self.scene.forceddisplays.clear()
		self.scene.forceddisplays.update(self.toPlainText().split())
		self.resize(
			self.width(), 
			self.document().defaultFont().pointSize() * (self.document().lineCount()+1)*2)

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

