from PyQt5.QtCore import Qt, QEvent
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QSizePolicy, QShortcut,
							QLabel, QPushButton, QAction, 
							QDockWidget, QFileDialog, QInputDialog
							)
from PyQt5.QtGui import QIcon, QKeySequence, QTextCursor

import os.path
import ast

from madcad.mathutils import vec3
from madcad.primitives import *
from madcad.mesh import Mesh, Wire, Web
from interpreter import astatpos


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

class ToolError(Exception):
	''' exception used to indicate an error in the usage of a Scene tool '''
	pass

def satisfy(obj, req):
	''' return True if obj satisfy the requirement req (type or funcion) '''
	if isinstance(req, type):	return isinstance(obj, req)
	elif callable(req):			return req(obj)
	else:						return False

def toolrequest(main, args):
	match = [None] * len(args)	# matched objects
	missing = []	# missing objects, the create on the fly
	used = set()
	
	# search the selection for the required objects
	for i,(req,comment) in enumerate(args):
		for grp,sub in main.selection:
			if grp in used:	continue
			used.add(grp)
			if satisfy(main.interpreter.current[grp], req):
				match[i] = grp
				break
		else:
			missing.append((i, req, comment))
	
	
	for i,grp in enumerate(match):
		if grp:
			# check that the used objects dont rely on an object that is in the modified area of the script
			if not islive(main, grp):
				raise ToolError('cannot use variable {} moved in the script'.format(repr(grp)))
			# create proper variables for temp objects reused
			if istemp(main, grp):
				newname = autoname(main, grp)
				rename(main, grp, newname)
				match[i] = newname
	
	# create successive missing objects (if they are sufficiently simple objects)
	for i,req,comment in missing:
		main.assist.info(comment)
		if req == vec3:
			create = createpoint(main)
		#elif req == isaxis:
			#o = yield from createpoint(main)
			#p = yield from createpoint(main)
			#match[i] = (o, normalize(p-o))
		else:
			raise ToolError('missing {}'.format(comment))
	
		# run a selection in concurrence with the creation
		def select(main):
			while True:
				evt = yield
				if not (evt.type() == QEvent.MouseButtonPress and evt.button() == Qt.LeftButton):
					continue
				pos = main.active_sceneview.objnear((evt.x(), evt.y()), 10)
				if not pos:	
					continue
				grp,rdr,sub = main.active_sceneview.grpat(pos)
				main.select((grp,sub), True)
				if not satisfy(main.scene[grp], req):
					continue
				# create proper variables for temp objects reused
				if istemp(main, grp):
					newname = autoname(main, grp)
					rename(main, grp, newname)
					return newname
				else:
					return grp
	
		# get the first returned value from the selector or the creation
		iterator = race(select(main), create)
		next(iterator)
		match[i] = yield from iterator
	
	main.selection.clear()
	return match

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
		
		NOTE: 
			the name in the interpreter and in the scene will remain the old name until the script is reexecuted
			the script may be reexecuted during this function call, as the renaming can insert newlines
			the name is changed in main.selection to get things right at the next execution
	'''
	if not islive(main, oldname):
		raise ToolError('cannot rename variable {} in a modified area'.format(repr(oldname)))
	if not newname:
		newname = QInputDialog.getText(main, 'choose variable name', 'new name:')[0]
	if not newname:
		raise ToolError('no new name entered')
	
	# change the name in selection
	newsel = set()
	for grp,sub in main.selection:
		newsel.add((newname,sub) if grp == oldname else (grp,sub))
	main.selection = newsel
	
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
	
def createpoint(main):
	evt = yield
	while evt.type() != QEvent.MouseButtonPress or evt.button() != Qt.LeftButton:
		evt = yield
	c = (evt.x(), evt.y())
	scene = main.active_sceneview
	p = scene.ptfrom(c, scene.manipulator.center)
	main.syncviews([main.addtemp(p)])
	return 'vec3({:.4g}, {:.4g}, {:.4g})'.format(*p)
	
def autoname(main, oldname):
	obj = main.interpreter.current[oldname]
	if isinstance(obj, vec3):	basename = 'P'
	elif isprimitive(obj):		basename = 'L'
	elif isinstance(obj, Mesh):	basename = 'S'
	elif isinstance(obj, Web):	basename = 'W'
	elif isinstance(obj, Wire):	basename = 'C'
	else:	basename = 'O'
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
	main.updatescene()


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
		# cancel shortcut
		self.shortcut = QShortcut(QKeySequence('Escape'), main)
		self.shortcut.activated.connect(self.cancel)
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
		tool = self.main.active_sceneview.tool
		if hasattr(tool, 'throw'):	tool.throw(ToolError('action canceled'))
		self.main.active_sceneview.tool = None
		self.tool(None)
		self.info('no active tool')
		
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
		if text:	text = '• '+text
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
		


def init_toolbars(self):
	tools = self.addToolBar('creation')
	tools.addAction(self.createaction('import', tool_import, 	'madcad-import'))
	tools.addAction('select')
	tools.addAction(QIcon.fromTheme('madcad-solid'), 'solid')
	tools.addAction(QIcon.fromTheme('madcad-meshing'), 'manual meshing')
	tools.addAction(self.createtool('point', tool_point,		'madcad-point'))
	tools.addAction(self.createtool('segment', tool_segment,	'madcad-segment'))
	tools.addAction(self.createtool('arc', tool_arcthrough,		'madcad-arc'))
	tools.addAction(QIcon.fromTheme('madcad-spline'), 'spline')
	tools.addAction('text')
	tools.addAction('image')
	
	tools = self.addToolBar('mesh')
	tools.addAction(self.createtool('boolean', tool_boolean, 'madcad-boolean'))
	tools.addAction(QIcon.fromTheme('madcad-chamfer'), 'chamfer')
	
	tools = self.addToolBar('web')
	tools.addAction(self.createtool('extrusion', tool_extrusion, 'madcad-extrusion'))
	tools.addAction(QIcon.fromTheme('madcad-revolution'), 'revolution')
	tools.addAction(QIcon.fromTheme('madcad-extrans'), 'screw')
	tools.addAction(QIcon.fromTheme('madcad-junction'), 'join')
	tools.addAction(QIcon.fromTheme('madcad-triangulation'), 'surface')
	
	tools = self.addToolBar('amelioration')
	tools.addAction('merge closes')
	tools.addAction('strip buffers')
	
	tools = self.addToolBar('constraints')
	tools.addAction(self.createtool('distance', tool_distance, 'madcad-cst-distance'))
	tools.addAction(self.createtool('radius', tool_radius, 'madcad-cst-radius'))
	tools.addAction(self.createtool('angle', tool_angle, 'madcad-cst-angle'))
	tools.addAction(QIcon.fromTheme('madcad-cst-pivot'), 'pivot')
	tools.addAction(QIcon.fromTheme('madcad-cst-plane'), 'plane')
	tools.addAction(QIcon.fromTheme('madcad-cst-track'), 'track')

def tool_rename(main):
	if not main.selection:
		raise ToolError('no object selected')
	name,_ = next(iter(main.selection))
	rename(main, name)

def tool_import(self):
	filename = QFileDialog.getOpenFileName(self, 'import file', 
						os.curdir, 
						'ply files (*.ply);;stl files (*.stl);;obj files (*.obj)',
						)[0]
	if not filename:
		raise ToolError('no file selected')
	objname = os.path.splitext(os.path.basename(filename))[0]
	if not objname.isidentifier():	objname = 'imported'
	self.insertstmt('{} = read({})'.format(objname, repr(filename)))

def tool_point(main):
	main.assist.tool('point')
	main.assist.info('click to place the point')
	p = yield from createpoint(main)
	main.insertexpr(p)
	
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
	displt = QInputDialog.getText(main, 'extrusion displacement', 'vector expression:')[0]
	if not displt:
		raise ToolError('no displacement entered')
	main.insertexpr('extrusion({}, {})'.format(dplt, obj))

def tool_distance(main):
	args = yield from toolrequest(main, [
				(vec3, 'start point'),
				(vec3, 'end point'),
				])
	target = QInputDialog.getText(main, 'distance constraint', 'target distance:')[0]
	if not target:
		raise ToolError('no distance entered or invalid radius')
	main.insertexpr('Distance({}, {}, {})'.format(*args, target))

def tool_radius(main):
	arc, = yield from toolrequest(main, [
				(lambda o: isinstance(o, (ArcThrough, ArcCentered, Circle)), 'arc'),
				])
	target = QInputDialog.getText(main, 'radius constraint', 'target radius:')[0]
	if not target:
		raise ToolError('no radius entered')
	main.insertexpr('Radius({}, {})'.format(arc, target))

def tool_angle(main):
	args = yield from toolrequest(main, [
				(Segment, 'start segment (angle is oriented)'),
				(Segment, 'second segment (angle is oriented)'),
				])
	target = QInputDialog.getText(main, 'angle constraint', 'target oriented angle:')[0]
	if not target:
		raise ToolError('no angle entered')
	main.insertexpr('Angle({}, {}, {})'.format(*args, target))




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


"""
def tool_point(self):
	def placepoint(scene, evt):
		c = (evt.x(), evt.y())
		p = scene.ptat(c) or scene.ptfrom(c, scene.manipulator.center)
		self.insertexpr(repr(p))
		self.activeview.tool = None
	self.activeview.tool = placepoint

def tool_arcthrough(self, cursor):
	def create(*args):
		self.insertexpr('ArchThrough({}, {}, {})'.format(*args))
		self.activeview.tool = None
	args = self.toolrequest([
				(vec3, 'start point'), 
				(vec3, 'pass point'), 
				(vec3, 'end point'),
			], create)

def toolrequest(self, args, usage):
	match = [None] * len(args)
	missing = []
	for i,(req,comment) in enumerate(args):
		for grp,sub in self.selection:
			obj = self.scene[grp]
			if isinstance(req, type) and isinstance(obj, req) or callable(req) and req(obj):
				match[i] = grp
				break
		else:
			missing.append((i, req, comment))
	def complete():
		for i,(req,comment) in missing:
			if req == vec3:		build = tool_point
			elif req == isaxis:	build = tool_axis
			build()

class ChainedTool:
	__slots__ = 'index', 'chain'
	def __init__(self, chain, finish=None):
		''' chain is a list of successive callables to put in scene.tool '''
		self.index = 0
		self.chain = chain
		if finish:	self.finish = finish
	def __call__(self, scene, evt):
		''' method put in scene.tool '''
		self.chain[self.index](scene, evt)
		if not scene.tool:
			self.index += 1
			if self.index > len(self.chain):
				self.finish()
			else:
				scene.tool = self
	def finish(self):
		''' called after all the chain tools have been executed '''
		pass
"""
