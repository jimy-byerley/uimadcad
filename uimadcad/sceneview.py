from __future__ import annotations
from functools import partial
from operator import itemgetter

import numpy as np
import moderngl as mgl
from pnprint import nprint

from madcad.qt import (
	Qt, QObject, QEvent, 
	QPoint, QMargins, QFont, 
	QWidget, QPushButton, QCheckBox, QComboBox, QLabel, QSizePolicy, QButtonGroup, QActionGroup,
	QTextCursor,
	QGroupBox,
	)

import madcad
import madcad.scheme
from madcad.rendering.d3 import Perspective, Orthographic, Turntable, Orbit
from madcad.mesh import Mesh, Web, Wire
from madcad.mathutils import *
from . import settings
from .utils import *

empty = ()


class Scene(madcad.rendering.Scene, QObject):
	def __init__(self, app, context=None, options=None):
		# active selection path
		self.active_selection = None
		self.active_path = None
		# systematic scene additions
		self.additions = {		
			'__grid__': madcad.rendering.Displayable(Grid),
			'__base__': madcad.rendering.Displayable(Base),
			}
		# application behavior
		self.composer = SceneComposer(self)
		
		# for optimization purpose
		if options is None:
			options = {}
		options.update(
			track_source = True,
			display_grid = True,
			display_base = False,
			)
		# data graph setup
		QObject.__init__(self)
		madcad.rendering.Scene.__init__(self, context=context, options=options)
		self.app = app
		self.app.scenes.append(self)
		self.root = Root(self, world=fmat4())
		
		self.sync()
	
	def sync(self):
		''' synchronize the scene content with the rest of the application '''
		name = self.app.active.scope
		scope = self.app.interpreter.scopes.get(name)
		usage = self.app.interpreter.usages.get(name)
		
		if scope is None:
			return
		
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
		# with scene composition
		for key in keys:
			if key.startswith('_madcad_'):
				continue
			obj = scope.get(key, None)
			if self.displayable(obj):
				new[key] = obj
		# with script selection
		if self.app.active.scriptview:
			for selected in self.app.active.scriptview.selection:
				scope = self.app.interpreter.scopes.get(selected.scope)
				if not scope:
					continue
				obj = scope.get(selected.name)
				if not obj:
					continue
				if selected.scope == self.app.interpreter.filename:
					new[selected.name] = obj
				else:
					if selected.scope not in new:
						new[selected.scope] = {}
					new[selected.scope][selected.name] = obj
		# with decoration elements
		new.update(self.additions)
		
		super().update(new)
		
	def prepare(self):
		super().prepare()
		# if scene is no more empty, adjust the view automatically
		for view in self.app.views:
			if isinstance(view, SceneView) and view.scene is self:
				view._populated_adjust()
	
	def selection_add(self, display, sub=None):
		super().selection_add(display, sub)
		if display.selected:
			if sub is None:
				self.active_path = display.key
				self.active_selection = display
			else:
				self.active_path = (*display.key, sub)
				self.active_selection = display
				
	def selection_remove(self, display, sub=None):
		super().selection_remove(display, sub)
		if not display.selected:
			self.active_selection = next(iter(self.selection), None)
			if self.active_selection:
				self.active_path = self.active_selection.key
	
	def selection_clear(self):
		super().selection_clear()
		self.active_selection = None
		self.active_path = None
	
	def selection_box(self):
		''' return the bounding box of the selection '''
		return boundingbox(disp.box.transform(disp.world)  for disp in self.selection)

	def format_key(self, key:tuple):
		text = []
		for k in key:
			if isinstance(k, str):
				if text:
					text.append('.')
				text.append(k)
			else:
				text.append('[')
				text.append(repr(k))
				text.append(']')
		return ''.join(text)

	def sources(self, display) -> Iterator[Located]:
		''' yield the source code of successive containg displays '''
		if not display.key:
			return
		node = self.root
		stack = []
		try:
			for k in display.key:
				node = node[k]
				stack.append(node)
		# display.key is outdated
		except KeyError:
			return
		for node in reversed(stack):
			located = self.source(node)
			if located is not None:
				yield located
	
	def source(self, display) -> Located|None:
		''' return the source code of the given display, or None if not available '''
		return self.app.interpreter.identified.get(id(getattr(display, 'source', None)))

	
