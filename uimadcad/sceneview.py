from functools import partial
from operator import itemgetter

from madcad.qt import (
	Qt, QObject, QEvent, 
	QPoint, QMargins, QFont, 
	QWidget, QPushButton, QCheckBox, QComboBox, QLabel, QSizePolicy,
	)

import madcad
from madcad.rendering import Perspective, Orthographic, Turntable, Orbit, Group
from madcad.mathutils import *
from . import settings
from .utils import *


QEventGLContextChange = 215	# opengl context change event type, not yet defined in PyQt5

class Scene(madcad.rendering.Scene, QObject):
	def __init__(self, app, *args, **kwargs):
		# data graph setup
		QObject.__init__(self)
		madcad.rendering.Scene.__init__(self, *args, **kwargs)
		self.app = app
		app.scenes.append(self)
		
		# prevent reference-loop in groups (groups are taken from the execution env, so the user may not want to display it however we are trying to)
		self.memo = set()
		# scene data
		self.additions = {		# systematic scene additions
			'__grid__': madcad.rendering.Displayable(Grid),
			}
		# application behavior
		self.composer = SceneComposer(self)
		self.sync()
		
	def sync(self):
		''' synchronize the scene content with the rest of the application '''
		keys = set()
		# hide_all is hidding all default displays
		if not self.composer.hide_all:
			# default displays are the writen only variables
			for key in self.app.intepreter.wo:
				keys.add(key)
		# show_all is showing all variables in the scopes
		if self.composer.show_all:
			for key in self.app.interpreter.scopes:
				keys.add(key)
		# hide_set selects displays to hide despite previous settings
		for key in self.composer.hide_set:
			keys.discard(key)
		# show set selects displays to show despite previous settings
		for key in self.composer.show_set:
			keys.add(key)
		
		# recreate the scene dictionnary
		new = {}
		for key in keys:
			obj = self.app.interpreter.scopes.get(key, None)
			if obj is not None:
				new[key] = obj
		new.update(self.additions)
		
		super().sync(new)
	
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
				
				# selected objects are showing their annotations
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
	
	def display(self, obj, former=None):
		# TODO: implement this recursion check in pymadcad rather than uimadcad
		ido = id(obj)
		assert ido not in self.memo, 'there should not be recursion loops in cascading displays'
		
		self.memo.add(ido)
		try:		disp = super().display(obj, former)
		except Exception as err:     
			self.app.showerror(err)
			raise
		finally:	self.memo.remove(ido)
		disp.source = obj
		return disp
	
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

		

