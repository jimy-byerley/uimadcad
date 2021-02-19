from PyQt5.QtCore import Qt, QEvent
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QSizePolicy, QShortcut,
							QLabel, QPushButton, QAction, 
							QDockWidget, QFileDialog, QInputDialog
							)
from PyQt5.QtGui import QIcon, QKeySequence, QTextCursor, QTextDocument

import os.path
import ast
from collections import namedtuple
from nprint import nformat

from madcad import *

from .interpreter import astatpos
from .sceneview import scene_unroll


class ToolError(Exception):
	''' exception used to indicate an error in the usage of a Scene tool '''
	pass

class ToolAssist(QWidget):
	''' assistant widget (or window) that pop up when a tool is enabled '''
	def __init__(self, main, parent=None):
		super().__init__(parent)
		self.main = main
		self.visible = False
		self._tool = QLabel()
		self._info = QLabel()
		
		# configure labels
		self._info.setSizePolicy(QSizePolicy(QSizePolicy.Fixed, QSizePolicy.Minimum))
		self._tool.setSizePolicy(QSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed))
		f = self._tool.font()
		f.setPointSize(int(f.pointSize()*1.2))
		self._tool.setFont(f)
		# cancel shortcut (already present in the menubar)
		#self.shortcut = QShortcut(QKeySequence('Escape'), self, 
							#member=self.cancel, 
							#ambiguousMember=self.cancel)
		#self.addAction(self.shortcut)
		# cancel button
		cancel = QPushButton('cancel')
		cancel.clicked.connect(self.main.cancel_tool)
		
		# ui layout
		layout = QVBoxLayout()
		layout.addWidget(self._tool)
		layout.addWidget(self._info)
		layout.addWidget(cancel)
		self.setLayout(layout)
		self.tool(None)
	
	def tool(self, name):
		''' set the current tool name, if set to None or an empty name, the assistant will be hidden '''
		if name:	
			self._tool.setText('<b>{}</b>'.format(name))
			self.visible = True
		else:		
			self._info.setText('no active tool')
			self.visible = False
		self.update_visibility()
	def info(self, text):
		''' set the info text about the current state of the tool procedure '''
		if text and not text.startswith('•'):	text = '• '+text
		self._info.setText(text)
	
	def update_visibility(self):
		''' update the widget visibility (or its dock's if it's docked) '''
		if self.visible:
			if isinstance(self.parent(), QDockWidget):
				self.parent().setVisible(True)
			else:
				self.setVisible(True)
		else:
			if isinstance(self.parent(), QDockWidget):
				self.parent().setVisible(False)
			else:
				self.setVisible(False)
	def changeEvent(self, evt):
		super().changeEvent(evt)
		self.update_visibility()
		
		
class Modification(object):
	''' proxy for modification to QTextDocument '''
	__slots__ = 'changes', 'conflict'
	def __init__(self, conflict=False):
		self.changes = []			# sorted list of couples ((start,end), text)
		self.conflict = conflict
	
	def commit(self, document):
		if isinstance(document, QTextDocument):
			document = QTextCursor(document)
		if isinstance(document, QTextCursor):
			document.beginEditBlock()
			for start,stop,change in reversed(self.changes):
				document.setPosition(start)
				document.setPosition(stop, QTextCursor.KeepAnchor)
				document.insertText(change)
			document.endEditBlock()
		elif isinstance(document, str):
			mod = ''
			last = 0
			for start,stop,change in self.changes:
				mod += document[last:start] + change
				last = stop
			return mod
		else:
			raise TypeError('commit expect a str, QTextCursor or QTextDocument')
	
	def clear(self):
		self.changes.clear()
	
	def __setitem__(self, index, text):
		if isinstance(index, int):	
			start,stop = index,index
		elif isinstance(index, slice):
			start,stop = index.start, index.stop
			if index.step and index.step != 1:
				raise ValueError('only slices with step 1 are supported')
		
		l = len(self.changes)
		i = bisect(self.changes, start, lambda c: c[0])
		while i < l and self.changes[i][0] == start and self.changes[i][1] == start:
			i += 1
			
		if not self.conflict and i < l and stop > self.changes[i][1]:
			raise IndexError('{} conflict with previous modification {}'.format((start,stop), self.changes[i][:2]))
		self.changes.insert(i, (start,stop,text)) 
		
	def __iadd__(self, other):
		if not isinstance(other, Modification):
			return NotImplemented
		for start,stop,block in other.changes:	# NOTE this loop should be replaced by a dual merge for better efficiency
			self[start:stop] = block
		return self


