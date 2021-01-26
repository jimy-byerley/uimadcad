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

from madcad import *
from madcad.rendering import Display, displayable, Displayable, Step
from madcad.displays import SolidDisplay, WebDisplay, GridDisplay
import madcad

from .common import *
from .detailview import DetailView
from .interpreter import Interpreter, InterpreterError, astinterval
from . import tricks

import ast
from copy import deepcopy, copy
from nprint import nprint


QEventGLContextChange = 215	# opengl context change event type, not yet defined in PyQt5

class Scene(madcad.rendering.Scene, QObject):
	changed = pyqtSignal()
	
	def __init__(self, main, *args, **kwargs):
		# data graph setup
		madcad.rendering.Scene.__init__(self, *args, **kwargs)
		QObject.__init__(self)
		self.main = main
		main.scenes.append(self)
		main.executed.connect(self.sync)
		main.scenesmenu.layoutChanged.emit()
		
		# scene data
		self.composition = QTextDocument()
		self.composition.setDocumentLayout(QPlainTextDocumentLayout(self.composition))
		
		self.forceddisplays = set()
		self.additions = {
			'__grid__': Displayable(Grid),
			'__updateposes__': Step('screen', -1, self._updateposes),
			}
		self.editors = {}
		self.poses = {}
		self.active_solid = None
	
	def __del__(self):
		try:	self.main.scenes.remove(self)
		except ValueError:	pass
	
	def sync(self):
		# objects selection in env, and already present objs
		main = self.main
		it = main.interpreter
		newscene = {}
		
		# display objects that are requested by the user, or that are never been used (lastly generated)
		for name,obj in it.current.items():
			if name in newscene:	continue
			if name in self.forceddisplays or name in main.neverused:
				if displayable(obj):
					newscene[name] = obj
				# some exceptional behaviors
				elif isjoint(obj):
					for s in obj.solids:
						i = id(s)
						if i in it.ids and it.ids[i] not in newscene:
							newscene[it.ids[i]] = s
		
		# display objects in the display zones
		for zs,ze in main.displayzones.values():
			for name,node in it.locations.items():
				if name not in newscene:
					ts,te = astinterval(node)
					temp = it.current[name]
					if zs <= ts and te <= ze and displayable(temp):
						newscene[name] = temp
		# add scene's own additions
		newscene.update(self.additions)
		
		# update the scene
		super().sync(newscene)
		# perform other actions on sync
		self.dequeue()
		self.update_solidsets()
		# trigger the signal for dependent widgets
		self.changed.emit()
		
	def update_solidsets(self):
		''' update the association of variables to solids '''
		self.poses = {}
		
		sets = []
		# process statements executed in the main flow
		def search_statements(node):
			for stmt in reversed(node.body):
				if isinstance(stmt, (ast.Expr, ast.Assign)):
					search_expr(stmt)
				elif isinstance(stmt, (ast.If, ast.With)):
					search_statements(stmt)
		# all variables trapped into the same expr are put into the same set
		def search_expr(node):
			used = set()
			wrote = []
			for child in ast.walk(node):
				if isinstance(child, (ast.Name, ast.NamedExpr)):
					used.add(child.id)
					if isinstance(child.ctx, ast.Store):
						wrote.append(child.id)
			assigned = False
			for s in sets:
				if not s.isdisjoint(wrote):
					s.update(used)
					assigned = True
			if not assigned:
				sets.append(used)
		search_statements(self.main.interpreter.altered_ast)
		
		# process SolidDisplays all across the scene
		def recur(level):
			for disp in level:
				if isinstance(disp, Solid.display):
					process(disp)
				# recursion
				elif isinstance(disp, madcad.rendering.Group):	
					recur(disp.displays.values())
		# find sub displays representing existing variables
		def process(disp):
			for sub in scene_unroll(disp):
				if not hasattr(sub, 'source'):	continue
				bound = self.main.interpreter.ids.get(id(sub.source))
				if not bound:	continue
				# find a solidset that provides that value
				try:	s = next(u for u in sets	if bound in u)
				except StopIteration:	continue
				# change its variables world matrices
				for name in s:
					self.poses[name] = disp
		recur(self.displays.values())
		
	def _updateposes(self, _):
		for name,disp in self.displays.items():
			if hasattr(disp, 'source') and isinstance(disp.source, (Solid,Kinematic)):	
				continue
			obj = self.poses.get(name, self.active_solid)
			if obj:
				disp.world = obj.world * obj.pose
	
	def display(self, obj):
		disp = super().display(obj)
		disp.source = obj
		return disp

	def items(self):
		''' yield recursively all couples (key, display) in the scene, including subscenes '''
		def recur(level, key):
			for sub,disp in level:
				yield (*key, sub), disp
				if isinstance(disp, madcad.rendering.Group):	
					yield from recur(disp.displays.items(), (*key, sub))
		yield from recur(self.displays.items(), ())
		
	def selectionbox(self):
		''' return the bounding box of the selection '''
		def selbox(level):
			box = Box(fvec3(inf), fvec3(-inf))
			for disp in level:
				if disp.selected:
					box.union(disp.box.transform(disp.world))
				elif isinstance(disp, madcad.rendering.Group):
					box.union(selbox(disp.displays.values()))
			return box
		return selbox(self.displays.values())

