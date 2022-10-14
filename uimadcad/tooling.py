from PyQt5.QtCore import Qt, QEvent
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QSizePolicy, QShortcut,
							QLabel, QPushButton, QAction, 
							QDockWidget, QFileDialog, QInputDialog
							)
from PyQt5.QtGui import QIcon, QKeySequence, QTextCursor, QTextDocument

import os.path
import ast
from collections import namedtuple
from madcad.nprint import nformat

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
		
	def __repr__(self):
		return '<Var {}: {}>'.format(
				repr(self.name) if self.name else'anonymous', 
				repr(self.value),
				)
	
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
			raise ToolError('cannot use variable {} moved in the script'.format(repr(var.name)))
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
		if o.name:	
			return o.name
		else:		
			o = o.value
			if isinstance(o, vec3):
				return 'vec3({:.4g}, {:.4g}, {:.4g})'.format(*o)
			elif isinstance(o, tuple):
				return '(' + ',\t'.join(dump(e) for e in o) + ')'
			elif isinstance(o, Mesh):
				args = [repr(mesh.points).replace('dvec3', 'vec3'), repr(mesh.faces)]
				if any(e	for e in mesh.groups):
					args.append(repr(mesh.tracks))
					args.append(repr(mesh.groups))
				return 'Mesh({})'.format(', '.join(args))
			else:
				return repr(o).replace('dvec3(', 'vec3(')
	else:
		return str(o)
		
def format(pattern, *args, **kwargs):
	''' format the given string using dump() instead of str()
		also applies nformat to split long resulting script
	'''
	return nformat(pattern.format(
				*[dump(o) for o in args], 
				**{k:dump(o) for k,o in kwargs.items()},
				),
				width=50)
		

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
		match[i] = yield from race(select(main, req), completition[req](main))
	
	main.deselectall()
	return match

def requestmany(main, req, description='', create=True):
	''' give as many of one element as requested '''
	vars = []
	# take all satisfying selected objects from the scene
	for disp in scene_unroll(main.active_sceneview.scene):
		if disp.selected:
			var = dispvar(main, disp)
			if var and req(var.value):
				vars.append(acquirevar(main, var))
	# if there is no such selection, generate an unlimited quantity
	if not vars and create and req in completition:
		main.assist.info(description)
		while True:	
			try:
				var = yield from race(select(main, vec3), completition[req](main))
			except ToolError:
				break
			vars.append(var)
	return vars

def race(*args):
	''' get the first returned value from the selector or the creation '''
	if len(args) == 1 and hasattr(args[0], '__iter__'):
		args = args[0]
	for it in args:	
		try:	
			next(it)
		except StopIteration as err:
			return err.value
	while True:
		obj = yield
		for it in args:
			try:
				it.send(obj)
			except StopIteration as err:
				return err.value

def satisfy(obj, req):
	''' return True if obj satisfy the requirement req (type or funcion) '''
	if isinstance(req, type):	return isinstance(obj, req)
	elif callable(req):			return req(obj)
	else:						return False

def select(main, req):
	''' return when an view item is selected '''
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
	
def createpoint(main):
	evt = yield from waitclick()
	view = main.active_sceneview
	if view.scene.options['display_faces']:
		p = view.ptat(evt.pos()) or view.ptfrom(evt.pos(), view.navigation.center)
	else:
		p = view.ptfrom(evt.pos(), view.navigation.center)
	solid = view.scene.active_solid  or view.scene.poses.get('return')
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
		axis = Axis(p0, vec3(fvec3(transpose(view.uniforms['view'])[2])))
	else:
		p1 = main.active_sceneview.ptfrom(evt.pos(), view.navigation.center)
		axis = Axis(p0, normalize(p1-p0))
	view.scene.add(axis)
	view.update()
	return Var(axis)