class Var(object):
	__slots__ = 'value', 'name'
	def __init__(self, value=None, name=None):
		self.value, self.name = value, name
	
def dispvar(main, disp):
	if hasattr(disp, 'source') and disp.source:
		name = main.interpreter.ids.get(id(disp.source))
		if name:
			return Var(disp.source, name)
		
def clickedvar(main, evt):
	view = main.active_sceneview
	pos = view.somenear(evt.pos())
	if pos:
		disp = view.scene.item(view.itemat(pos))
		return dispvar(main, disp)
	

def islive(main, name):
	''' return True if the variable using this name is in a text area that 
		has never been modified since the last execution.
		The AST informations and positions are then correct
	'''
	if name in main.interpreter.locations:
		node = main.interpreter.locations[name]
		return main.interpreter.ast_end >= node.end_position
	return False

def istemp(main, name):
	''' return whether a variable name belongs to a temporary object (an expression) or has been assigned '''
	node = main.interpreter.locations[name]
	return not isinstance(node, ast.Assign)

def acquirevar(main, var):
	''' create proper variables for temp objects reused '''
	if istemp(main, var.name):
		# check that the used objects dont rely on an object that is in the modified area of the script
		if not islive(main, var.name):
			raise ToolError('cannot use variable {} moved in the script'.format(repr(grp)))
		newname = autoname(main, var.value)
		rename(main, var.name, newname)
		return Var(var.value, newname)
	return var

def rename(main, oldname, newname=None):
	''' rename the object
		if the object is a temporary value, its expression is moved into a new assignation statement
		if the object is an existing variable, simply change the name the value is assigned to
	'''
	if not islive(main, oldname):
		raise ToolError('cannot rename variable {} in a modified area'.format(repr(oldname)))
	if not newname:
		newname = QInputDialog.getText(main.mainwindow, 'choose variable name', 'new name:')[0]
	if not newname:
		raise ToolError('no new name entered')
	
	node = main.interpreter.locations[oldname]
	# the renamed object already has a variable name
	if isinstance(node, ast.Assign):
		zone = node.targets[0]
		main.mod[zone.position:zone.end_position] = newname
	
	# the renamed object is a temporary variable
	else:
		stmt = main.interpreter.ast.body[astatpos(main.interpreter.ast, node.position)]
		
		# the expression result is not used, just assign it
		if isinstance(stmt, ast.Expr) and stmt.position == node.position and stmt.end_position == node.end_position:
			# just insert the assignation
			main.mod[node.position] = '{} = '.format(newname)
		# the expression result is used, move it and assign it
		else:
			# get and remove the expression
			cursor = QTextCursor(main.script)
			cursor.setPosition(node.position)
			cursor.setPosition(node.end_position, QTextCursor.KeepAnchor)
			expr = cursor.selectedText()
			main.mod[node.position:node.end_position] = newname
			# insert expression with assignation
			main.mod[stmt.position] = '{} = {}\n'.format(newname, expr)
	main.interpreter.current[newname] = main.interpreter.current.get(oldname)
			
def autoname(main, obj):
	''' suggest an unused name for the given object '''
	if isinstance(obj, vec3):		basename = 'P'
	elif isprimitive(obj):			basename = 'L'
	elif isinstance(obj, Mesh):		basename = 'M'
	elif isinstance(obj, Web):		basename = 'W'
	elif isinstance(obj, Wire):		basename = 'C'
	elif isinstance(obj, Solid):	basename = 'M'
	else:							basename = 'O'
	i = 0
	while True:
		name = basename+str(i)
		if name not in main.interpreter.current:	return name
		i += 1
	
	
def dump(o):
	''' dump object into script '''
	if isinstance(o, Var):
		if o.name:	return o.name
		else:		o = o.value
	if isinstance(o, vec3):
		return 'vec3({:.4g},\t{:.4g},\t{:.4g})'.format(*o)
	elif isinstance(o, tuple):
		return '(' + ',\t'.join(dump(e) for e in o) + ')'
	else:
		return repr(o)
		
def format(pattern, *args, **kwargs):
	''' format the given string using dump() instead of str()
		also applies nformat to split long resulting script
	'''
	return nformat(pattern.format(
				*[dump(o) for o in args], 
				**{k:dump(o) for k,o in kwargs.items()},
				),
				width=40)
		