def scene_unroll(scene):
	''' yield recursively all displays in the scene, including subscenes '''
	def recur(level):
		for disp in level:
			yield disp
			if isinstance(disp, madcad.rendering.Group):	
				yield from recur(disp.displays.values())
	yield from recur(scene.displays.values())		


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
		self.main.views.remove(self)
		if self.main.active_sceneview is self:
			self.main.active_sceneview = None
		if isinstance(self.parent(), QDockWidget):
			self.main.mainwindow.removeDockWidget(self.parent())
		else:
			super().close()
		
	def focusInEvent(self, event):
		super().focusInEvent(event)
		self.main.active_sceneview = self
		self.main.active_changed.emit()
	
	def changeEvent(self, evt):
		# detect QDockWidget integration
		if evt.type() == evt.ParentChange:
			if isinstance(self.parent(), QDockWidget):
				self.parent().setTitleBarWidget(self.statusbar)
		# update scene when color changes
		elif evt.type() == QEvent.PaletteChange and settings.display['system_theme']:
			self.scene.sync()
		return super().changeEvent(evt)
		
	def control(self, key, evt):
		''' overwrite the Scene method, to implement the edition behaviors '''
		disp = self.scene.displays
		for i in range(1,len(key)):
			disp = disp[key[i-1]]
			disp.control(self, key[:i], key[i:], evt)
			if evt.isAccepted(): return
		
		if evt.type() == QEvent.MouseButtonRelease and evt.button() == Qt.LeftButton:
			disp = self.scene.item(key)
			if type(disp).__name__ in ('SolidDisplay', 'WebDisplay'):
				disp.vertices.selectsub(key[-1])
				disp.selected = any(disp.vertices.flags & 0x1)
			else:
				disp.selected = not disp.selected
			self.update()
			self.main.updatescript()
	
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
			self.composition.scene = self.sceneview.scene
		scenes.activated.connect(callback)
		scenes.setModel(sceneview.main.scenesmenu)
		scenes.setCurrentIndex(sceneview.main.scenes.index(sceneview.scene))
		
		def btn(icon, callback=None):
			b = QPushButton(QIcon.fromTheme(icon), '')
			b.setSizePolicy(QSizePolicy(QSizePolicy.Maximum, QSizePolicy.Maximum))
			b.setFlat(True)
			if callback:
				b.clicked.connect(callback)
			return b
			
		def separate_scene():
			self.sceneview.separate_scene()
			self.sceneview.update()
			self.composition.scene = self.sceneview.scene
			scenes.setCurrentIndex(len(sceneview.main.scenes)-1)
			
		def viewadapt(self):
			scene = sceneview.scene
			box = scene.selectionbox() or scene.box()
			sceneview.center(box.center)
			sceneview.adjust(box)
		
		btn_compose = btn('madcad-compose')
		self.composition = SceneComposition(sceneview.scene, parent=btn_compose)
		btn_compose.clicked.connect(self.show_composition)
		
		layout = QHBoxLayout()
		layout.addWidget(self.scenes)
		layout.addWidget(btn('list-add', separate_scene))
		layout.addWidget(QWidget())
		layout.addWidget(btn('view-fullscreen', viewadapt))
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
		
		self.document().contentsChange.connect(self._contentsChange)
		margins = self.viewportMargins()
		height = (
			QFontMetrics(self.currentCharFormat().font()).height()
			+ margins.top() + margins.bottom()
			+ 2*self.contentOffset().y()
			)
		self.setMinimumHeight(height)
		self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
		
		self.scene = scene
		
	@propertywrite
	def scene(self, scene):
		self.document().contentsChange.disconnect(self._contentsChange)
		self.setDocument(scene.composition)
		self.document().contentsChange.connect(self._contentsChange)
	
	def _contentsChange(self, item):
		self._scene.forceddisplays.clear()
		self._scene.forceddisplays.update(self.toPlainText().split())
		self.resize(
			self.width(), 
			self.document().defaultFont().pointSize() * (self.document().lineCount()+1)*2)
		self._scene.sync()

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
					
class Grid(GridDisplay):
	def __init__(self, scene, **kwargs):
		super().__init__(scene, fvec3(0), **kwargs)
	
	def stack(self, scene):
		if scene.options['display_grid']:	return super().stack(scene)
		else: 								return ()
	
	def render(self, view):
		self.center = view.navigation.center
		super().render(view)