def create_toolbars(main, widget):
	tools = widget.addToolBar('io')
	tools.setObjectName('toolbar-io')
	tools.addAction(main.createaction('import', tool_import, 	'document-import'))
	tools.addAction(main.createtool('export', tool_export, 	'document-export'))
	
	tools = widget.addToolBar('creation')
	tools.setObjectName('toolbar-creation')
	tools.addAction(main.createaction('solid', tool_solid, 'madcad-solid'))
	#tools.addAction(main.createaction('manual triangulated meshing', tool_meshing, 'madcad-meshing'))
	#tools.addAction(QIcon.fromTheme('madcad-splined'), 'manual splined meshing')
	tools.addAction(main.createtool('point', tool_point,		'madcad-point'))
	tools.addAction(main.createtool('axis', tool_axis,		'madcad-axis'))
	tools.addAction(main.createtool('segment', tool_segment,	'madcad-segment'))
	tools.addAction(main.createtool('arc through', tool_arcthrough,		'madcad-arc'))
	tools.addAction(main.createtool('circle', tool_circle,		'madcad-circle'))
	tools.addAction(main.createtool('interpolated', tool_interpolated, 'madcad-spline-interpolated'))
	tools.addAction(main.createtool('softened', tool_softened,	'madcad-spline-softened'))
	tools.addAction(main.createtool('arc tangent', tool_arctangent,		'madcad-arctangent'))
	tools.addAction(main.createtool('tangent ellipsis', tool_tangentellipsis,	'madcad-tangentellipsis'))
	
	tools = widget.addToolBar('annotation')
	tools.setObjectName('toolbar-annotation')
	tools.addAction(main.createtool('annotation', tool_note, 'madcad-annotation'))
	tools.addAction(main.createtool('boundingbox', tool_bounds, 'madcad-boundingbox'))
	tools.addAction(QIcon.fromTheme('madcad-cst-distance'), 'distance measure +')
	tools.addAction(main.createtool('floating text', tool_text, 'insert-text'))
	tools.addAction(QIcon.fromTheme('insert-image'), 'image +')
	
	tools = widget.addToolBar('mesh')
	tools.setObjectName('toolbar-mesh')
	tools.addAction(main.createtool('boolean', tool_boolean, 'madcad-boolean'))
	tools.addAction(QIcon.fromTheme('madcad-chamfer'), 'chamfer')
	
	tools = widget.addToolBar('web')
	tools.setObjectName('toolbar-web')
	tools.addAction(main.createtool('extrusion', tool_extrusion, 'madcad-extrusion'))
	tools.addAction(main.createtool('revolution', tool_revolution, 'madcad-revolution'))
	tools.addAction(main.createtool('tube', tool_tube, 'madcad-tube'))
	tools.addAction(main.createtool('saddle', tool_saddle, 'madcad-saddle'))
	tools.addAction(main.createtool('surface', tool_triangulation, 'madcad-triangulation'))
	tools.addAction(main.createtool('junction', tool_junction, 'madcad-junction'))
	
	tools = widget.addToolBar('amelioration')
	tools.setObjectName('toolbar-ameliration')
	tools.addAction(main.createtool('merge closes', tool_mergeclose, 'madcad-mergeclose'))
	tools.addAction(main.createtool('strip buffers', tool_stripbuffers, 'madcad-stripbuffer'))
	tools.addAction(main.createtool('flip orientation', tool_flip, 'madcad-flip'))
	
	tools = widget.addToolBar('constraints')
	tools.setObjectName('toolbar-constraints')
	# primitive constraints
	tools.addAction(main.createtool('hold distance', tool_distance, 'madcad-cst-distance'))
	tools.addAction(main.createtool('hold radius', tool_radius, 'madcad-cst-radius'))
	tools.addAction(main.createtool('hold angle', tool_angle, 'madcad-cst-angle'))
	tools.addAction(main.createtool('make tangent', tool_tangent, 'madcad-cst-tangent'))
	tools.addAction(main.createtool('hold on plane', tool_onplane, 'madcad-cst-onplane'))
	tools.addAction(main.createtool('hold projection', tool_projected, 'madcad-cst-projection'))
	# kinematic constraints
	tools.addAction(main.createtool('ball', tool_ball, 'madcad-cst-ball'))
	tools.addAction(main.createtool('planar', tool_planar, 'madcad-cst-plane'))
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
	
def tool_export(main):
	args = yield from toolrequest(main, [(object, 'object to export')])
	
	filename = QFileDialog.getSaveFileName(main.mainwindow, 'export as', 
						os.curdir, 
						'ply files (*.ply);;stl files (*.stl);;obj files (*.obj);;pickle files (*.pickle)',
						)[0]
	if not filename:
		raise ToolError('no file selected')
	
	main.insertstmt(format('io.write({}, {})', args[0], repr(filename)))
	
def tool_solid(main):
	main.insertexpr('Solid()')
	
def tool_meshing(main):
	main.insertexpr('Mesh(\n\tpoints=[],\n\tfaces=[])')

