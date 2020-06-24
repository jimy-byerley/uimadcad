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

from madcad.mathutils import vec3, fvec3, Box, boundingbox, inf, length
from madcad.view import Scene
import madcad.settings

from interpreter import Interpreter, InterpreterError, astinterval
import tricks

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
		''' overload the Scene method, to implement the edition behaviors '''
		grp,rdr = self.stack[rdri]
		
		# an editor exists for this object
		if grp in self.main.editors:
			if evt.button() == Qt.LeftButton and evt.type() == QEvent.MouseButtonDblClick:
				self.main.finishedit(grp)
			else:
				self.tool = rdr.control(self, grp, subi, evt)
		
		# the left button is the master key: used for selection on simple click and to start edition on other usage
		elif evt.button() == Qt.LeftButton:
			if evt.type() == QEvent.MouseButtonPress and hasattr(rdr, 'select'):
				self.main.select((grp,subi))
			elif evt.type() == QEvent.MouseButtonDblClick:
				self.main.select((grp,subi))
				self.main.edit(grp)
			else:
				super().objcontrol(rdri, subi, evt)
		# right button is used for the normal display purposes
		else:
			super().objcontrol(rdri, subi, evt)


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

