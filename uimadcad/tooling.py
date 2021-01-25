from PyQt5.QtCore import Qt, QEvent
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QSizePolicy, QShortcut,
							QLabel, QPushButton, QAction, 
							QDockWidget, QFileDialog, QInputDialog
							)
from PyQt5.QtGui import QIcon, QKeySequence, QTextCursor

import os.path
import ast

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
		self.generator = None
		self._tool = QLabel()
		self._info = QLabel()
		
		# configure labels
		self._info.setSizePolicy(QSizePolicy(QSizePolicy.Fixed, QSizePolicy.Minimum))
		self._tool.setSizePolicy(QSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed))
		f = self._tool.font()
		f.setPointSize(int(f.pointSize()*1.2))
		self._tool.setFont(f)
		# cancel shortcut
		self.shortcut = QAction('cancel', self, shortcut=QKeySequence('Escape'))
		self.shortcut.triggered.connect(self.cancel)
		self.addAction(self.shortcut)
		# cancel button
		cancel = QPushButton('cancel')
		cancel.clicked.connect(self.cancel)
		
		# ui layout
		layout = QVBoxLayout()
		layout.addWidget(self._tool)
		layout.addWidget(self._info)
		layout.addWidget(cancel)
		self.setLayout(layout)
		self.tool(None)
		
	def cancel(self):
		''' cancel the current tool procedure '''
		if self.generator:
			try:	self.generator.throw(ToolError('action canceled'))
			except ToolError:	pass
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
	

def toolrequest(main, args, create=True):
	match = [None] * len(args)	# matched objects
	
	# search the selection for the required objects
	for disp in scene_unroll(main.active_sceneview.scene):
		if disp.selected:
			name = dispname(main, disp)
			if name:
				for i,(req,comment) in enumerate(args):
					if not match[i] and satisfy(main.interpreter.current[name], req):
						match[i] = name
						break
	
	for i,name in enumerate(match):
		if not name:	continue
		# check that the used objects dont rely on an object that is in the modified area of the script
		if not islive(main, name):
			raise ToolError('cannot use variable {} moved in the script'.format(repr(grp)))
		# create proper variables for temp objects reused
		if istemp(main, name):
			newname = autoname(main, main.interpreter.current[name])
			rename(main, name, newname)
			match[i] = newname
	
	# create successive missing objects (if they are sufficiently simple objects)
	for i,(req,comment) in enumerate(args):
		if match[i]:	continue
		
		main.assist.info(comment)
		if req not in completition or not create:
			raise ToolError('missing {}'.format(comment))
	
		# run a selection in concurrence with the creation
		def select(main):
			while True:
				evt = yield
				if not (evt.type() == QEvent.MouseButtonRelease and evt.button() == Qt.LeftButton):
					continue
				view = main.active_sceneview
				pos = view.somenear(evt.pos(), 10)
				if not pos:	
					continue
				key = view.itemat(pos)
				disp = view.scene.item(key)
				name = dispname(main, disp)
				if not name or not satisfy(main.interpreter.current[name], req):
					continue
				disp.selected = True
				# create proper variables for temp objects reused
				if istemp(main, name):
					newname = autoname(main, main.interpreter.current[name])
					rename(main, name, newname)
					return newname
				else:
					return name

		# get the first returned value from the selector or the creation
		iterator = race(select(main), completition[req](main))
		next(iterator)
		match[i] = yield from iterator
	
	deselectall(main)
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
	
def dispname(main, disp):
	if hasattr(disp, 'source') and disp.source:
		return main.interpreter.ids.get(id(disp.source))

	

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
		cursor = QTextCursor(main.script)
		zone = node.targets[0]
		cursor.setPosition(zone.position)
		cursor.setPosition(zone.end_position, QTextCursor.KeepAnchor)
		cursor.insertText(newname)
	
	# the renamed object is a temporary variable
	else:
		stmt = main.interpreter.ast.body[astatpos(main.interpreter.ast, node.position)]
		cursor = QTextCursor(main.script)
		cursor.beginEditBlock()
		
		# the expression result is not used, just assign it
		if isinstance(stmt, ast.Expr) and stmt.position == node.position and stmt.end_position == node.end_position:
			# just insert the assignation
			cursor.setPosition(node.position)
			cursor.insertText('{} = '.format(newname))
		# the expression result is used, move it and assign it
		else:
			# get and remove the expression
			cursor.setPosition(node.position)
			cursor.setPosition(node.end_position, QTextCursor.KeepAnchor)
			expr = cursor.selectedText()	
			cursor.insertText(newname)
			# insert expression with assignation
			cursor.setPosition(stmt.position)
			cursor.insertText('{} = {}\n'.format(newname, expr))
		
		cursor.endEditBlock()
		