def toolrequest(main, args, create=True):
	match = [None] * len(args)	# matched objects
	env = main.interpreter.current
	
	# search the selection for the required objects
	for disp in scene_unroll(main.active_sceneview.scene):
		if disp.selected:
			var = dispvar(main, disp)
			if var:
				for i,(req,comment) in enumerate(args):
					if not match[i] and satisfy(var.value, req):
						match[i] = var
						break
	
	for i,var in enumerate(match):
		if var:
			match[i] = acquirevar(main, var)
	
	# create successive missing objects (if they are sufficiently simple objects)
	for i,(req,comment) in enumerate(args):
		if match[i]:	continue
		
		main.assist.info(comment)
		if req not in completition or not create:
			raise ToolError('missing {}'.format(comment))
	
		# run a selection in concurrence with the creation
		def select(main):
			while True:
				evt = yield from waitclick()
				view = main.active_sceneview
				pos = view.somenear(evt.pos())
				if not pos:	
					continue
				disp = view.scene.item(view.itemat(pos))
				var = dispvar(main, disp)
				if not var or not satisfy(var.value, req):
					continue
				disp.selected = True
				# create proper variables for temp objects reused
				return acquirevar(main, var)

		# get the first returned value from the selector or the creation
		iterator = race(select(main), completition[req](main))
		next(iterator)
		match[i] = yield from iterator
	
	main.deselectall()
	return match



def race(*args):
	if len(args) == 1 and hasattr(args[0], '__iter__'):
		args = args[0]
	while True:
		obj = yield
		for it in args:
			try:
				res = it.send(obj)
			except StopIteration as err:
				return err.value

def satisfy(obj, req):
	''' return True if obj satisfy the requirement req (type or funcion) '''
	if isinstance(req, type):	return isinstance(obj, req)
	elif callable(req):			return req(obj)
	else:						return False

		
	
def createpoint(main):
	evt = yield from waitclick()
	view = main.active_sceneview
	p = view.ptfrom(evt.pos(), view.navigation.center)
	solid = view.scene.active_solid
	if solid:
		p = vec3(mat4(affineInverse(solid.world * solid.pose)) * vec4(p,1))
	main.addtemp(p)
	view.scene.add(p)
	view.update()
	return Var(p)
	
def waitclick():
	evt = yield
	while evt.type() != QEvent.MouseButtonRelease or evt.button() != Qt.LeftButton:
		evt = yield
	return evt

def createaxis(main):
	evt = yield from waitclick()
	view = main.active_sceneview
	p0 = view.ptfrom(evt.pos(), view.navigation.center)
	first = evt.pos()
	evt = yield from waitclick()
	if view == main.active_sceneview and (first-evt.pos()).manhattanLength() < 20:
		axis = (p0, vec3(fvec3(view.navigation.matrix()[2])))
	else:
		p1 = main.active_sceneview.ptfrom(evt.pos(), view.navigation.center)
		axis = (p0, normalize(p1-p0))
	view.scene.add(axis)
	view.update()
	return Var(axis)



