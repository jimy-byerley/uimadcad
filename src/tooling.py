import os.path

from PyQt5.QtCore import Qt, QEvent
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, 
							QLabel, QPushButton, QAction, 
							QDockWidget, QFileDialog,
							)
from PyQt5.QtGui import QIcon, QKeySequence

from madcad.mathutils import vec3

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


def toolrequest(main, args):
	match = [None] * len(args)	# matched objects
	missing = []	# missing objects, the create on the fly
	used = set()
	
	# search the selection for the required objects
	for i,(req,comment) in enumerate(args):
		for grp,sub in main.selection:
			if grp in used:	continue
			used.add(grp)
			obj = main.scene[grp]
			if isinstance(req, type) and isinstance(obj, req) or callable(req) and req(obj):
				match[i] = grp
				break
		else:
			missing.append((i, req, comment))
	
	# create successive missing objects (if they are sufficiently simple objects)
	for i,req,comment in missing:
		main.assist.info(comment)
		if req == vec3:
			match[i] = yield from createpoint(main)
		elif req == isaxis:
			o = yield from createpoint(main)
			p = yield from createpoint(main)
			match[i] = (o, normalize(p-o))
		else:
			raise ToolError('no routine to satisfy request for '+repr(req))
	
	main.selection.clear()
	return match

class ToolError(Exception):
	''' exception used to indicate an error in the usage of a Scene tool '''
	pass
		

def toolcapsule(main, name, procedure):
	main.assist.tool(name)
	main.assist.info('')
	try:
		yield from procedure(main)
	except ToolError as err:
		main.assist.info(str(err))
	else:
		main.assist.tool('')
		main.assist.info('')
	main.updatescene()

def createtool(main, icon, name, procedure):
	''' create a QAction for the main class, with the given generator procedure '''
	def callback():
		gen = toolcapsule(main, name, procedure)
		try:	next(gen)
		except StopIteration:	pass
		else:
			def tool(scene, evt):
				try:	gen.send(evt)
				except StopIteration:	
					scene.tool = None
					main.updatescene()
			main.active_sceneview.tool = tool
	action = QAction(QIcon.fromTheme(icon), name, main)
	action.triggered.connect(callback)
	return action

def createaction(main, icon, name, procedure):
	''' create a QAction for the main class, with a one-shot procedure '''
	action = QAction(QIcon.fromTheme(icon), name, main)
	action.triggered.connect(lambda: procedure(main))
	return action


class ToolAssist(QWidget):
	''' assistant widget (or window) that pop up when a tool is enabled '''
	def __init__(self, main, parent=None):
		super().__init__(parent)
		self.main = main
		self.visible = False
		self._tool = QLabel()
		self._info = QLabel()
		f = self._tool.font()
		f.setPointSize(int(f.pointSize()*1.2))
		self._tool.setFont(f)
		cancel = QPushButton('cancel', shortcut=QKeySequence('Esc'))
		cancel.clicked.connect(self.cancel)
		layout = QVBoxLayout()
		layout.addWidget(self._tool)
		layout.addWidget(self._info)
		layout.addWidget(cancel)
		self.setLayout(layout)
		self.tool(None)
		
	def cancel(self):
		tool = self.main.active_sceneview.tool
		if hasattr(tool, 'throw'):	tool.throw(ToolError('action canceled'))
		self.main.active_sceneview.tool = None
		self.tool(None)
		self.info('no active tool')
		
	def tool(self, name):
		if name:	
			self._tool.setText('<b>{}</b>'.format(name))
			self.visible = True
		else:		
			self._info.setText('no active tool')
			self.visible = False
		self.update_visibility()
	def info(self, text):
		if text:	text = '• '+text
		self._info.setText(text)
	
	def update_visibility(self):
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
	tools.addAction(createaction(self, 'madcad-import', 'import', tool_import))
	tools.addAction('select')
	tools.addAction(QIcon.fromTheme('madcad-solid'), 'solid')
	tools.addAction(QIcon.fromTheme('madcad-meshing'), 'manual meshing')
	tools.addAction(createtool(self, 'madcad-point', 'point', 		tool_point))
	tools.addAction(createtool(self, 'madcad-segment', 'segment', 	tool_segment))
	tools.addAction(createtool(self, 'madcad-arc', 'arc', 			tool_arcthrough))
	tools.addAction(QIcon.fromTheme('madcad-spline'), 'spline')
	
	tools = self.addToolBar('mesh')
	tools.addAction(QIcon.fromTheme('madcad-boolean'), 'boolean')
	tools.addAction(QIcon.fromTheme('madcad-chamfer'), 'chamfer')
	
	tools = self.addToolBar('web')
	tools.addAction(QIcon.fromTheme('madcad-extrusion'), 'extrusion')
	tools.addAction(QIcon.fromTheme('madcad-revolution'), 'revolution')
	tools.addAction(QIcon.fromTheme('madcad-extrans'), 'screw')
	tools.addAction(QIcon.fromTheme('madcad-junction'), 'join')
	tools.addAction(QIcon.fromTheme('madcad-triangulation'), 'surface')
	
	tools = self.addToolBar('amelioration')
	tools.addAction('merge closes')
	tools.addAction('strip buffers')
	
	tools = self.addToolBar('constraints')
	tools.addAction(QIcon.fromTheme('madcad-cst-distance'), 'distance')
	tools.addAction(QIcon.fromTheme('madcad-cst-radius'), 'radius')
	tools.addAction(QIcon.fromTheme('madcad-cst-angle'), 'angle')
	tools.addAction(QIcon.fromTheme('madcad-cst-pivot'), 'pivot')
	tools.addAction(QIcon.fromTheme('madcad-cst-plane'), 'plane')
	tools.addAction(QIcon.fromTheme('madcad-cst-track'), 'track')


def tool_import(self):
	filename = QFileDialog.getOpenFileName(self, 'import file', 
						os.curdir, 
						'ply files (*.ply);;stl files (*.stl);;obj files (*.obj)',
						)[0]
	if filename:
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

def createpoint(main):
	evt = yield
	while evt.type() != QEvent.MouseButtonPress or evt.button() != Qt.LeftButton:
		evt = yield None
	c = (evt.x(), evt.y())
	scene = main.active_sceneview
	p = scene.ptat(c) or scene.ptfrom(c, scene.manipulator.center)
	main.addtemp(p)
	return 'vec3({:.5g}, {:.5g}, {:.5g})'.format(*p)



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
