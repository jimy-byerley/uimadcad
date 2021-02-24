from PyQt5.QtCore import (
		Qt, QSize, QRect, QPoint, QPointF,
		QEvent, pyqtSignal, QObject,
		QAbstractListModel,
		)
from PyQt5.QtWidgets import (
		QWidget, QStyleFactory, QSizePolicy, QHBoxLayout, 
		QPlainTextEdit, QComboBox, QDockWidget, QPushButton, QToolBar, QAction, 
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
from madcad.rendering import Display, displayable, Displayable, Step, Group
from madcad.displays import SolidDisplay, WebDisplay, GridDisplay
import madcad

from .common import *
from .detailview import DetailView
from .interpreter import Interpreter, InterpreterError, astinterval
from . import tricks, settings

import ast
from copy import deepcopy, copy


QEventGLContextChange = 215	# opengl context change event type, not yet defined in PyQt5

class Scene(madcad.rendering.Scene, QObject):
	changed = pyqtSignal()
	
	def __init__(self, main, *args, **kwargs):
		# data graph setup
		madcad.rendering.Scene.__init__(self, *args, **kwargs)
		QObject.__init__(self)
		self.main = main
		main.scenes.append(self)
		main.executed.connect(self._executed)
		main.scenesmenu.layoutChanged.emit()
		
		# scene data
		self.composition = QTextDocument()
		self.composition.setDocumentLayout(QPlainTextDocumentLayout(self.composition))
		
		self.forceddisplays = set()		# variable names to always display
		self.additions = {		# systematic scene additions
			'__grid__': Displayable(Grid),
			'__updateposes__': Step('screen', -1, self._updateposes),
			}
		self.poses = {}			# solid per variable for poses, non associated solids are not in that dict
		self.active_solid = None	# current solid for current space
		self.executed = True	# flag set to True to enable a full relead of the scene
		self.displayall = False
	
	def __del__(self):
		try:	self.main.scenes.remove(self)
		except ValueError:	pass
		
	def _executed(self):
		self.executed = True
		self.sync()
	
	def sync(self):
		# objects selection in env, and already present objs
		main = self.main
		it = main.interpreter
		newscene = {}
		
		# display objects that are requested by the user, or that are never been used (lastly generated)
		for name,obj in it.current.items():
			if name in newscene:	continue
			if name in self.forceddisplays or name in it.neverused or self.displayall and name in it.locations:
				if displayable(obj):
					newscene[name] = obj
		
		# display objects in the display zones
		for zs,ze in main.displayzones.values():
			for name,node in it.locations.items():
				if name not in newscene:
					ts,te = astinterval(node)
					temp = it.current[name]
					if zs <= ts and te <= ze and displayable(temp):
						newscene[name] = temp
		# add scene's own additions
		newscene.update(main.editors)
		newscene.update(self.additions)
		
		# update the scene
		super().sync(newscene)
		# perform other actions on sync
		self.dequeue()
		self.update_solidsets()
		# trigger the signal for dependent widgets
		self.changed.emit()
		
	def touch(self):
		self.changed.emit()
		super().touch()
	
	def update(self, objs):
		if not objs:	return
		for k,v in objs.items():
			disp = self.displays.get(k)
			if self.executed or not disp or id(getattr(disp,'source',None)) != id(v):
				self.queue[k] = v
		self.executed = False
		self.touch()
			
		
	def update_solidsets(self):
		''' update the association of variables to solids '''
		self.poses = {}	# pose for each variable name
		
		ast_name = (ast.Name, ast.NamedExpr) if hasattr(ast, 'NamedExpr') else ast.Name
		sets = []	# sets of variables going together
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
				if isinstance(child, ast_name):
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
		search_statements(self.main.interpreter.part_altered)
		
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
			if name in self.additions or hasattr(disp, 'source') and isinstance(disp.source, (Solid,Kinematic)):	
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
				if isinstance(disp, Group):
					box.union(selbox(disp.displays.values()))
				elif disp.selected:
					box.union(disp.box.transform(disp.world))
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
		
		self.quick = QToolBar('quick', self)
		self.quick.setOrientation(Qt.Vertical)
		action = QAction('points', main, checkable=True)
		action.setChecked(madcad.settings.scene['display_points'])
		action.toggled.connect(main._display_points)
		self.quick.addAction(action)
		action = QAction('wire', main, checkable=True)
		action.setChecked(madcad.settings.scene['display_wire'])
		action.toggled.connect(main._display_wire)
		self.quick.addAction(action)
		action = QAction('groups', main, checkable=True)
		action.setChecked(madcad.settings.scene['display_groups'])
		action.toggled.connect(main._display_groups)
		self.quick.addAction(action)
		action = QAction('faces', main, checkable=True)
		action.setChecked(madcad.settings.scene['display_faces'])
		action.toggled.connect(main._display_faces)
		self.quick.addAction(action)
		action = QAction('all', main, checkable=True)
		action.toggled.connect(main._display_all)
		self.quick.addAction(action)
		self.quick.addAction(QIcon.fromTheme('lock'), 'lock solid', main.lock_solid)
		self.quick.addAction(QIcon.fromTheme('madcad-solid'), 'set active solid', main.set_active_solid)
		self.quick.addAction(QIcon.fromTheme('edit-select-all'), 'deselect all', main.deselectall)
		self.quick.addAction(QIcon.fromTheme('edit-node'), 'graphical edit object', main._edit)
		self.quick.setGeometry(0,0, 40, 300)
		self.quick.hide()
	
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
		
	def enterEvent(self, event):
		if settings.view['quick_toolbars']:	
			self.quick.show()
		
	def leaveEvent(self, event):
		if not self.hasFocus():	
			self.quick.hide()
		
	def focusOutEvent(self, event):
		self.quick.hide()
	
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
		stack = []
		for i in range(1,len(key)):
			disp = disp[key[i-1]]
			disp.control(self, key[:i], key[i:], evt)
			if evt.isAccepted(): return
			stack.append(disp)
		
		# sub selection
		if evt.type() == QEvent.MouseButtonRelease and evt.button() == Qt.LeftButton:
			disp = stack[-1]
			# select what is under cursor
			if type(disp).__name__ in ('SolidDisplay', 'WebDisplay'):
				disp.vertices.selectsub(key[-1])
				disp.selected = any(disp.vertices.flags & 0x1)
			else:
				disp.selected = not disp.selected
			# make sure that a display is selected if one of its sub displays is
			for disp in reversed(stack):
				if isinstance(disp, Group):
					disp.selected = any(sub.selected	for sub in disp.displays.values())
			self.update()
			self.main.updatescript()
			evt.accept()
		
		# show details
		elif evt.type() == QEvent.MouseButtonRelease and evt.button() == Qt.RightButton:
			self.showdetail(key, evt.pos())
			evt.accept()
		
		# edition
		elif evt.type() == QEvent.MouseButtonDblClick and evt.button() == Qt.LeftButton and hasattr(disp, 'source'):
			name = self.main.interpreter.ids.get(id(disp.source))
			if name:	
				if name in self.main.editors:
					self.main.finishedit(name)
				else:
					self.main.edit(name)
				evt.accept()
		
	
	def showdetail(self, key, position=None):
		''' display a detail window for the ident given (grp,sub) '''
		if key in self.main.details:	
			return
		disp = self.scene.item(key)
		if not disp or not hasattr(disp, 'source') or not isinstance(disp.source, (Mesh,Web)):
			return
		
		detail = DetailView(self.scene, key)
		detail.move(self.mapToGlobal(self.geometry().center()))
		detail.show()
	
		if position:
			if position.x() < self.width()//2:	offsetx = -200
			else:								offsetx = 50
			detail.move(self.mapToGlobal(position) + QPoint(offsetx,0))
		
		detail.show()
		detail.activateWindow()
		
	def separate_scene(self):
		#self.scene = self.scene.duplicate(self.scene.ctx)
		self.set_scene(Scene(self.main, ctx=self.scene.ctx))
		self.preload()
		self.scene.sync()
		
	def set_scene(self, new):
		if self.scene:
			self.scene.changed.disconnect(self.update)
		self.scene = new
		self.scene.changed.connect(self.update)
		self.update()
		

class SceneViewBar(QWidget):
	''' statusbar for a sceneview, containing scene management tools '''
	def __init__(self, sceneview, parent=None):
		super().__init__(parent)
		self.sceneview = sceneview
		
		self.scenes = scenes = QComboBox()
		scenes.setFrame(False)
		def callback(i):
			self.sceneview.set_scene(self.sceneview.main.scenes[i])
			self.composition.scene = self.sceneview.scene
		scenes.activated.connect(callback)
		scenes.setModel(sceneview.main.scenesmenu)
		scenes.setCurrentIndex(sceneview.main.scenes.index(sceneview.scene))
		scenes.setToolTip('scene to display')
		
		def btn(icon, callback=None, help=''):
			b = QPushButton(QIcon.fromTheme(icon), '')
			b.setSizePolicy(QSizePolicy(QSizePolicy.Maximum, QSizePolicy.Maximum))
			b.setFlat(True)
			b.setToolTip(help)
			if callback:
				b.clicked.connect(callback)
			return b
			
		def separate_scene():
			self.sceneview.separate_scene()
			self.composition.scene = self.sceneview.scene
			scenes.setCurrentIndex(len(sceneview.main.scenes)-1)
			
		def viewadapt(self):
			scene = sceneview.scene
			box = scene.selectionbox() or scene.box()
			sceneview.center(box.center)
			sceneview.adjust(box)
		
		btn_compose = btn('madcad-compose', help='force some objects to display')
		self.composition = SceneComposition(sceneview.scene, parent=btn_compose)
		btn_compose.clicked.connect(self.show_composition)
		
		layout = QHBoxLayout()
		layout.addWidget(self.scenes)
		layout.addWidget(btn('list-add', separate_scene, 'duplicate scene'))
		layout.addWidget(QWidget())
		layout.addWidget(btn('view-fullscreen', viewadapt, 'adapt view to centent'))
		layout.addWidget(btn_compose)
		layout.addWidget(btn('dialog-close-icon', sceneview.close, 'close view'))
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


