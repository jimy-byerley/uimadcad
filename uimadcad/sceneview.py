from PyQt5.QtCore import (
		Qt, QSize, QRect, QPoint, QPointF,
		QEvent, pyqtSignal,
		)
from PyQt5.QtWidgets import (
		QWidget, QStyleFactory, QSizePolicy,
		QPlainTextEdit,
		)
from PyQt5.QtGui import (
		QFont, QFontMetrics, 
		QColor, QPalette,
		QIcon, QKeySequence, 
		QTextOption, QTextDocument, QTextCursor,
		QPainter, QPainterPath,
		)

from madcad.mathutils import vec3, fvec3, fmat4, Box, boundingbox, inf, length, inverse
from madcad.view import Scene
from madcad.displays import SolidDisplay, WebDisplay
from madcad.mesh import Mesh, Web, Wire
import madcad.settings

from .detailview import DetailView
from .interpreter import Interpreter, InterpreterError, astinterval
from . import tricks

from copy import deepcopy, copy
from nprint import nprint



QEventGLContextChange = 215	# opengl context change event type, not yet defined in PyQt5

class SceneView(Scene):
	''' dockable and reparentable scene view widget, bases on madcad.Scene '''
	def __init__(self, main, **kwargs):
		self.main = main
		self.frozen = False
		self.initnum = 0
		super().__init__(**kwargs)
		
		main.views.append(self)
		if not main.active_sceneview:	main.active_sceneview = self
		self.sync()
	
	def initializeGL(self):
		self.initnum = 1
		super().initializeGL()
		
	def focusInEvent(self, event):
		self.main.active_sceneview = self
	
	def freeze(self):
		self.frozen = True
		parent = self.parent()
		if isinstance(parent, QDockWidget):
			parent.setWindowTitle(parent.windowTitle() + ' - frozen')
	
	def sync(self, updated=()):
		if not self.frozen:
			for key in list(self.displayed):
				if key not in self.main.scene or key in updated:
					self.remove(key)
			for key,obj in self.main.scene.items():
				if key not in self.displayed or key in updated:
					self.add(obj, key)
			self.update()
	
	def applyposes(self):
		for name,rdr in self.stack:
			if hasattr(rdr, 'transform'):
				solid = self.main.poses.get(name, self.main.active_solid)
				if solid is not None:
					rdr.transform = fmat4(solid.pose())
	
	def dequeue(self):
		dequeued = bool(self.queue)
		super().dequeue()
		if dequeued:
			self.applyposes()
	
	def closeEvent(self, event):
		super().closeEvent(event)
		# WARNING: due to some Qt bugs, a removed Scene can be closed multiple times, and the added scenes are never closed nor displayed
		#self.main.views.remove(self)
		for i,view in enumerate(self.main.views):
			if view is self:
				self.main.views.pop(i)
		event.accept()
	
	# exceptional override of this method to handle the opengl context change
	def event(self, event):
		if event.type() == QEventGLContextChange:
			if self.initnum >= 1:
				# reinit completely the scene to rebuild opengl contextual objects
				dock = self.parent()
				self.close()
				dock.setWidget(SceneView(self.main, 
									projection=self.projection, 
									manipulator=self.manipulator))
			return True
		else:
			return super().event(event)
			
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
	
	def localptfrom(self, pos, center):
		center = vec3(center)
		solid = self.main.active_solid
		if not solid:	return self.ptfrom(pos, center)
		wcenter = solid.orientation * center + solid.position
		wpt = self.ptfrom(pos, wcenter)
		return inverse(solid.orientation) * (wpt - solid.position)
	
	def localptat(self, pos):
		solid = self.main.active_solid
		if not solid:	return self.ptat(pos)
		wpt = self.ptat(pos)
		return inverse(solid.orientation) * (wpt - solid.position)


class SceneList(QPlainTextEdit):
	''' text view to specify objects main.currentenv we want to append to main.scene '''
	def __init__(self, main):
		super().__init__()
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
	
	def sizeHint(self):
		return self.document().size().toSize()
	
	def _contentsChange(self, item):
		self.updateGeometry()
		self.main.forceddisplays = set(self.toPlainText().split())
		self.main.updatescene()

