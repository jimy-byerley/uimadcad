from PyQt5.QtCore import (
		Qt, QSize, QRect, QPoint, QPointF,
		QEvent, pyqtSignal, QObject,
		QAbstractListModel,
		)
from PyQt5.QtWidgets import (
		QWidget, QStyleFactory, QSizePolicy, QHBoxLayout, QVBoxLayout, 
		QComboBox, QDockWidget, QPushButton, QLabel, QSizeGrip, QCheckBox,
		QToolBar, QAction, 
		QPlainTextEdit, QPlainTextDocumentLayout,
		)
from PyQt5.QtGui import (
		QFont, QFontMetrics, 
		QColor, QPalette,
		QIcon, QKeySequence, 
		QTextOption, QTextDocument, QTextCursor,
		QPainter, QPainterPath,
		)

from madcad import *
from madcad.rendering import Display, displayable, Displayable, Step, Group, Turntable, Orbit, Perspective, Orthographic
from madcad.displays import SolidDisplay, WebDisplay, GridDisplay
import madcad

from .common import *
from .detailview import DetailView
from .interpreter import Interpreter, InterpreterError, astinterval
from . import tricks, settings

import ast
from copy import deepcopy, copy
from weakref import WeakValueDictionary
from operator import itemgetter


QEventGLContextChange = 215	# opengl context change event type, not yet defined in PyQt5

class Scene(madcad.rendering.Scene, QObject):
	changed = pyqtSignal()
	
	def __init__(self, main, *args, **kwargs):
		# data graph setup
		QObject.__init__(self)
		madcad.rendering.Scene.__init__(self, *args, **kwargs)
		self.main = main
		main.scenes.append(self)
		main.executed.connect(self._executed)
		main.scenesmenu.layoutChanged.emit()
		
		# scene data
		self.composition = SceneComposition(self)
		
		self.showset = set()		# variable names to always display
		self.hideset = set()		# variable names to never display
		self.additions = {		# systematic scene additions
			'__grid__': Displayable(Grid),
			'__updateposes__': Step('screen', -1, self._updateposes),
			}
		self.poses = {}			# solid per variable for poses, non associated solids are not in that dict
		self.active_solid = None	# current solid for current space
		self.active_selection = None	# key of the last selected display
		self.executed = True	# flag set to True to enable a full relead of the scene
		self.displayall = False
		self.displaynone = False
		self.selected = False
		
		self.cache = WeakValueDictionary()	# prevent loading multiple times the same object
		self.recursion_check = set()  # prevent reference-loop in groups (groups are taken from the execution env, so the user may not want to display it however we are trying to)
	
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
			if name in self.hideset:	continue
			if name in self.showset or self.displayall or (name in it.neverused and not self.displaynone) and name in it.locations:
				if displayable(obj):
					newscene[name] = obj
		
		# display objects in the display zones
		for zs,ze in main.displayzones.values():
			for name,node in it.locations.items():
				if name not in newscene and name in it.current:
					ts,te = astinterval(node)
					temp = it.current[name]
					if zs <= ts and te <= ze and displayable(temp) and type(temp) not in (list, dict):
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
		if not objs:    return
		for k,v in objs.items():
			disp = self.displays.get(k)
			if self.executed or not disp or type(getattr(disp, 'source', None)) != type(v):	# with a normal scene, self.executed would be the only condition, but scene elements like editors can be inserted by the interface
				self.queue[k] = v
		self.executed = False
		self.touch()
		
	def restack(self):
		''' update the rendering calls stack from the current scene's displays.
			this is called automatically on `dequeue()`
		'''
		# recreate stacks
		for stack in self.stacks.values():
			stack.clear()
		for key,display in self.displays.items():
			for frame in display.stack(self):
				if len(frame) != 4:
					raise ValueError('wrong frame format in the stack from {}\n\t got {}'.format(display, frame))
				sub,target,priority,func = frame
				full = (key,*sub)
				
				# try special behaviors
				try:	i = full.index('annotations')
				except ValueError:	pass
				else:
					if i:	disp = self.item(full[:i+1])
					else:	disp = self
					if not self.options['display_annotations'] and not disp.selected:
						continue
				
				if target not in self.stacks:	self.stacks[target] = []
				stack = self.stacks[target]
				stack.append((full, priority, func))
		# sort the stack using the specified priorities
		for stack in self.stacks.values():
			stack.sort(key=itemgetter(1))
		self.touched = False
		
	#def display(self, obj):		# NOTE will prevent different group from showing the same object, this is not desirable
		#ido = id(obj)
		#if ido in self.recursion_check:
			#raise Exception('recursion error')
		
		#if ido not in self.cache:
			#self.recursion_check.add(ido)
			#self.cache[ido] = super().display(obj)
			#self.cache[ido].source = obj
			#self.recursion_check.remove(ido)
		#return self.cache[ido]
		
	def display(self, obj, former=None):
		ido = id(obj)
		assert ido not in self.recursion_check, 'there should not be recursion loops in cascading displays'
		
		self.recursion_check.add(ido)
		try:		disp = super().display(obj, former)
		except Exception as err:     
			self.main.showerror(err)
			raise
		finally:	self.recursion_check.remove(ido)
		disp.source = obj
		return disp
		
	def update_solidsets(self):
		''' update the association of variables to solids '''
		# remove current object references, to allow deallocating their memory
		for name in self.poses:
			if isinstance(name, str) and name not in self.main.interpreter.current and name != 'return':
				self.poses[name] = None
		
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
				if isinstance(child, ast.Name):
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
		if self.main.interpreter.part_altered:
			search_statements(self.main.interpreter.part_altered)
		
		# the default pose for any object in the code executed, is the current local pose
		for u in sets:
			for name in u:
				if name != 'return':
					self.poses[name] = 'return'
		
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
			obj = self.poses.get(name)
			if obj != 'return' and isinstance(disp, (Solid.display, madcad.rendering.Group)):
				continue
			# solve dynamic pose binding (when a string is put instead of a solid)
			last = None
			while isinstance(obj, str) and last is not obj:	
				# the active solid can override a binding to the local pose
				if self.active_solid and obj == self.main.interpreter.name and disp is not self.active_solid:
					obj = self.active_solid
				else:
					obj, last = self.poses.get(obj), obj
			if isinstance(obj, Solid.display):
				disp.world = obj.world * obj.pose
			elif obj:
				disp.world = obj.world 
			else:
				disp.world = fmat4(1)

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
			if hasattr(disp, '__iter__'):	
				yield from recur(disp)
	yield from recur(scene.displays.values())		
	
	