def deselectall(main):
	for disp in scene_unroll(main.active_sceneview.scene):
		if disp.selected:	disp.selected = False
		if type(disp).__name__ in ('MeshDisplay', 'WebDisplay'):
			disp.vertices.flags &= 0x11111110
			disp.vertices.flags_updated = True
	main.active_sceneview.update()
	main.updatescript()
	
def set_active_solid(main):
	for disp in scene_unroll(main.active_sceneview.scene):
		if isinstance(disp, Solid.display):
			if disp.selected:	
				main.active_sceneview.scene.active_solid = disp
				break
	
def createpoint(main):
	evt = yield from waitclick()
	view = main.active_sceneview
	p = view.ptfrom(evt.pos(), view.navigation.center)
	main.addtemp(p)
	view.scene.add(p)
	view.update()
	return p
	
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
	return axis
	

def autoname(main, obj):
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
	
	


def toolcapsule(main, name, procedure):
	main.assist.tool(name)
	main.assist.info('')
	try:
		yield from procedure(main)
	except ToolError as err:
		main.assist.info('<b style="color:#ff5555">{}</b>'.format(err))
	else:
		main.assist.tool('')
		main.assist.info('')


def create_toolbars(main, widget):
	tools = widget.addToolBar('creation')
	tools.addAction(main.createaction('import', tool_import, 	'madcad-import'))
	tools.addAction(QIcon.fromTheme('madcad-solid'), 'solid')
	tools.addAction(QIcon.fromTheme('madcad-meshing'), 'manual triangulated meshing')
	tools.addAction(QIcon.fromTheme('madcad-splined'), 'manual splined meshing')
	tools.addAction(main.createtool('point', tool_point,		'madcad-point'))
	tools.addAction(main.createtool('segment', tool_segment,	'madcad-segment'))
	tools.addAction(main.createtool('arc', tool_arcthrough,		'madcad-arc'))
	tools.addAction(QIcon.fromTheme('madcad-spline'), 'spline')
	tools.addAction(QIcon.fromTheme('insert-text'), 'text')
	tools.addAction(QIcon.fromTheme('insert-image'), 'image')
	tools.addAction(QIcon.fromTheme('madcad-annotation'), 'annotation')
	
	tools = widget.addToolBar('mesh')
	tools.addAction(main.createtool('boolean', tool_boolean, 'madcad-boolean'))
	tools.addAction(QIcon.fromTheme('madcad-chamfer'), 'chamfer')
	
	tools = widget.addToolBar('web')
	tools.addAction(main.createtool('extrusion', tool_extrusion, 'madcad-extrusion'))
	tools.addAction(QIcon.fromTheme('madcad-revolution'), 'revolution')
	tools.addAction(QIcon.fromTheme('madcad-extrans'), 'screw')
	tools.addAction(QIcon.fromTheme('madcad-junction'), 'join')
	tools.addAction(QIcon.fromTheme('madcad-triangulation'), 'surface')
	
	tools = widget.addToolBar('amelioration')
	tools.addAction(main.createtool('merge closes', tool_mergeclose, 'madcad-mergeclose'))
	tools.addAction(main.createtool('strip buffers', tool_stripbuffers, 'madcad-stripbuffer'))
	
	tools = widget.addToolBar('constraints')
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
			name = dispname(main, disp)
			if name:
				rename(main, name)
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
	main.insertexpr(repr(p))
	
def tool_segment(main):
	args = yield from toolrequest(main, [
				(vec3, 'start point'),
				(vec3, 'end point'),
			])
	main.insertexpr('Segment({}, {})'.format(*args))

def tool_arcthrough(main):
	args = yield from toolrequest(main, [
				(vec3, 'start point'), 
				(vec3, 'pass point'), 
				(vec3, 'end point'),
			])
	main.insertexpr('ArcThrough({}, {}, {})'.format(*args))