class SceneView(madcad.rendering.View):
	''' dockable and reparentable scene view widget, bases on madcad.Scene '''
	
	bar_margin = 0
	
	def __init__(self, app, scene=None, **kwargs):
		self.app = app
		
		# try to reuse existing scene
		if scene:
			pass
		elif app.active.sceneview:
			scene = app.active.sceneview.scene
		elif app.scenes:
			scene = app.scenes[0]
		else:
			scene = Scene(app)
		print(scene is app.scenes[0], scene, app.scenes)
		
		super().__init__(scene, **kwargs)
		print(self.scene is app.scenes[0], self.scene)
		
		if app.active.sceneview:
			self.navigation = deepcopy(app.active.sceneview.navigation)
			self.projection = deepcopy(app.active.sceneview.projection)
		
		Initializer.init(self)
		self.setMinimumSize(100,100)
		self.setSizePolicy(QSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum))
		
		app.views.append(self)
		if not app.active.sceneview:	app.active.sceneview = self
		
		# toolbars
		self.top = ToolBar('scene', [
			self.new_view,
			self.open_composer,
			spacer(5, 0),
			self.scroll_selection,
			],
			orientation=Qt.Horizontal,
			margins=QMargins(3,3,3,0),
			parent=self)
		
		self.left = ToolBar('display', [
			self.display_points,
			self.display_wire,
			self.display_faces,
			self.display_groups,
			self.display_annotations,
			self.display_grid,
			None,
			self.mode_free,
			None,
			self.mode_joint,
			self.mode_translate,
			self.mode_rotate,
			# Button(icon='madcad-kinematic-joint', flat=True, menu=Menu('some', [
			# 	self.mode_joint,
			# 	self.mode_translate,
			# 	self.mode_rotate,
			# 	])),
			], 
			orientation=Qt.Vertical, 
			margins=QMargins(3,3,0,3),
			parent=self)
		self.right = ToolBar('view', [
			self.projection_switch,
			self.view_adjust,
			self.view_normal,
			Button(icon='madcad-standard-view', flat=True, menu=Menu('standard views', [
				self.view_mz, self.view_pz,
				self.view_mx, self.view_px,
				self.view_my, self.view_py,
				])),
			None,
			# self.selection_mode,
			# self.direction_selector,
			# None,
			# self.reset_pose,
			# self.set_pose,
			], 
			orientation=Qt.Vertical, 
			margins=QMargins(0,3,3,3),
			parent=self)
			
		group([self.mode_joint, self.mode_translate, self.mode_rotate], self)
		
		self._update_active_scene()
		self._update_active_selection()
		
	def initializeGL(self):
		super().initializeGL()
		self.scene.ctx.gc_mode = 'context_gc'
	
	def closeEvent(self, event):
		# never close the first openned view, this avoids a Qt bug deleting the context, or something similar
		if next((view for view in self.app.views if isinstance(view, SceneView)), None) is self:
			event.ignore()
			return
		
		self.app.views.remove(self)
		if self.app.active.sceneview is self:
			self.app.active.sceneview = None
	
	def focusOutEvent(self, event):
		self._toolbars_visible(False)
		
	def focusInEvent(self, event):
		self._toolbars_visible(True)
		self._update_active_scene()
		self.open_composer.setChecked(False)
	
	def changeEvent(self, evt):
		# update scene when color changes
		if evt.type() == QEvent.PaletteChange and madcad.settings.display['system_theme'] and self.scene.ctx:
			self.scene.sync()
		return super().changeEvent(evt)
		
	def resizeEvent(self, evt):
		super().resizeEvent(evt)
		self.left.setGeometry(
			self.bar_margin, 
			max(0, self.height()//2 - self.left.sizeHint().height()//2),
			self.left.sizeHint().width(),
			min(self.height(), self.left.sizeHint().height()),
			)
		self.right.setGeometry(
			self.width() - self.right.sizeHint().width() - self.bar_margin, 
			max(0, self.height()//2 - self.right.sizeHint().height()//2),
			self.right.sizeHint().width(), 
			min(self.height(), self.right.sizeHint().height()),
			)
		if self.top.parent() is self:
			self.top.setGeometry(
				self.bar_margin+self.left.width(), 
				self.bar_margin,
				self.width()-self.left.width() - self.bar_margin,
				self.top.sizeHint().height(),
				)
		
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
				self._update_active_selection()
			elif not disp.selected and self.scene.active_selection == key:
				self.scene.active_selection = None
				self._update_active_selection()
			self.scene.touch()
			self.update()
			self.app.updatescript()
			evt.accept()
		
		# show details
		elif evt.type() == QEvent.MouseButtonRelease and evt.button() == Qt.RightButton:
			self._show_details(key, evt.pos())
			evt.accept()
		
		# edition
		elif evt.type() == QEvent.MouseButtonDblClick and evt.button() == Qt.LeftButton and hasattr(disp, 'source'):
			name = self.app.interpreter.ids.get(id(disp.source))
			if name:	
				if name in self.app.editors:
					self.app.finishedit(name)
				else:
					self.app.edit(name)
				evt.accept()
	
	def _update_active_scene(self):
		self.open_composer.setText('scene:{}'.format(self.app.scenes.index(self.scene)))
		self.update()
	
	def _update_active_selection(self):
		# if self.scene.active_selection:
		if True:
			# text = format_scenekey(self.scene, self.scene.active_selection)
			text = "machin['truc'].bidule"
		
			font = QFont(*settings.scriptview['font'])
			pointsize = font.pointSize()
			self.scroll_selection.setFont(font)
			self.scroll_selection.setText(text)
			self.scroll_selection.resize(pointsize*len(text), pointsize*2)
			self.scroll_selection.show()
		else:
			self.scroll_selection.hide()
	
	def _show_details(self, key, position=None):
		''' display a detail window for the ident given (grp,sub) '''
		if key in self.app.details:	
			self.app.details[key].activateWindow()
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
		self.set_scene(Scene(self.app, ctx=self.scene.ctx))
		self.preload()
		self.scene.sync()
		
	def set_scene(self, new):
		if self.scene:
			self.scene.changed.disconnect(self.update)
		self.scene = new
		self.scene.changed.connect(self.update)
		self.update()
	
	def _toolbars_visible(self, enable):
		self.right.setVisible(enable)
		self.left.setVisible(enable)
	
	@button(icon='view-dual-symbolic', flat=True, shortcut='Shift+V')
	def new_view(self):
		''' create a new view widget '''
		self.app.window.new_sceneview()
		
	@button(flat=True, checked=False, shortcut='Shift+C')
	def open_composer(self, show):
		''' set the scene to render and its content '''
		if show:
			self.scene.composer.view = self
			self.scene.composer.setParent(self)
			self.scene.composer.setGeometry(
				self.left.width(), 
				0, 
				self.scene.composer.sizeHint().width(),
				min(self.height(), self.scene.composer.sizeHint().height()),
				)
			self.scene.composer.show()
			self.scene.composer.setFocus(True)
		else:
			self.scene.composer.hide()
			self.setFocus(True)
	
	@button(flat=True, shortcut='Home')
	def scroll_selection(self):
		''' last selection, click to scroll to it '''
		indev
	
	@button(icon='view-fullscreen', flat=True, shortcut='C')
	def view_adjust(self):
		''' center and zoom to displayed objects '''
		box = self.scene.selectionbox() or self.scene.box()
		self.center(box.center)
		self.adjust(box)
	
	@button(icon='madcad-view-normal', flat=True, shortcut='N')
	def view_normal(self):
		''' move the view orthogonal to the selected surface '''
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
	
	@button(icon='madcad-projection', flat=True, shortcut='Shift+S')
	def projection_switch(self):
		''' switch between perspective and orthographic projection 
		
			- orthographic guaratees to show close and far objects at the same scale
			- perspective shows far objects smaller and close objects bigger
		'''
		if isinstance(self.projection, Perspective):
			self.projection = Orthographic()
		else:
			self.projection = Perspective()
		self.update()
	
	def _scene_setting(key, **kwargs):
		@button(
			name='', #key.replace('_', ' '),
			flat=True, 
			checked=madcad.settings.scene[key],
			**kwargs
			)
		def callback(self, value):
			self.scene.options[key] = value
			self.scene.touch()
			self.update()
		return callback
	
	display_points = _scene_setting('display_points', 
		icon='madcad-display-points', 
		description='display mesh points',
		shortcut='Shift+P')
	display_faces = _scene_setting('display_faces', 
		icon='madcad-display-faces', 
		description='display mesh surface',
		shortcut='Shift+F')
	display_wire = _scene_setting('display_wire', 
		icon='madcad-display-wire', 
		description='display mesh triangulations',
		shortcut='Shift+W')
	display_groups = _scene_setting('display_groups', 
		icon='madcad-display-groups',
		description='display mesh groups frontiers',
		shortcut='Shift+G')
	display_annotations = _scene_setting('display_annotations', 
		icon='madcad-annotation',
		description='display annotation and schematics',
		shortcut='Shift+A')
	display_grid = _scene_setting('display_grid', 
		icon='view-app-grid-symbolic',
		description='display metric a grid in the background',
		shortcut='Shift+B')
	
	@button(icon='madcad-solid-freemove', flat=True, shortcut='F', checked=False)
	def mode_free(self):
		''' move solids freely in the view '''
		self.scene.options['solid-move'] = False
	
	@button(icon='madcad-kinematic-joint', flat=True, shortcut='J', checked=True)
	def mode_joint(self):
		''' move kinematic joint by joint whenever possible '''
		self.scene.options['kinematic-mode'] = 'joint'
	
	@button(icon='madcad-kinematic-translate', flat=True, shortcut='T', checked=False)
	def mode_translate(self):
		''' move kinematic by translating solids '''
		self.scene.options['kinematic-mode'] = 'translate'
	
	@button(icon='madcad-kinematic-rotate', flat=True, shortcut='R', checked=False)
	def mode_rotate(self):
		''' move kinematic by rotating solids '''
		self.scene.options['kinematic-mode'] = 'rotate'

		
	def _standard_view(direction, name, shortcut, orientation):
		@action(
			name='{} {}'.format(direction, name), 
			description='{} view: toward {}'.format(name, direction),
			shortcut=shortcut,
			)
		def callback(self):
			nav = self.navigation
			if isinstance(nav, Turntable):
				nav.yaw = roll(orientation)
				nav.pitch = pi/2 - pitch(orientation)
			elif isinstance(nav, Orbit):
				nav.orient = orientation
			else:
				raise TypeError('navigation type {} is not supported for standard views'.format(type(nav)))
			self.update()
		return callback
	
	view_mz = _standard_view('-Z', 'top', shortcut='Y', orientation=fquat(fvec3(0, 0, 0)))
	view_pz = _standard_view('+Z', 'bottom', shortcut='Shift+Y', orientation=fquat(fvec3(pi, 0, 0)))
	view_mx = _standard_view('-X', 'front', shortcut='U', orientation=fquat(fvec3(pi/2, 0, 0)))
	view_px = _standard_view('+X', 'back', shortcut='Shift+U', orientation=fquat(fvec3(pi/2, 0, pi)))
	view_my = _standard_view('-Y', 'right', shortcut='I', orientation=fquat(fvec3(pi/2, 0, -pi/2)))
	view_py = _standard_view('+Y', 'left', shortcut='Shift+I', orientation=fquat(fvec3(pi/2, 0, pi/2)))
	


class SceneComposer(QWidget):
	def __init__(self, scene, parent=None):
		super().__init__(parent)
		Initializer.init(self)
		self.scene = scene
		
		self.hide_all = False
		self.show_all = False
		self.hide_set = set()
		self.show_set = set()
		
		self.scene_selector = QComboBox()
		self.scene_selector.activated.connect(self._scene_change)
		self.scene_selector.setToolTip("select the scene to display in the view")
		
		self.show_all = Button(name='all', checked=False, 
			description="show all objects in all scopes, except those in the hiding list below")
		self.show_all.clicked.connect(self._content_change)
		
		self.show_list = PlainTextEdit()
		self.show_list.setPlaceholderText("variable names separated by spaces or newlines")
		self.show_list.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
		self.show_list.document().contentsChange.connect(self._content_change)
		
		self.hide_all = Button(name='all', checked=False,
			description="hide all objects in all scopes, except those in the show list above")
		self.hide_all.clicked.connect(self._content_change)
		self.hide_list = PlainTextEdit()
		self.hide_list.setPlaceholderText("variable names separated by spaces or newlines")
		self.hide_list.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
		self.hide_list.document().contentsChange.connect(self._content_change)
		
		self.setLayout(vlayout([
			QLabel('scene selection'),
			hlayout([self.scene_remove, self.scene_selector, self.scene_add]),
			QLabel('scene composition'),
			hlayout([QLabel('show'), self.show_all]),
			self.show_list,
			hlayout([QLabel('hide'), self.hide_all]),
			self.hide_list,
			]))
		
# 		selector = QGroupBox('scene')
# 		selector.setLayout(hlayout([self.scene_remove, self.scene_selector, self.scene_add]))
# 		
# 		composition = QGroupBox('composition')
# 		composition.setLayout(vlayout([
# 			hlayout([QLabel('show'), self.show_all]),
# 			self.show_list,
# 			hlayout([QLabel('hide'), self.hide_all]),
# 			self.hide_list,
# 			]))
# 			
# 		self.setLayout(vlayout([selector, composition]))
			
	def focusInEvent(self, evt):
		self._update_scenes()
			
	def _update_scenes(self):
		self.scene_selector.clear()
		for i, scene in enumerate(self.scene.app.scenes):
			self.scene_selector.addItem(str(i))
			if scene is self.scene:
				self.scene_selector.setCurrentIndex(i)
		
	def _update_active_scene(self):
		self.view._update_active_scene()
		self.hide()
		self.view.scene.composer.view = self.view
		self.view.scene.composer.setParent(self.view)
		self.view.scene.composer.move(self.pos())
		self.view.scene.composer.show()
		self.view.scene.composer.setFocus(True)
			
	def _scene_change(self, index):
		self.view.scene = self.scene.app.scenes[index]
		self._update_active_scene()
		
	def _content_change(self):
		self.scene.sync()
	
	@button(icon='list-add-symbolic', flat=True)
	def scene_add(self):
		''' create a new scene '''
		former = self.view.scene
		# self.view.scene = Scene(self.scene.app, 
		# 	ctx = former.ctx, 
		# 	options = former.options,
		# 	)
		# self.view.scene = madcad.rendering.Scene(
		# 	{'sphere':madcad.icosphere(vec3(0),1)},
		# 	ctx = former.ctx, 
		# 	options = former.options,
		# 	)
		print(former is self.view.app.scenes[0], former)
		former.update({'sphere':madcad.icosphere(vec3(0),1), 'base2':mat4()})
		print(former.displays, former.queue)
		self.view.makeCurrent()
		with self.view.scene.ctx:
			self.view.preload()
			self.view.init()
			
			# former.dequeue()
			# print(former.displays, former.queue)
			# from pnprint import nprint
			# nprint(former.stacks)
		
			# self.view.scene.touch()
			# self.view.scene.restack()
			# self.view.scene.ctx.finish()
			# self.view.fb_screen.use()
			# self.view.fb_screen.clear()
			# self.view.scene.resources['shader_ident'] = former.resources['shader_ident']
			# self.view.scene.resources['shader_subident'] = former.resources['shader_subident']
		# self._update_active_scene()
		
	@button(icon='list-remove-symbolic', flat=True)
	def scene_remove(self):
		''' delete this scene '''
		self.view.app.scenes.pop(self.view.app.scenes.index(self.scene))
		if self.view.app.scenes:
			self.view.scene = self.view.app.scenes[0]
			self._update_active_scene()
		else:
			self.scene_add.trigger()


class Grid(madcad.displays.GridDisplay):
	def __init__(self, scene, **kwargs):
		super().__init__(scene, fvec3(0), **kwargs)
	
	def stack(self, scene):
		if scene.options['display_grid']:	return super().stack(scene)
		else: 								return ()
	
	def render(self, view):
		self.center = view.navigation.center
		super().render(view)