def create_toolbars(main, widget):
	tools = widget.addToolBar('creation')
	tools.setObjectName('toolbar-creation')
	tools.addAction(main.createaction('import', tool_import, 	'madcad-import'))
	tools.addAction(main.createaction('solid', tool_solid, 'madcad-solid'))
	tools.addAction(main.createaction('manual triangulated meshing', tool_meshing, 'madcad-meshing'))
	tools.addAction(QIcon.fromTheme('madcad-splined'), 'manual splined meshing')
	tools.addAction(main.createtool('point', tool_point,		'madcad-point'))
	tools.addAction(main.createtool('axis', tool_axis,		'madcad-axis'))
	tools.addAction(main.createtool('segment', tool_segment,	'madcad-segment'))
	tools.addAction(main.createtool('arc', tool_arcthrough,		'madcad-arc'))
	tools.addAction(QIcon.fromTheme('madcad-spline'), 'spline')
	
	tools = widget.addToolBar('annotation')
	tools.setObjectName('toolbar-annotation')
	tools.addAction(main.createtool('annotation', tool_note, 'madcad-annotation'))
	tools.addAction(QIcon.fromTheme('madcad-cst-distance'), 'distance measure')
	tools.addAction(QIcon.fromTheme('insert-text'), 'floating text')
	tools.addAction(QIcon.fromTheme('insert-image'), 'image')
	
	tools = widget.addToolBar('mesh')
	tools.setObjectName('toolbar-mesh')
	tools.addAction(main.createtool('boolean', tool_boolean, 'madcad-boolean'))
	tools.addAction(QIcon.fromTheme('madcad-chamfer'), 'chamfer')
	
	tools = widget.addToolBar('web')
	tools.setObjectName('toolbar-web')
	tools.addAction(main.createtool('extrusion', tool_extrusion, 'madcad-extrusion'))
	tools.addAction(QIcon.fromTheme('madcad-revolution'), 'revolution')
	tools.addAction(QIcon.fromTheme('madcad-tube'), 'tube')
	tools.addAction(QIcon.fromTheme('madcad-saddle'), 'saddle')
	tools.addAction(QIcon.fromTheme('madcad-triangulation'), 'surface')
	tools.addAction(QIcon.fromTheme('madcad-junction'), 'junction')
	
	tools = widget.addToolBar('amelioration')
	tools.setObjectName('toolbar-ameliration')
	tools.addAction(main.createtool('merge closes', tool_mergeclose, 'madcad-mergeclose'))
	tools.addAction(main.createtool('strip buffers', tool_stripbuffers, 'madcad-stripbuffer'))
	tools.addAction(QIcon.fromTheme('madcad-flip'), 'flip orientation')
	
	tools = widget.addToolBar('constraints')
	tools.setObjectName('toolbar-constraints')
	# primitive constraints
	tools.addAction(main.createtool('hold distance', tool_distance, 'madcad-cst-distance'))
	tools.addAction(main.createtool('hold radius', tool_radius, 'madcad-cst-radius'))
	tools.addAction(main.createtool('hold angle', tool_angle, 'madcad-cst-angle'))
	tools.addAction(QIcon.fromTheme('madcad-cst-tangent'), 'make tangent')
	tools.addAction(QIcon.fromTheme('madcad-cst-onplane'), 'hold on plane')
	tools.addAction(QIcon.fromTheme('madcad-cst-projection'), 'hold projection')
	# kinematic constraints
	tools.addAction(main.createtool('ball', tool_ball, 'madcad-cst-ball'))
	tools.addAction(main.createtool('plane', tool_plane, 'madcad-cst-plane'))
	tools.addAction(main.createtool('pivot', tool_pivot, 'madcad-cst-pivot'))
	tools.addAction(main.createtool('gliding', tool_gliding, 'madcad-cst-gliding'))
	tools.addAction(main.createtool('track', tool_track, 'madcad-cst-track'))
	#tools.addAction(main.createtool('linear annular', tool_annular, 'madcad-cst-annular'))
	tools.addAction(QIcon.fromTheme('madcad-cst-annular'), 'linear annular')
	tools.addAction(main.createtool('punctiform', tool_punctiform, 'madcad-cst-punctiform'))
	tools.addAction(main.createtool('helicoid', tool_helicoid, 'madcad-cst-helicoid'))
	#tools.addAction(main.createtool('gear', tool_gear, 'madcad-cst-gear'))
	tools.addAction(QIcon.fromTheme('madcad-cst-gear'), 'gear')
	



def act_rename(main):
	for disp in scene_unroll(main.active_sceneview.scene):
		if disp.selected:
			var = dispvar(main, disp)
			if var:
				rename(main, var.name)
				break

def tool_import(main):
	filename = QFileDialog.getOpenFileName(main.mainwindow, 'import file', 
						os.curdir, 
						'ply files (*.ply);;stl files (*.stl);;obj files (*.obj)',
						)[0]
	if not filename:
		raise ToolError('no file selected')
	objname = os.path.splitext(os.path.basename(filename))[0]
	if not objname.isidentifier():	objname = 'imported'
	main.insertstmt('{} = read({})'.format(objname, repr(filename)))
	
def tool_solid(main):
	main.insertexpr('Solid()')
	
def tool_meshing(main):
	main.insertexpr('Mesh(\n\tpoints=[],\n\tfaces=[])')

def tool_mergeclose(main):
	args = yield from toolrequest(main, [(Mesh, 'mesh to process')], create=False)
	main.insertstmt(args[0]+'.mergeclose()')
	
def tool_stripbuffers(main):
	args = yield from toolrequest(main, [(Mesh, 'mesh to process')], create=False)
	main.insertstmt(args[0]+'.finish()')

def tool_point(main):
	main.assist.tool('point')
	main.assist.info('click to place the point')
	p = yield from createpoint(main)
	main.insertexpr(dump(p))
	
def tool_axis(main):
	origin, dst = yield from toolrequest(main, [
				(vec3, 'origin point'),
				(vec3, 'direction point'),
			])
	dir = normalize(dst.value-origin.value)
	main.insertexpr(format('Axis({}, {})', origin, dir))
	