def format_scenekey(scene, key, root=True, terminal=True):
	''' return a string representing the access to the object represented by a display in a scene 
	
		Example:
			
			>>> format_scenekey(..., root=True)
			cage.group(4)
			>>> format_scenekey(..., root=False)
			['cage'].group(4)
	'''
	if root:	name = str(key[0])
	else:		name = '[{}]'.format(repr(key[0]))
	node = scene
	for i in range(len(key)-1):
		node = node[key[i]]
		if isinstance(node, (SolidDisplay,WebDisplay)):
			access = '.group({})'
		elif i == len(key)-2 and terminal:
			access = ''
		else:
			access = '[{}]'
		name += access.format(repr(key[i+1]))
	return name


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
		action.setToolTip('display points')
		action.toggled.connect(lambda enable: self.set_option('display_points', enable))
		self.quick.addAction(action)
		action = QAction('wire', main, checkable=True)
		action.setChecked(madcad.settings.scene['display_wire'])
		action.setToolTip('display wire')
		action.toggled.connect(lambda enable: self.set_option('display_wire', enable))
		self.quick.addAction(action)
		action = QAction('groups', main, checkable=True)
		action.setChecked(madcad.settings.scene['display_groups'])
		action.setToolTip('display groups')
		action.toggled.connect(lambda enable: self.set_option('display_groups', enable))
		self.quick.addAction(action)
		action = QAction('faces', main, checkable=True)
		action.setChecked(madcad.settings.scene['display_faces'])
		action.setToolTip('display faces')
		action.toggled.connect(lambda enable: self.set_option('display_faces', enable))
		self.quick.addAction(action)
		#action = QAction('all', main, checkable=True)
		#action.setToolTip('display all variables')
		#action.toggled.connect(main._display_all)
		#self.quick.addAction(action)
		self.quick.addSeparator()
		self.quick.addAction(QIcon.fromTheme('view-fullscreen'), 'adapt view to centent', self.adapt)
		self.quick.addAction(QIcon.fromTheme('madcad-view-normal'), 'set view normal to mesh', self.normalview)
		self.quick.addAction(QIcon.fromTheme('madcad-projection'), 'switch projection perspective/orthographic', self.projectionswitch)
		self.quick.addSeparator()
		self.quick.addAction(QIcon.fromTheme('lock'), 'lock solid', main.lock_solid)
		self.quick.addAction(QIcon.fromTheme('madcad-solid'), 'set active solid', main.set_active_solid)
		self.quick.addAction(QIcon.fromTheme('edit-select-all'), 'deselect all', main.deselectall)
		self.quick.addAction(QIcon.fromTheme('edit-node'), 'graphical edit object', main._edit)
		self.quick.hide()
		
		self.selection_label = QPushButton(self)
		self.selection_label.setFont(QFont(*settings.scriptview['font']))
		self.selection_label.move(self.quick.width()*2, 0)
		self.selection_label.setToolTip('last selection, click to scroll to it')
		self.selection_label.setFlat(True)
		self.selection_label.clicked.connect(self.scroll_selection)
		self.selection_label.hide()
	
		self.statusbar = SceneViewBar(self)
		self.scene.changed.connect(self.update)
		
	def initializeGL(self):
		super().initializeGL()
		self.scene.ctx.gc_mode = 'context_gc'
	
	def closeEvent(self, event):
		# never close the first openned view, this avoids a Qt bug deleting the context, or something similar
		if next((view for view in self.main.views if isinstance(view, SceneView)), None) is self:
			event.ignore()
			return
		
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
		elif evt.type() == QEvent.PaletteChange and madcad.settings.display['system_theme'] and self.scene.ctx:
			self.scene.sync()
		return super().changeEvent(evt)
		
	def resizeEvent(self, evt):
		super().resizeEvent(evt)
		self.quick.setGeometry(2, 0, 1+self.quick.sizeHint().width(), self.height())
		
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
				if hasattr(disp, '__iter__'):
					disp.selected = any(sub.selected	for sub in disp)
			self.scene.selected = any(sub.selected    for sub in self.scene.displays.values())
			
			if disp.selected:
				self.scene.active_selection = key
				self.update_active_selection()
			elif not disp.selected and self.scene.active_selection == key:
				self.scene.active_selection = None
				self.update_active_selection()
			self.scene.touch()
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
	
	def update_active_selection(self):
		if self.scene.active_selection:
			text = format_scenekey(self.scene, self.scene.active_selection)
		
			pointsize = self.selection_label.font().pointSize()
			self.selection_label.setText(text)
			self.selection_label.resize(pointsize*len(text), pointsize*2)
			self.selection_label.show()
		else:
			self.selection_label.hide()
	
	def showdetail(self, key, position=None):
		''' display a detail window for the ident given (grp,sub) '''
		if key in self.main.details:	
			self.main.details[key].activateWindow()
			return
		
		disp = self.scene.item(key)
		if not disp or not hasattr(disp, 'source') or not isinstance(disp.source, (Mesh,Web)):
			return
		
		detail = DetailView(self.scene, key)
		detail.move(self.mapToGlobal(self.geometry().center()))
		detail.show()
	
		if position:
			if position.x() < self.width()//2:	offsetx = -400
			else:								offsetx = 100
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
		
	def adapt(self):
		box = self.scene.selectionbox() or self.scene.box()
		self.center(box.center)
		self.adjust(box)
		
	def normalview(self):
		if not self.scene.active_selection:	return
		disp = self.scene.item(self.scene.active_selection)
		if not disp or not disp.source:	return
		source = disp.source
		world = disp.world
		
		if not isinstance(source, (Mesh,Web,Wire)) and hasattr(source, 'mesh'):
			source = source.mesh()
		
		if isinstance(source, (Mesh,Web,Wire)):
			mesh = source.group(self.scene.active_selection[-1])
			center = mesh.barycenter()
			direction = vec3(transpose(fmat3(world)) * fvec3(transpose(self.navigation.matrix())[2]))
			
			# set view orthogonal to the closest face normal
			if isinstance(mesh, Mesh):
				f = max(mesh.faces, key=lambda f: dot(mesh.facenormal(f), direction))
				normal = mesh.facenormal(f)
			# set view normal to the two closest edges
			elif isinstance(mesh, (Web,Wire)):
				if isinstance(mesh, Web):	it = mesh.edges
				else:						it = mesh.edges()
				es = sorted(it, key=lambda e: abs(dot(mesh.edgedirection(e), direction)))
				if len(es) > 1:
					normal = cross(mesh.edgedirection(es[0]), mesh.edgedirection(es[1]))
				elif len(es):
					x = mesh.edgedirection(es[0])
					normal = cross(normalize(cross(x, direction)), x)
			else:
				return
			
			if dot(direction, normal) > 0:
				normal = -normal
				
			center = mat4(world) * center
			normal = mat3(fmat3(world)) * normal
			
			if isinstance(self.navigation, Turntable):
				self.navigation.center = fvec3(center)
				self.navigation.yaw = atan2(normal.x, normal.y)
				self.navigation.pitch = -atan(normal.z, length(normal.xy))
			elif isinstance(self.navigation, Orbit):
				self.navigation.center = fvec3(center)
				self.navigation.orient *= fquat(quat(direction, normal))
			else:
				return
				
			self.update()
			
	def projectionswitch(self):
		if isinstance(self.projection, Perspective):
			self.projection = Orthographic()
		else:
			self.projection = Perspective()
		self.update()
		
	def set_option(self, option, value):
		self.scene.options[option] = value
		self.scene.touch()
		
	def scroll_selection(self):
		if not self.scene.active_selection or not self.main.active_scriptview:	
			return
		try:	disp = self.scene.item(self.scene.active_selection)
		except KeyError:	
			self.active_selection = None
			self.update_active_selection()
			return
		it = self.main.interpreter
		if not hasattr(disp, 'source') or id(disp.source) not in it.ids:	
			return
		self.main.active_scriptview.seek_position(it.locations[it.ids[id(disp.source)]].position)
		self.main.active_scriptview.editor.setFocus(True)
		