def tool_boolean(main):
	args = yield from toolrequest(main, [
				(Mesh, 'first volume'),
				(Mesh, 'second volume'),
				])
	main.insertexpr('difference({}, {})'.format(*args))
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
	obj = yield from toolrequest(main, [
				(lambda o: isinstance(o, (Web,Mesh)), 'first volume'),
				])
	displt = QInputDialog.getText(main.mainwindow, 'extrusion displacement', 'vector expression:')[0]
	if not displt:
		raise ToolError('no displacement entered')
	main.insertexpr('extrusion({}, {})'.format(displt, obj))




def tool_distance(main):
	args = yield from toolrequest(main, [
				(vec3, 'start point'),
				(vec3, 'end point'),
				])
	target = QInputDialog.getText(main.mainwindow, 'distance constraint', 'target distance:')[0]
	if not target:
		raise ToolError('no distance entered or invalid radius')
	main.insertexpr('Distance({}, {}, {})'.format(*args, target))

def tool_radius(main):
	arc, = yield from toolrequest(main, [
				(lambda o: isinstance(o, (ArcThrough, ArcCentered, Circle)), 'arc'),
				])
	target = QInputDialog.getText(main.mainwindow, 'radius constraint', 'target radius:')[0]
	if not target:
		raise ToolError('no radius entered')
	main.insertexpr('Radius({}, {})'.format(arc, target))

def tool_angle(main):
	args = yield from toolrequest(main, [
				(Segment, 'start segment (angle is oriented)'),
				(Segment, 'second segment (angle is oriented)'),
				])
	target = QInputDialog.getText(main.mainwindow, 'angle constraint', 'target oriented angle:')[0]
	if not target:
		raise ToolError('no angle entered')
	main.insertexpr('Angle({}, {}, {})'.format(*args, target))

def tool_tangent(main):
	args = yield from toolrequest(main, [
				(object, 'primitive 1'),
				(object, 'primitive 2'),
				])
	for v1 in args[0].slvvars:
		for v2 in args[1].slvvars:
			indev
			
def tool_planar(main):
	args = yield from toolrequest(main, [
				(Axis, 'axis normal to the plane'),
				])
	# let the user select or create the points to put on the plane
	indev


def tool_pivot(main):
	args = yield from toolrequest(main, [
				(Axis, 'axis of the pivot'),
				])
	main.insertexpr('Pivot(Solid(), Solid(), {})'.format(args[0]))

def tool_gliding(main):
	args = yield from toolrequest(main, [
				(Axis, 'axis of the pivot'),
				])
	main.insertexpr('Gliding(Solid(), Solid(), {})'.format(args[0]))
	
def tool_plane(main):
	args = yield from toolrequest(main, [
				(Axis, 'normal axis to the plane'),
				])
	main.insertexpr('Plane(Solid(), Solid(), {})'.format(args[0]))
	
def tool_ball(main):
	args = yield from toolrequest(main, [
				(vec3, 'position of the ball'),
				])
	main.insertexpr('Ball(Solid(), Solid(), {})'.format(args[0]))
	
def tool_punctiform(main):
	args = yield from toolrequest(main, [
				(Axis, 'normal axis to the plane'),
				])
	main.insertexpr('Punctiform(Solid(), Solid(), {})'.format(args[0]))
	
def tool_track(main):
	(o,x), = yield from toolrequest(main, [
				(Axis, 'axis of the track'),
				])
	z = vec3(fvec3(main.active_sceneview.uniforms['view'][2]))
	main.insertexpr('Track(Solid(), Solid(), {})'.format((o,x,z)))
	
def tool_helicoid(main):
	axis, = yield from toolrequest(main, [
				(Axis, 'axis of the helicoid'),
				])
	pitch = QInputDialog.getText(main.mainwindow, 'helicoid joint', 'screw pitch (/tr):')[0]
	if not pitch:
		raise ToolError('no pich entered')
	main.insertexpr('Helicoid(Solid(), Solid(), {}, {})'.format(pitch, axis))


# tools that will automatically used to create missing objects in request
completition = {
	vec3:	createpoint,
	Axis:	createaxis,
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