def tool_segment(main):
	args = yield from toolrequest(main, [
				(vec3, 'start point'),
				(vec3, 'end point'),
			])
	main.insertexpr(format('Segment({}, {})', *args))

def tool_arcthrough(main):
	args = yield from toolrequest(main, [
				(vec3, 'start point'), 
				(vec3, 'pass point'), 
				(vec3, 'end point'),
			])
	main.insertexpr(format('ArcThrough({}, {}, {})', *args))
	
def tool_note(main):
	while True:
		evt = yield from waitclick()
		view = main.active_sceneview
		pos = view.somenear(evt.pos())
		if not pos:		continue
		item = view.itemat(pos)
		disp = view.scene.item(item)
		var = dispvar(main, disp)
		if var:	break
	
	acquirevar(main, var)
		
	def asktext():
		return QInputDialog.getText(main.mainwindow, 'text note', 'enter text:')[0]
		
	if isinstance(var.value, (Mesh,Web,Wire)):
		expr = format('note_leading({}.group({}), text={})', var, item[-1], asktext())
	elif isinstance(var.value, (Wire,vec3,Axis,tuple)):
		expr = format('note_leading({}, text={})', var, asktext())
	else:
		raise ToolError('unable to place a note on top of {}'.format(type(var.value)))
	main.insertexpr(expr)

def tool_boolean(main):
	args = yield from toolrequest(main, [
				(Mesh, 'first volume'),
				(Mesh, 'second volume'),
				])
	main.insertexpr(format('difference({}, {})', *args))
	#main.assist.ui(BooleanChoice(args))
"""
class BooleanChoice(QWidget):
	''' menu to select options for tool execution '''
	def __init__(self, meshes):
		self.meshes = meshes
		choice = QComboBox(self)
		choice.addItem('union')
		choice.addItem('difference')
		choice.addItem('intersection')
		choice.addItem('exclusion')
		choice.currentIndexChanged.connect(self.set)
		finishbt = QPushButton('finish')
		finishbt.activated.connect(self.finish)
		layout = QHBoxLayout()
		layout.addWidget(choice)
		layout.addWidget(finishbt)
		self.setLayout(layout)
	def set(self, mode):
		indev
	def finish(self):
		indev
"""

def tool_extrusion(main):
	outline, = yield from toolrequest(main, [
				(lambda o: isinstance(o, (Web,Wire,Mesh)), 'outline mesh'),
				])
	displt = QInputDialog.getText(main.mainwindow, 'extrusion displacement', 'vector expression:')[0]
	if not displt:
		raise ToolError('no displacement entered')
	main.insertexpr(format('extrusion({}, {})', Var(name=displt), outline))

def tool_revolution(main):
	outline, axis = yield from toolrequest(main, [
				(lambda o: isinstance(o, (Web,Wire,Mesh)), 'outline mesh'),
				(isaxis, 'revolution axis'),
				])
	angle = QInputDialog.getText(main.mainwindow, 'revolution angle', 'angle (degrees):')[0]
	if not angle:
		raise ToolError('no displacement entered')
	main.insertexpr(format('revolution(radians({}), {}, {})', Var(name=angle), axis, outline))
	
def tool_tube(main):
	args = yield from toolrequest(main, [
				(lambda o: isinstance(o, (Web,Wire,Mesh)), 'outline'),
				(lambda o: isinstance(o, (Web,Wire,Mesh)), 'path'),
				])
	main.insertexpr(format('tube({}, {})', *args))
	
def tool_saddle(main):
	args = yield from toolrequest(main, [
				(lambda o: isinstance(o, (Web,Wire,Mesh)), 'profile 1'),
				(lambda o: isinstance(o, (Web,Wire,Mesh)), 'profile 2'),
				])
	main.insertexpr(format('saddle({}, {})', *args))



def tool_distance(main):
	crit = lambda o: isinstance(o, vec3) or isaxis(o) or isinstance(o, Segment)
	args = yield from toolrequest(main, [
				(crit, 'start point'),
				(crit, 'end point'),
				])
	target = QInputDialog.getText(main.mainwindow, 'distance constraint', 'target distance:')[0]
	if not target:
		raise ToolError('no distance entered or invalid radius')
	main.insertexpr(format('Distance({}, {}, {})', *args, Var(name=target)))