class SceneViewBar(QWidget):
	''' statusbar for a sceneview, containing scene management tools '''
	def __init__(self, sceneview, parent=None):
		super().__init__(parent)
		self.sceneview = sceneview
		
		self.scenes = scenes = QComboBox()
		scenes.setFrame(False)
		def callback(i):
			self.sceneview.set_scene(self.sceneview.main.scenes[i])
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
			scenes.setCurrentIndex(len(sceneview.main.scenes)-1)
		
		self.compose = btn('madcad-compose', help='force some objects to display')
		self.compose.clicked.connect(self.show_composition)
		
		layout = QHBoxLayout()
		layout.addWidget(self.scenes)
		layout.addWidget(btn('list-add', separate_scene, 'duplicate scene'))
		layout.addWidget(QWidget())
		layout.addWidget(self.compose)
		layout.addWidget(btn('dialog-close-icon', sceneview.close, 'close view'))
		self.setLayout(layout)
	
	def show_composition(self):
		composition = self.sceneview.scene.composition
		# show the composition window
		composition.show()
		composition.activateWindow()
		composition.setFocus()
		# place it below the button
		psize = self.compose.size()
		composition.move(self.compose.mapToGlobal(QPoint(0,0)) + QPoint(
				psize.width()-composition.width(), 
				psize.height(),
				))
		
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


