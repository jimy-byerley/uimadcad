from functools import partial
from operator import itemgetter

import numpy as np
import moderngl as mgl

from madcad.qt import (
	Qt, QObject, QEvent, 
	QPoint, QMargins, QFont, 
	QWidget, QPushButton, QCheckBox, QComboBox, QLabel, QSizePolicy, QButtonGroup, QActionGroup,
	QTextCursor,
	QGroupBox,
	)

import madcad
from madcad.rendering import Perspective, Orthographic, Turntable, Orbit, Group, displayable
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
		
		# selected displays
		self.selection = Selection()
		self.active = None
		# prevent reference-loop in groups (groups are taken from the execution env, so the user may not want to display it however we are trying to)
		self.memo = set()
		# scene data
		self.additions = {		# systematic scene additions
			'__grid__': madcad.rendering.Displayable(Grid),
			'__highlight__': madcad.rendering.Displayable(Highlight),
			}
		# application behavior
		self.composer = SceneComposer(self)
		self.sync()
		
		self.app.scenes.append(self)
		
		
	def sync(self):
		''' synchronize the scene content with the rest of the application '''
		# name = self.app.active.scope
		name = self.app.interpreter.filename # TODO: remove this debug value
		scope = self.app.interpreter.scopes.get(name)
		usage = self.app.interpreter.usages.get(name)
			
		# from pnprint import nprint
		# nprint('usage', usage)
		
		keys = set()
		if usage is not None:
			# hide_all is hidding all default displays
			if not self.composer.hide_all:
				# default displays are the writen only variables
				for key in usage.wo:
					keys.add(key)
				for key in usage.ro:
					keys.add(key)
			# show_all is showing all variables in the scopes
			if self.composer.show_all:
				for key in scope:
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
			if key.startswith('_madcad_'):
				continue
			obj = scope.get(key, None)
			if displayable(obj):
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
		try:		
			disp = super().display(obj, former)
		except Exception as err:     
			self.app.window.panel.set_exception(err)
			self.app.window.open_panel.setChecked(True)
			raise
		finally:
			self.memo.remove(ido)
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
		
	def select(self, key, sub=()):
		''' select the object matchnig the given key '''
		self.selection.add(key)
		self.active = (key, sub)
		
	def deselect(self, key):
		''' deselect the object matching the given key '''
		self.selection.discard(key)
		
	def clear_selection(self):
		''' clear selection index and deselect displays '''
		def clear(display, selection):
			if selection is None:
				display.selected = False
			else:
				for k, sub in selection.items():
					try:
						clear(display[k], sub)
					except (KeyError, IndexError):
						continue
		clear(self.displays, self.selection.root)
		self.selection.clear()
		self.active = None
		