class Root(madcad.rendering.Group):
	''' override for the scene root display, hiding annotations when the user sets '''
	def stack(self, scene):
		for step in super().stack(scene):
			if not isinstance(step, madcad.rendering.Step):
				step = madcad.rendering.Step(*step)
			if step.display.key[0] == 'annotations':
				continue
			yield step


class SceneView(madcad.rendering.QView3D):
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
		Initializer.process(self)
		self._init_scene_settings()
		
		# toolbars
		self.top = ToolBar('scene', [
			self.new_view,
			self.open_composer,
			spacer(5, 0),
			self.select_parent,
			self.select_child,
			self.seek_selection,
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
			self.display_base,
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
			None,
			self.selection_multiple,
			self.selection_sub,
			# None,
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
		self._populated_adjust()
		
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
		if evt.type() == QEvent.PaletteChange and madcad.settings.display['system_theme']:
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
		# reimplement top bar shortcuts here because Qt cannot deambiguate which view the shortcut belongs to
		if event.type() == QEvent.KeyPress:
			if event.key() == Qt.Key_Return and event.modifiers() & Qt.AltModifier:
				event.accept()
				self.open_composer.setChecked(True)
			elif event.key() == Qt.Key_Up and event.modifiers() & Qt.AltModifier:
				event.accept()
				self.seek_selection.click()
		# implement mouse shortcuts here since they cannot be defined using other Qt means
		elif event.type() == QEvent.Type.MouseButtonRelease:
			if event.button() == Qt.MouseButton.BackButton:
				event.accept()
				self.select_parent.trigger()
			elif event.button() == Qt.MouseButton.ForwardButton:
				event.accept()
				self.select_child.trigger()
		
		if not event.isAccepted():
			event.ignore()
			super().inputEvent(event)
			
			if event.type() == QEvent.MouseButtonRelease:
				self._update_active_selection()
	
	def _populated_adjust(self):
		''' if scene is no more empty, adjust the view automatically '''
		box = self.scene.root.box
		empty = box.isempty()
		if self._last_empty and not empty:
			self.center(box.center)
			self.adjust(box)
		self._last_empty = empty
	
	def _update_active_scene(self):
		self.open_composer.setText('scene:{}'.format(self.app.scenes.index(self.scene)))
		self.update()
	
	def _update_active_selection(self):
		if self.scene.active_selection:
			selection = self.scene.active_selection
			text = self.scene.format_key(selection.key)
			# special case for subitem
			if isinstance(selection.selected, set) and None not in selection.selected:
				text += '.group({})'.format(next(iter(selection.selected)))
		
			font = QFont(*settings.scriptview['font'])
			pointsize = font.pointSize()
			self.seek_selection.setFont(font)
			self.seek_selection.setText(text)
			self.seek_selection.setEnabled(True)
			self.seek_selection.show()
		else:
			self.seek_selection.setEnabled(False)
			self.seek_selection.setFont(QFont())
			self.seek_selection.setText('seek selection')
			self.seek_selection.hide()
		if self.app.active.scriptview:
			self.app.active.scriptview.sync()
	
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
			self.setFocus()
			self.scene.composer.setVisible(False)
	
	@button(flat=True) #, shortcut='Alt+Up')
	def seek_selection(self):
		''' last selection, click to scroll to it 
		
			(shortcut: Alt+Up)
		'''
		if self.scene.active_selection and self.app.active.scriptview:
			for located in self.scene.sources(self.scene.active_selection):
				self.app.active.scriptview.seek_position(range(
					self.app.reindex.upgrade(located.range.start),
					self.app.reindex.upgrade(located.range.stop-1)+1,
					))
				self.app.active.scriptview.setFocus()
				break
	
	@action(icon='view-fullscreen', shortcut='C')
	def view_adjust(self):
		''' center and zoom to displayed objects '''
		box = self.scene.selection_box() or self.scene.root.box
		self.center(box.center)
		self.adjust(box)
	
	@action(icon='madcad-view-normal', shortcut='N')
	def view_normal(self):
		''' move the view orthogonal to the selected surface '''
		if not self.scene.active:	return
		disp = self.scene.active
		if not disp or not disp.source:	return
		source = disp.source
		world = disp.world
		
		if not isinstance(source, (Mesh,Web,Wire)) and hasattr(source, 'mesh'):
			source = source.mesh()
		
		if isinstance(source, (Mesh,Web,Wire)):
			sub = next(iter(disp.selected), None)
			if sub is not None:
				mesh = source.group(sub)
			else:
				mesh = source
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
			
			self.navigation.sight(normal)
			self.update()
	
	@action(icon='madcad-projection', shortcut='Shift+X')
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
	
	@action(icon='go-next', shortcut='Alt+Right')
	def select_child(self):
		''' select the parent object of the active selection
			active selection is the last object you clicked 
		'''
		active = self.scene.active_path
		if not active:
			return
		parent, child = None, self.scene.root
		sub = None
		for rank, key in enumerate(active):
			if isinstance(child.selected, set):
				sub = key
				break
			parent, child = child, child[key]
			if parent.selected:
				break
		self.scene.selection_remove(parent)
		self.scene.selection_add(child, sub)
		self.scene.active_path = active
		self._update_active_selection()
		self.update()
	
	@action(icon='go-previous', shortcut='Alt+Left')
	def select_parent(self):
		''' select the child object of the active selection
			which child it takes depends on what you clicked to select it
		'''
		active = self.scene.active_path
		if not active:
			return
		parent, child = None, self.scene.root
		for rank, key in enumerate(active):
			if isinstance(child.selected, set):
				parent = child
				break
			parent, child = child, child[key]
			if isinstance(child.selected, set):
				if None in child.selected:
					break
			else:
				if child.selected:
					break
		self.scene.selection_remove(child)
		self.scene.selection_add(parent)
		self.scene.active_path = active
		self._update_active_selection()
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
			
		display_base = dict( 
			icon='madcad-base',
			description='display base vectors and origin',
			shortcut='Shift+V'),
		
		solid_freemove = dict(
			icon='madcad-solid',
			description='move solids freely in the view',
			shortcut='F'),
		
		selection_multiple = dict(
			icon='madcad-selection-multiple',
			description='''
				enable multiple selection
				
				- exclusive selection (selecting an object clear any previoous selection)
				- multiple selection (selection an object adds it to the selection
				
				click the background to deselect all
				''',
			shortcut='Shift'),
		
		selection_sub = dict(
			icon='madcad-selection-sub',
			description='''
				enable subitem selection
				
				- objects subitem when it exists (like groups in meshes)
				- object as a whole (the complete variable)
				''',
			shortcut='Shift+S'),
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
		self.view.scene.composer.setFocus()
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

	@button(icon='list-add', flat=True)
	def scene_add(self):
		''' create a new scene '''
		former = self.view.scene
		self.view.scene = Scene(self.scene.app, 
			context = former.context, 
			options = former.options,
			)
		self._update_active_scene()
		
	@button(icon='list-remove', flat=True)
	def scene_remove(self):
		''' delete this scene '''
		self.view.app.scenes.pop(self.view.app.scenes.index(self.scene))
		if self.view.app.scenes:
			self.view.scene = self.view.app.scenes[0]
			self._update_active_scene()
		else:
			self.scene_add.trigger()

class Grid(madcad.rendering.d3.marker.GridDisplay):
	''' display for the scene metric grid '''
	def __init__(self, scene):
		super().__init__(scene, fvec3(0))
	
	def stack(self, scene):
		if scene.options['display_grid']:	return super().stack(scene)
		else: 								return ()
	
	def render(self, view):
		self.center = view.navigation.center
		super().render(view)

class Base(madcad.scheme.Scheme.display):
	''' display for the scene base of vectors '''
	def __init__(self, scene):
		super().__init__(scene, madcad.scheme.note_base(mat4()))
	
	def stack(self, scene):
		if scene.options['display_base']:
			for step in super().stack(scene):
				if isinstance(step, tuple):
					step = madcad.rendering.Step(*step)
				if step.target != 'ident':
					yield step
		else:
			return ()

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