def tool_mergeclose(main):
	args = yield from toolrequest(main, [(lambda o: isinstance(o, (Web,Wire,Mesh)), 'mesh to process')], create=False)
	main.insertstmt(format('{}.mergeclose()', args[0]))
	
def tool_stripbuffers(main):
	args = yield from toolrequest(main, [(lambda o: isinstance(o, (Web,Wire,Mesh)), 'mesh to process')], create=False)
	main.insertstmt(format('{}.finish()', args[0]))
	
def tool_flip(main):
	args = yield from toolrequest(main, [(lambda o: isinstance(o, (Web,Wire,Mesh)), 'mesh to process')], create=False)
	main.insertstmt(format('{}.flip()', args[0]))

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
	main.insertexpr(format('Axis({}, {})', origin, Var(dir)))
	
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
	
def tool_circle(main):
	axis, radius = yield from toolrequest(main, [
				(isaxis, 'circle axis'),
				(vec3, 'point on radius'),
				])
	main.insertexpr(format('Circle({}, {})', axis, distance(axis.value[0], radius.value)))
	
def tool_arctangent(main):
	args = yield from toolrequest(main, [
				(vec3, 'start point'), 
				(vec3, 'pass point'), 
				(vec3, 'end point'),
			])
	main.insertexpr(format('ArcTangent({}, {}, {})', *args))
	
def tool_tangentellipsis(main):
	args = yield from toolrequest(main, [
				(vec3, 'start point'), 
				(vec3, 'pass point'), 
				(vec3, 'end point'),
			])
	main.insertexpr(format('TangentEllipsis({}, {}, {})', *args))
	
def tool_softened(main):
	pts = yield from requestmany(main, vec3, "create points")
	main.insertexpr(format('Softened(['+ ', '.join(dump(p) for p in pts) + '])'))
	
def tool_interpolated(main):
	pts = yield from requestmany(main, vec3, "create points")
	main.insertexpr(format('Interpolated(['+ ', '.join(dump(p) for p in pts) + '])'))
	
	
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
		return repr(QInputDialog.getText(main.mainwindow, 'text note', 'enter text:')[0])
		
	if isinstance(var.value, (Mesh,Web,Wire)):
		expr = format('note_leading({}.group({}), text={})', var, item[-1], asktext())
	elif isinstance(var.value, (Wire,vec3,Axis,tuple)):
		expr = format('note_leading({}, text={})', var, asktext())
	else:
		raise ToolError('unable to place a note on top of {}'.format(type(var.value)))
	main.insertexpr(expr)
	
def tool_bounds(main):
	args = yield from toolrequest(main, [(lambda o: isinstance(o, (Web,Wire,Mesh)), 'mesh to size')], create=False)
	main.insertexpr(format('note_bounds({})', args[0]))

	
def tool_text(main):
	pos, = yield from toolrequest(main, [(vec3, 'placement point')])
	text = QInputDialog.getText(main.mainwindow, 'text note', 'enter text:')[0]
	
	main.insertexpr(format('note_floating({}, text={})', pos, text))

def tool_boolean(main):
	args = yield from toolrequest(main, [
				(Mesh, 'first volume'),
				(Mesh, 'second volume'),
				])
	main.insertexpr(format('difference({}, {})', *args))


def tool_extrusion(main):
	outline, = yield from toolrequest(main, [
				(lambda o: isinstance(o, (Web,Wire,Mesh)), 'outline mesh'),
				])
	displt = QInputDialog.getText(main.mainwindow, 'extrusion displacement', 'vector expression:')[0]
	if not displt:
		raise ToolError('no displacement entered')
	main.insertexpr(format('extrusion({}, {})', displt, outline))

def tool_revolution(main):
	outline, axis = yield from toolrequest(main, [
				(lambda o: isinstance(o, (Web,Wire,Mesh)), 'outline mesh'),
				(isaxis, 'revolution axis'),
				])
	angle = QInputDialog.getText(main.mainwindow, 'revolution angle', 'angle (degrees):')[0]
	if not angle:
		raise ToolError('no displacement entered')
	main.insertexpr(format('revolution(radians({}), {}, {})', angle, axis, outline))
	
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
	
def tool_triangulation(main):
	outline, = yield from toolrequest(main, [
				(lambda o: isinstance(o, (Web,Wire) or isprimitive(o)), 'outline'),
				])
	main.insertexpr(format('flatsurface({})', outline))
	