class SceneView(madcad.rendering.View):
	''' dockable and reparentable scene view widget, bases on madcad.Scene '''
	
	bar_margin = 0
	
	def __init__(self, app, scene=None, **kwargs):
		self.app = app
		self.hover = None
		self._last_empty = True
		
		# try to reuse existing scene
		if scene:
			pass
		elif self.app.active.sceneview:
			scene = self.app.active.sceneview.scene
		elif self.app.scenes:
			scene = self.app.scenes[0]
		else:
			scene = Scene(self.app)
		
		super().__init__(scene, **kwargs)
		self.setMinimumSize(100,100)
		self.setSizePolicy(QSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.MinimumExpanding))
		self.handler.setMouseTracking(True)
		Initializer.process(self)
		self._init_scene_settings()
		
		# toolbars
		self.top = ToolBar('scene', [
			self.new_view,
			self.open_composer,
			spacer(5, 0),
			self.seek_selection,
			self.select_parent,
			self.select_child,
			],
			orientation=Qt.Horizontal,
			margins=QMargins(3,3,3,0),
			icon_size='small',
			parent=self)
		
		self.left = ToolBar('display', [
			self.display_points,
			self.display_wire,
			self.display_faces,
			self.display_groups,
			self.display_annotations,
			self.display_grid,
			None,
			self.solid_freemove,
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
			icon_size='small',
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
			# None,
			# self.selection_mode,
			# self.direction_selector,
			# None,
			# self.reset_pose,
			# self.set_pose,
			], 
			orientation=Qt.Vertical, 
			margins=QMargins(0,3,3,3),
			icon_size='small',
			parent=self)
		
		self._update_active_scene()
		self._update_active_selection()
		self._toolbars_visible(False)
	
	def init(self):
		import numpy as np
		ctx = self.scene.ctx
		assert ctx, 'context is not initialized'
		
		size = ivec2(self.width(), self.height())
		# if the size is not a multiple of 4, it seems that openGL or Qt doesn't understand its strides well
		m = 4
		size += (-size%m)
		
		# release framebuffers before reinitializing them
		if self.fb_final:
			if size == self.fb_final.size:
				return
			self.fb_final.release()
			self.fb_screen.release()
			self.fb_ident.release()
			self.map_ident = None
			self.map_depth = None
			self.map_color = None

		ident_samples = 2
		self.fb_final = ctx.simple_framebuffer(size)
		self.fb_screen = ctx.simple_framebuffer(size, samples=4)
		self.tx_ident = ctx.texture(ident_samples*size, components=1, dtype='u2')
		self.tx_depth = ctx.depth_texture(ident_samples*size)
		self.fb_ident_multi = ctx.framebuffer(self.tx_ident, self.tx_depth)
		self.fb_ident = ctx.framebuffer(ctx.renderbuffer(size, components=1, dtype='u2'), ctx.depth_renderbuffer(size))
		self.targets = [ 
			('ident', self.fb_ident_multi, self.setup_ident),
			('screen', self.fb_screen, self.setup_screen),
			]
		w, h = size
		self.downsample_ident = DownsampleIdent(self.scene)
		
		self.map_ident = madcad.rendering.CheapMap(self.fb_ident, attachment=0)
		self.map_depth = madcad.rendering.CheapMap(self.fb_ident, attachment=-1)
		self.map_color = np.empty((h,w,3), dtype='u1')
		
	def render(self):