def tool_radius(main):
	arc, = yield from toolrequest(main, [
				(lambda o: isinstance(o, (ArcThrough, ArcCentered, Circle)), 'arc'),
				])
	target = QInputDialog.getText(main.mainwindow, 'radius constraint', 'target radius:')[0]
	if not target:
		raise ToolError('no radius entered')
	main.insertexpr(format('Radius({}, {})', arc, Var(name=target)))

def tool_angle(main):
	args = yield from toolrequest(main, [
				(lambda o: hasattr(o, 'direction'), 'start segment'),
				(lambda o: hasattr(o, 'direction'), 'second segment'),
				])
	target = QInputDialog.getText(main.mainwindow, 'angle constraint', 'target oriented angle:')[0]
	if not target:
		raise ToolError('no angle entered')
	main.insertexpr(format('Angle({}, {}, radians({}))', *args, Var(name=target)))

def tool_tangent(main):
	args = yield from toolrequest(main, [
				(lambda o: hasattr(o, 'slv_tangent'), 'primitive 1'),
				(lambda o: hasattr(o, 'slv_tangent'), 'primitive 2'),
				])
	common = None
	for v1 in args[0].slvvars:
		for v2 in args[1].slvvars:
			if getattr(args[0], v1) is getattr(args[1], v2):
				common = v1, v2
	main.insertexpr(format('Tangent({}, {}, {}.{})', args[0], args[1], args[0], Var(name=common[0])))
				
			
def tool_planar(main):
	axis, = yield from toolrequest(main, [
				(isaxis, 'axis normal to the plane'),
				])
	
	# let the user select or create the points to put on the plane
	vars = []
	while True:
		evt = yield
		if evt.type() == QEvent.KeyPressed and evt.key() == Qt.Esc or evt.type() == QEvent.MouseButtonRelease and evt.button() == Qt.MiddleButton:
			break
		if not (evt.type() == QEvent.MouseButtonRelease and evt.button() == Qt.LeftButton):
			continue
		var = clickedvar(evt)
		if not var:	
			continue
		vars.append(acquirevar(var))
	
	main.insertexpr(format('Planar({}, [{}])', 
				axis, 
				', '.join(dump(obj) for obj in vars)),
				)


def tool_pivot(main):
	args = yield from toolrequest(main, [
				(isaxis, 'axis of the pivot'),
				])
	main.insertexpr(format('Pivot(Solid(), Solid(), {})', *args))

def tool_gliding(main):
	args = yield from toolrequest(main, [
				(isaxis, 'axis of the pivot'),
				])
	main.insertexpr(format('Gliding(Solid(), Solid(), {})', *args))
	
def tool_plane(main):
	args = yield from toolrequest(main, [
				(isaxis, 'normal axis to the plane'),
				])
	main.insertexpr(format('Plane(Solid(), Solid(), {})',  *args))
	
def tool_ball(main):
	args = yield from toolrequest(main, [
				(vec3, 'position of the ball'),
				])
	main.insertexpr(format('Ball(Solid(), Solid(), {})', *args))
	
def tool_punctiform(main):
	args = yield from toolrequest(main, [
				(isaxis, 'normal axis to the plane'),
				])
	main.insertexpr(format('Punctiform(Solid(), Solid(), {})', *args))
	
def tool_track(main):
	axis, = yield from toolrequest(main, [
				(isaxis, 'axis of the track'),
				])
	z = vec3(fvec3(main.active_sceneview.uniforms['view'][2]))
	main.insertexpr(format('Track(Solid(), Solid(), {})', (*axis.value, z)))
	
def tool_helicoid(main):
	axis, = yield from toolrequest(main, [
				(isaxis, 'axis of the helicoid'),
				])
	pitch = QInputDialog.getText(main.mainwindow, 'helicoid joint', 'screw pitch (mm/tr):')[0]
	if not pitch:
		raise ToolError('no pich entered')
	main.insertexpr(format('Helicoid(Solid(), Solid(), {}, {})', Var(name=pitch), axis))


# tools that will automatically used to create missing objects in request
completition = {
	vec3:	createpoint,
	Axis:	createaxis,
	isaxis:	createaxis,
	}


'''
Pour afficher une bouton avec menu déroulant:

QMenu *menu = new QMenu();
QAction *testAction = new QAction("test menu item", this);
menu->addAction(testAction);

QToolButton* toolButton = new QToolButton();
toolButton->setMenu(menu);
toolButton->setPopupMode(QToolButton::MenuButtonPopup);
toolBar->addWidget(toolButton);
'''