def tool_junction(main):
	scene = main.active_sceneview.scene
	outlines = yield from requestmany(main,
			req=lambda o: isinstance(o, (Web,Wire,Mesh)) or isprimitive(o) or o and isinstance(o, list) and isprimitive(var.value[0]),
			description="select outlines",
			create=False)
	main.insertexpr(format('junction(' + ', '.join(dump(o) for o in outlines) + ')'))



def tool_distance(main):
	crit = lambda o: isinstance(o, vec3) or isaxis(o) or isinstance(o, Segment)
	args = yield from toolrequest(main, [
				(crit, 'start point'),
				(crit, 'end point'),
				])
	target = QInputDialog.getText(main.mainwindow, 'distance constraint', 'target distance:')[0]
	if not target:
		raise ToolError('no distance entered')
	main.insertexpr(format('Distance({}, {}, {})', *args, target))

def tool_radius(main):
	arc, = yield from toolrequest(main, [
				(lambda o: isinstance(o, (ArcThrough, ArcCentered, Circle)), 'arc'),
				])
	target = QInputDialog.getText(main.mainwindow, 'radius constraint', 'target radius:')[0]
	if not target:
		raise ToolError('no radius entered')
	main.insertexpr(format('Radius({}, {})', arc, target))

def tool_angle(main):
	args = yield from toolrequest(main, [
				(lambda o: hasattr(o, 'direction'), 'start segment'),
				(lambda o: hasattr(o, 'direction'), 'second segment'),
				])
	target = QInputDialog.getText(main.mainwindow, 'angle constraint', 'target oriented angle:')[0]
	if not target:
		raise ToolError('no angle entered')
	main.insertexpr(format('Angle({}, {}, radians({}))', *args, target))

def tool_tangent(main):
	args = yield from toolrequest(main, [
				(lambda o: hasattr(o, 'slv_tangent'), 'primitive 1'),
				(lambda o: hasattr(o, 'slv_tangent'), 'primitive 2'),
				])
	common = None
	for v1 in args[0].value.slvvars:
		for v2 in args[1].value.slvvars:
			if getattr(args[0], v1) is getattr(args[1], v2):
				common = v1, v2
	main.insertexpr(format('Tangent({}, {}, {}.{})', args[0], args[1], args[0], common[0]))
				
			
def tool_onplane(main):
	axis, = yield from toolrequest(main, [
				(isaxis, 'axis normal to the plane'),
				])
	pts = []
	
	for disp in scene_unroll(main.active_sceneview.scene):
		if disp.selected:
			var = dispvar(main, disp)
			if var and isinstance(var.value, vec3):
				pts.append(var)
	
	# let the user select or create the points to put on the plane
	if not pts:
		main.assist.info("select the points to keep on plane")
		while True:
			try:	var = yield from select(main, vec3)
			except ToolError: break
			pts.append(var)
	
	main.insertexpr(format('OnPlane({}, [{}])', 
				axis, 
				', '.join(dump(obj) for obj in vars)),
				)

def tool_projected(main):
	crit = lambda o: isinstance(o, vec3) or isaxis(o) or isinstance(o, Segment)
	args = yield from toolrequest(main, [
				(crit, 'start point'),
				(crit, 'end point'),
				])
	along = QInputDialog.getText(main.mainwindow, 'projection constraint', 'vector direction:')[0]
	if not along:
		raise ToolError('no direction entered')
	
	target = QInputDialog.getText(main.mainwindow, 'distance constraint', 'target distance:')[0]
	if not target:
		raise ToolError('no distance entered')
	
	main.insertexpr(format('Distance({}, {}, {}, along={})', *args, target))

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
	
def tool_planar(main):
	args = yield from toolrequest(main, [
				(isaxis, 'normal axis to the plane'),
				])
	main.insertexpr(format('Planar(Solid(), Solid(), {})',  *args))
	
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
	z = vec3(fvec3(transpose(main.active_sceneview.uniforms['view'])[2]))
	main.insertexpr(format('Track(Solid(), Solid(), {})', (axis.value[0], z, cross(z,axis.value[1]))))
	
def tool_helicoid(main):
	axis, = yield from toolrequest(main, [
				(isaxis, 'axis of the helicoid'),
				])
	pitch = QInputDialog.getText(main.mainwindow, 'helicoid joint', 'screw pitch (mm/tr):')[0]
	if not pitch:
		raise ToolError('no pich entered')
	main.insertexpr(format('Helicoid(Solid(), Solid(), {}, {})', pitch, axis))


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