# 		self.init()
# 		empty = ()
# 		selected = []
# 		for target, frame, setup in self.targets:
# 			if target != 'ident':
# 				continue
# 			frame = self.fb_ident_multi
# 			self.target = frame
# 			frame.use()
# 			frame.clear()
# 			setup()
# 			for key, priority, func in self.scene.stacks.get(target,empty):
# 				if self.scene.selection.isabove(key) or self.hover and beginwith(key, self.hover):
# 					print('render selected', key)
# 					func(self)
		
		super().render()
		self.fb_ident.use()
		self.downsample_ident.render(self)
	
	def paintEvent(self, evt):
		# if scene is no more empty, adjust the view automatically
		empty = self.scene.box().isempty()
		if not empty and self._last_empty:
			self.adjust()
		self._last_empty = empty
		# proceed to rendering normally
		super().paintEvent(evt)
	
	def showEvent(self, event):
		self.app.views.add(self)
		if not self.app.active.sceneview:	
			self.app.active.sceneview = self
	
	def hideEvent(self, event):
		self.app.views.discard(self)
		if self.app.active.scriptview is self:
			self.app.active.scriptview = None
		
	def focusInEvent(self, event):
		self.app.active.sceneview = self
		self._retreive_scene_options()
		self._toolbars_visible(True)
		self._update_active_scene()
		self.open_composer.setChecked(False)
		self.app.window.clear_panel(self)
		# self.app.window.open_panel.setChecked(False)
		super().focusInEvent(event)
	
	def focusOutEvent(self, event):
		self._toolbars_visible(False)
		super().focusOutEvent(event)
	
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
		
	def inputEvent(self, event):
		# deselection at any click when shift is not held
		if event.type() == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton and not event.modifiers() & Qt.ShiftModifier:
			self.scene.clear_selection()
			self.update()
		# hover objects
		elif event.type() == QEvent.MouseMove and event.buttons() == Qt.NoButton:
			pos = self.somenear(event.pos())
			if pos:
				item = self.itemat(pos)[:-1]
				if item != self.hover:
					self.hover = item
					self.update()
			else:
				self.hover = None
				self.update()
			return
		# reimplement top bar shortcuts here because Qt cannot deambiguate which view the shortcut belongs to
		if event.type() == QEvent.KeyPress:
			event.accept()
			if event.key() == Qt.Key_Return and event.modifiers() & Qt.AltModifier:
				self.open_composer.setChecked(True)
			elif event.key() == Qt.Key_Up and event.modifiers() & Qt.AltModifier:
				self.seek_selection.click()
			else:
				event.ignore()
				return super().inputEvent(event)
		else:
			event.ignore()
			return super().inputEvent(event)
	
	def control(self, key, evt):
		''' overwrite the Scene method, to implement the edition behaviors '''
		self.update()
		disp = self.scene.displays
		stack = []
		for i in range(1,len(key)):
			disp = disp[key[i-1]]
			path, sub = key[:i], key[i:]
			disp.control(self, path, sub, evt)
			# update selection index
			if disp.selected:
				self.scene.selection.add(path)
				self.scene.active = path
			# stop at first parent display catching it
			if evt.isAccepted():  break
			stack.append(disp)
		
		# show details
		if evt.type() == QEvent.MouseButtonRelease and evt.button() == Qt.RightButton:
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
			self.seek_selection.setFont(font)
			self.seek_selection.setText(text)
			# self.seek_selection.resize(pointsize*(len(text)+2), self.seek_selection.height())
			self.seek_selection.show()
		else:
			self.seek_selection.hide()
	
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
	
	def _toolbars_visible(self, enable):
		self.right.setVisible(enable)
		self.left.setVisible(enable)
	
	
	def separate_scene(self):
		''' create a new Scene and set it to the current view '''
		self.set_scene(Scene(self.app, ctx=self.scene.ctx))
		self.preload()
		self.scene.sync()
		
	def set_scene(self, new):
		''' set the scene rendered in the view '''
		if self.scene:
			self.scene.changed.disconnect(self.update)
		self.scene = new
		self.scene.changed.connect(self.update)
		self.update()
	
	def orient(self, orientation: fquat):
		''' change the view orinetation around its center using the given rotation '''
		nav = self.navigation
		if isinstance(nav, Turntable):
			nav.yaw = roll(orientation)
			nav.pitch = pi/2 - pitch(orientation)
		elif isinstance(nav, Orbit):
			nav.orient = orientation
		else:
			raise TypeError('navigation type {} is not supported for standard views'.format(type(nav)))
		self.update()
	
	
	@action(icon='view-dual')
	def new_view(self):
		''' create a new view widget '''
		self.app.window.insert_view(self, SceneView(
			self.app, 
			scene = self.scene,
			navigation = deepcopy(self.navigation),
			projection = deepcopy(self.projection),
			))
		
	@button(flat=True, checked=False) #, shortcut='Alt+Return')
	def open_composer(self, show):
		''' set the scene to render and its content 
		
			(shortcut: Alt+Return)
		'''
		if show:
			self.scene.composer.view = self
			self.scene.composer.setParent(self)
			self.scene.composer.setGeometry(
				self.left.width(), 
				0, 
				self.scene.composer.sizeHint().width(),
				min(self.height(), self.scene.composer.sizeHint().height()),
				)
			# the rest has to be made after changing parent
			self.scene.composer.setFocus()
			self.scene.composer.setVisible(True)
		else:
			self.setFocus(True)
			self.scene.composer.setVisible(False)
	
	@button(flat=True) #, shortcut='Alt+Up')
	def seek_selection(self):
		''' last selection, click to scroll to it 
		
			(shortcut: Alt+Up)
		'''
		indev
	
	@action(icon='view-fullscreen', shortcut='C')
	def view_adjust(self):
		''' center and zoom to displayed objects '''
		box = self.scene.selectionbox() or self.scene.box()
		self.center(box.center)
		self.adjust(box)
	
	@action(icon='madcad-view-normal', shortcut='N')
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
	
	@action(icon='madcad-projection', shortcut='Shift+S')
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
	
	@action(icon='go-right', shortcut='Alt+Right')
	def select_child(self):
		''' select the parent object of the active selection
			active selection is the last object you clicked 
		'''
		if not self.scene.active:
			return
		key, sub = self.scene.active
		if len(sub) < 1:
			return
		self.scene.deselect(key)
		# try:
		# 	self.scene.item(key).selected = False
		# except (KeyError, IndexError):
		# 	pass
		self.scene.select((*key, sub[0]), sub[1:])
		self.update()
	
	@action(icon='go-left', shortcut='Alt+Left')
	def select_parent(self):
		''' select the child object of the active selection
			which child it takes depends on what you clicked to select it
		'''
		if not self.scene.active:
			return
		key, sub = self.scene.active
		if len(key) < 2:
			return
		self.scene.deselect(key)
		# try:
		# 	self.scene.item(key).selected = False
		# except (KeyError, IndexError):
		# 	pass
		self.scene.select(key[:-1], (key[-1], *sub))
		self.update()
	
	# settings buttons for booleans
	_scene_options = dict(
		display_points = dict(
			description="display mesh points", 
			icon='madcad-display-points', 
			shortcut='Shift+P'),
		
		display_faces = dict(
			description='display mesh surface', 
			icon='madcad-display-faces',
			shortcut='Shift+F'),
		
		display_wire = dict( 
			icon='madcad-display-wire', 
			description='display mesh triangulations',
			shortcut='Shift+W'),
		
		display_groups = dict( 
			icon='madcad-display-groups',
			description='display mesh groups frontiers',
			shortcut='Shift+G'),
		
		display_annotations = dict( 
			icon='madcad-annotation',
			description='display annotation and schematics',
			shortcut='Shift+A'),
		
		display_grid = dict( 
			icon='view-grid',
			description='display metric a grid in the background',
			shortcut='Shift+B'),
		
		solid_freemove = dict(
			icon='madcad-solid-freemove',
			description='move solids freely in the view',
			shortcut='F',
			)
		)
	# settings buttons for kinematic manipulation mode
	_kinematic_modes = dict(
		joint = dict(
			icon='madcad-kinematic-joint',
			description='move kinematic joint by joint whenever possible',
			shortcut='J'),
		
		translate = dict(
			icon='madcad-kinematic-translate',
			description='move kinematic by translating solids',
			shortcut='T'),
		
		rotate = dict(
			icon='madcad-kinematic-rotate', 
			description='move kinematic by rotating solids',
			shortcut='R'),
		)
	
	def _init_scene_settings(self):
		''' create the settings buttons '''
		for name, kwargs in self._scene_options.items():
			setattr(self, name, Action(
				self._apply_scene_options, 
				checkable = True, 
				# name = name.replace('_', ' '),
				name = '',
				**kwargs))
		modes = QActionGroup(self)
		for name, kwargs in self._kinematic_modes.items():
			button = Action(
				self._apply_scene_options,
				checkable=True,
				# name = name.replace('_', ' '),
				name = '',
				**kwargs)
			modes.addAction(button)
			setattr(self, 'mode_'+name, button)
			
	def _retreive_scene_options(self):
		''' set all settings button states to the matching values from scene.options '''
		for name in self._scene_options:
			getattr(self, name).setChecked(self.scene.options.get(name, False))
		attr = getattr(self, 'mode_'+self.scene.options['kinematic_manipulation'], None)
		if attr:
			attr.setChecked(True)
			
	def _apply_scene_options(self):
		''' set all scene.options settings to the matching values from button states '''
		for name in self._scene_options:
			self.scene.options[name] = getattr(self, name).isChecked()
		for name in self._kinematic_modes:
			if getattr(self, 'mode_'+name).isChecked():
				self.scene.options['kinematic_manipulation'] = name
		self.scene.touch()
		self.update()
	
	def _standard_view(direction, name, shortcut, orientation):
		return action(
			name='{} {}'.format(direction, name), 
			description='{} view: toward {}'.format(name, direction),
			shortcut=shortcut,
			)(lambda self: self.orient(orientation))
	
	view_mz = _standard_view('-Z', 'top', shortcut='Y', orientation=fquat(fvec3(0, 0, 0)))
	view_pz = _standard_view('+Z', 'bottom', shortcut='Shift+Y', orientation=fquat(fvec3(pi, 0, 0)))
	view_mx = _standard_view('-X', 'front', shortcut='U', orientation=fquat(fvec3(pi/2, 0, 0)))
	view_px = _standard_view('+X', 'back', shortcut='Shift+U', orientation=fquat(fvec3(pi/2, 0, pi)))
	view_my = _standard_view('-Y', 'right', shortcut='I', orientation=fquat(fvec3(pi/2, 0, -pi/2)))
	view_py = _standard_view('+Y', 'left', shortcut='Shift+I', orientation=fquat(fvec3(pi/2, 0, pi/2)))
	