class PlainTextEdit(QPlainTextEdit):
	''' text view to specify objects main.currentenv we want to append to main.scene '''
	def __init__(self, parent=None):
		super().__init__(parent)
		self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
		
	def sizeHint(self):
		return QSize(20, self.document().lineCount())*self.document().defaultFont().pointSize()


class SceneComposition(QWidget):
	def __init__(self, scene, parent=None):
		super().__init__(parent)
		self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint)
		self.scene = scene
		
		layout = QVBoxLayout()
		
		layout.addWidget(QLabel('show'))
		
		btn = QCheckBox('show all')
		btn.toggled.connect(scene.main._display_all)
		layout.addWidget(btn)
		
		self.showlist = PlainTextEdit()
		self.showlist.setPlaceholderText('variable names separated by spaces or newlines')
		self.showlist.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
		self.showlist.document().contentsChange.connect(self._contentsChange)
		layout.addWidget(self.showlist)
		
		layout.addWidget(QLabel('hide'))
		
		btn = QCheckBox('hide all')
		btn.toggled.connect(scene.main._display_none)
		layout.addWidget(btn)
		
		self.hidelist = PlainTextEdit()
		self.hidelist.setPlaceholderText('variable names separated by spaces or newlines')
		self.hidelist.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
		self.hidelist.document().contentsChange.connect(self._contentsChange)
		layout.addWidget(self.hidelist)
		
		layout.addWidget(QSizeGrip(self))
		
		self.setLayout(layout)
		self.setFocusProxy(self.showlist)
		
	def auto_resize(self):
		pointsize = self.showlist.document().defaultFont().pointSize()
		self.setMinimumSize(QSize(15,15)*pointsize)
		self.resize(30*pointsize, (self.showlist.document().lineCount() + self.hidelist.document().lineCount()+10) * pointsize*2)
	
	def _contentsChange(self):
		self.scene.showset = set(self.showlist.document().toPlainText().split())
		self.scene.hideset = set(self.hidelist.document().toPlainText().split())
		self.scene.sync()
	
	def changeEvent(self, evt):
		if not self.isActiveWindow():
			self.setVisible(False)
		
		


class Grid(GridDisplay):
	def __init__(self, scene, **kwargs):
		super().__init__(scene, fvec3(0), **kwargs)
	
	def stack(self, scene):
		if scene.options['display_grid']:	return super().stack(scene)
		else: 								return ()
	
	def render(self, view):
		self.center = view.navigation.center
		super().render(view)