class SceneComposer(QWidget):
	''' widget for allowing to select the scene to display and what variables to display '''
	def __init__(self, scene, parent=None):
		super().__init__(parent)
		Initializer.process(self, parent=self)
		self.scene = scene
		self._spaces = 0
		
		self.hide_all = False
		self.show_all = False
		self.hide_set = set()
		self.show_set = set()
		
		self.scene_selector = QComboBox()
		self.scene_selector.activated.connect(self._scene_change)
		self.scene_selector.setToolTip("select the scene to display in the view")
		
		self.show_check = Button(name='all', checked=False, 
			description="show all objects in all scopes, except those in the hiding list below")
		self.show_check.clicked.connect(self._change)
		
		self.show_entry = PlainTextEdit()
		self.show_entry.setPlaceholderText("variable names separated by spaces or newlines")
		self.show_entry.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
		self.show_entry.document().contentsChange.connect(partial(self._entry_change, self.show_entry))
		
		self.hide_check = Button(name='all', checked=False,
			description="hide all objects in all scopes, except those in the show list above")
		self.hide_check.clicked.connect(self._change)
		self.hide_entry = PlainTextEdit()
		self.hide_entry.setPlaceholderText("variable names separated by spaces or newlines")
		self.hide_entry.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
		self.hide_entry.document().contentsChange.connect(partial(self._entry_change, self.hide_entry))
		
		selector = QGroupBox('scene')
		selector.setLayout(hlayout([self.scene_remove, self.scene_selector, self.scene_add]))
		
		composition = QGroupBox('composition')
		composition.setLayout(vlayout([
			hlayout([QLabel('show'), self.show_check]),
			self.show_entry,
			hlayout([QLabel('hide'), self.hide_check]),
			self.hide_entry,
			]))
			
		self.setLayout(vlayout([selector, composition]))
			
	def focusInEvent(self, evt):
		self._update_scenes()
		self.show_entry.setFocus()
			
	def _update_scenes(self):
		self.scene_selector.clear()
		for i, scene in enumerate(self.scene.app.scenes):
			self.scene_selector.addItem(str(i))
			if scene is self.scene:
				self.scene_selector.setCurrentIndex(i)
		
	def _update_active_scene(self):
		self.view._update_active_scene()
		self.view.scene.composer.view = self.view
		self.view.scene.composer.setParent(self.view)
		self.view.scene.composer.move(self.pos())
		self.view.scene.composer.show()
		self.view.scene.composer.setFocus(True)
		self.hide()
			
	def _scene_change(self, index):
		self.view.scene = self.scene.app.scenes[index]
		self._update_active_scene()
		
	def _change(self):
		''' update boolean flags, and update the scene '''
		self.show_all = self.show_check.isChecked()
		self.hide_all = self.hide_check.isChecked() and not self.show_all
		self.scene.sync()
		self.view.update()
		
	def _entry_change(self, entry):
		''' called when an entry has been typed to
			update the sets when a sace char has been inserted or many chars added
		'''
		# count the number of psaces, trigger only if spaces were inserted
		spaces = sum(char.isspace()  for char in entry.toPlainText())
		if spaces != self._spaces:
			self._spaces = spaces
			
			# update sets
			self.show_set = set(self.show_entry.toPlainText().split())
			self.hide_set = set(self.hide_entry.toPlainText().split())
			
			self._change()

	@button(icon='list-add-symbolic', flat=True)
	def scene_add(self):
		''' create a new scene '''
		former = self.view.scene
		self.view.scene = Scene(self.scene.app, 
			ctx = former.ctx, 
			options = former.options,
			)
		self._update_active_scene()
		
	@button(icon='list-remove-symbolic', flat=True)
	def scene_remove(self):
		''' delete this scene '''
		self.view.app.scenes.pop(self.view.app.scenes.index(self.scene))
		if self.view.app.scenes:
			self.view.scene = self.view.app.scenes[0]
			self._update_active_scene()
		else:
			self.scene_add.trigger()

class Selection:
	__slots__ = 'root'
	
	def __init__(self):
		self.root = {}
	
	def add(self, key):
		if not key:
			return
		node = self.root
		for i in range(len(key)-1):
			k = key[i]
			# create recursive nodes until the terminal node
			if k not in node:
				node[k] = {}
			# if we find an early terminal node, consider key is already in the selection
			if node[k] is None:
				return
			node = node[k]
		# create terminal node
		node[key[-1]] = None
	
	def discard(self, key):
		if not key:
			return
		node = self.root
		# search for presence of the given key
		stack = []
		for k in key:
			stack.append((k, node))
			# if key item is not found, then key was not selected, no need for deselection
			if k not in node:
				return
			node = node[k]
			# if a terminal node is encountered earlier than expected, it is removed anyway
			if node is None:
				break
		for k, node in reversed(stack):
			# remove selection key
			node.pop(k, None)
			# if node has other selection, keep it
			if node:
				break
				
	def clear(self):
		self.root.clear()
	
	def isabove(self, key):
		if not key:
			return False
		node = self.root
		for k in key:
			# if any key item is missing, then key is considered not in the selection
			if k not in node:
				return False
			node = node[k]
			if node is None:
				return True
		return False
		
	def contains(self, key):
		if not key:
			return False
		node = self.root
		for k in key:
			if node.get(k) is None:
				return False
			node = node[k]
		return node is None
		
	def isbelow(self, key):
		if not key:
			return False
		node = self.root
		for k in key:
			if node.get(k) is None:
				return False
			node = node[k]
		return True

	def __repr__(self):
		return '{}({})'.format(type(self).__name__, self.root)

class Grid(madcad.displays.GridDisplay):
	''' display for the scene metric grid '''
	def __init__(self, scene, **kwargs):
		super().__init__(scene, fvec3(0), **kwargs)
	
	def stack(self, scene):
		if scene.options['display_grid']:	return super().stack(scene)
		else: 								return ()
	
	def render(self, view):
		self.center = view.navigation.center
		super().render(view)


class DownsampleIdent(madcad.rendering.Display):
	''' simple display used to downsample the ident map to the screen size '''
	def __init__(self, scene):
		self.va = scene.resource('downsample_ident', self.load)
		
	def load(self, scene):
		shader = scene.ctx.program(
			vertex_shader = self.vertex_shader,
			fragment_shader = self.fragment_shader,
			)
		vertices = scene.ctx.buffer(np.array([(0,0), (0,1), (1,1), (0,0), (1,1), (1,0)], 'f4'))
		return scene.ctx.vertex_array(shader, [(vertices, '2f', 'v_position')], mode=mgl.TRIANGLES)
	
	def render(self, view):
		view.scene.ctx.disable(mgl.DEPTH_TEST)
		view.tx_ident.use(0)
		view.tx_depth.use(1)
		self.va.program['ident'] = 0
		self.va.program['depth'] = 1
		self.va.program['width'] = 1/vec2(view.tx_ident.size)
		self.va.render()
				
	vertex_shader = '''
		#version 330

		in vec2 v_position;
		out vec2 position;
		
		void main() {
			position = v_position;
			gl_Position = vec4(2*v_position - 1, 0, 1);
		}
		'''
		
	fragment_shader = '''
		#version 330

		uniform usampler2D ident;
		uniform sampler2D depth;
		uniform vec2 width;
		in vec2 position;
		out uint ident_pool;

		const int kernel = 2;
		
		void main() {
			float depth_pool = 1.;
			ident_pool = uint(0);
			for (int x=0; x<kernel; x++) {
				for (int y=0; y<kernel; y++) {
					vec2 pixel = position + (vec2(x, y)+0.5)*width;
					float depth_sample = texture(depth, pixel).r;
					uint ident_sample = texture(ident, pixel).r;
					if (depth_sample < depth_pool) {
						depth_pool = depth_sample;
						ident_pool = ident_sample;
					}
				}
			}
			gl_FragDepth = depth_pool;
		}
		'''

def beginwith(sequence, pattern):
	if len(pattern) > len(sequence):
		return False
	for i in range(len(pattern)):
		if pattern[i] != sequence[i]:
			return False
	return True
		
class Highlight(madcad.rendering.Display):
	def __init__(self, scene):
		self.va = scene.resource('highlight', self.load)
		self.highlights = []
		
	def load(self, scene):
		shader = scene.ctx.program(
			vertex_shader = self.vertex_shader,
			fragment_shader = self.fragment_shader,
			)
		vertices = scene.ctx.buffer(np.array([(0,0), (0,1), (1,1), (0,0), (1,1), (1,0)], 'f4'))
		return scene.ctx.vertex_array(shader, [(vertices, '2f', 'v_position')], mode=mgl.TRIANGLES)
		
	def stack(self, scene):
		return ((), 'screen', 3, self.render),
		
	def render(self, view):
		view.scene.ctx.disable(mgl.DEPTH_TEST)
		view.tx_ident.use(0)
		self.va.program['idents'] = 0
		self.va.program['width'] = 1/vec2(view.fb_screen.size)
		stack = view.scene.stacks.get('ident')
		if not stack:
			return
		
		ranges = []
		start = 0
		stop = 0
		current = 0
		for item, step in zip(stack, view.steps):
			key = item[0]
			if view.scene.selection.isabove(key):
				highlight = 1
			elif view.hover and beginwith(key, view.hover):
				highlight = 2
			else:
				highlight = 0
			if current != highlight:
				if current:
					ranges.append((start, stop, current))
				start = stop+1
				current = highlight
			stop = step
		if current:
			ranges.append((start, stop, current))
		
		for start, stop, highlight in ranges:
			if highlight == 1:
				self.va.program['highlight'] = fvec4(madcad.settings.display['select_color_line'], 1)
			elif highlight == 2:
				self.va.program['highlight'] = fvec4(0, 0.7, 1, 0.7)
			else:
				continue
			self.va.program['interval'] = vec2(start, stop)
			self.va.render()
			
				
	vertex_shader = '''
		#version 330

		in vec2 v_position;
		out vec2 position;
		
		void main() {
			position = v_position;
			gl_Position = vec4(2*v_position - 1, 0, 1);
		}
		'''
		
	fragment_shader = '''
		#version 330

		uniform usampler2D idents;
		uniform vec4 highlight;
		uniform vec2 interval;
		uniform vec2 width;
		in vec2 position;
		out vec4 color;

		// the kernel points are repeated at serveral scale to mutlisample and antialias the outline
		const int samples_size = 2;
		const float samples[samples_size] = float[](1, 0.5);
		
		// the kernel set comparison points to check whether position is on an outline
		const int kernel_size = 4;
		const vec2 kernel[kernel_size] = vec2[](
			vec2(-1,0), vec2(+1,0),
			vec2(0,-1), vec2(0,+1)
		);

		void main() {
			float middle = texture(idents, position).r;
			float border = 0;
			int inside = int(interval.x <= middle) & int(middle <= interval.y);
			for (int i=0; i<kernel_size; i++) {
				float sum = 0.;
				for (int j=0; j<samples_size; j++) {
					vec2 neighboor = position + kernel[i]*samples[j]*width;
					if (neighboor.x < 0 || neighboor.y < 0 || neighboor.x > 1 || neighboor.y > 1)
						continue;
					float aside = texture(idents, neighboor).r;
					sum += inside ^ (int(interval.x <= aside) & int(aside <= interval.y));
				}
				border = max(border, sum/samples_size);
			}
			float intensity = border + 0.05 * inside;
			
			color = vec4(highlight.rgb, highlight.a * intensity);
		}
		'''
