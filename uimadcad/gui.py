from PyQt5.QtCore import (
		Qt, QSize, QRect, QPoint, QPointF,
		QEvent, pyqtSignal,
		)
from PyQt5.QtWidgets import (
		QVBoxLayout, QWidget, QHBoxLayout, QStyleFactory, QSplitter, QSizePolicy, QAction,
		QPlainTextDocumentLayout, 
		QPushButton, QLabel, QComboBox,
		QMainWindow, QDockWidget, QFileDialog, QMessageBox, QDialog
		)
from PyQt5.QtGui import (
		QFont, QFontMetrics, 
		QColor, QPalette,
		QIcon, QKeySequence, 
		QTextOption, QTextDocument, QTextCursor,
		)

from madcad import *
from madcad import displays
from madcad.rendering import Display, Group, Turntable, Orbit, Displayable
from madcad.annotations import annotations
import madcad.settings

from .common import *
from .interpreter import Interpreter, InterpreterError, astinterval
from .scriptview import ScriptView
from .sceneview import Scene, SceneView, SceneList
from .errorview import ErrorView
from .detailview import DetailView
from .tricks import PointEditor, EditionError
from . import tooling

from copy import deepcopy, copy
from nprint import nprint
import ast
import traceback
import os
import re


version = '0.5'

from weakref import WeakSet, ref
from PyQt5.QtCore import QObject, QStringListModel

class Madcad(QObject):
	executed = pyqtSignal()
	exectarget_changed = pyqtSignal()
	
	def __init__(self):
		super().__init__()
		
		# main components
		self.script = QTextDocument(self)
		self.script.setDocumentLayout(QPlainTextDocumentLayout(self.script))
		self.script.contentsChange.connect(self._contentsChange)
		self.interpreter = Interpreter()
		self.assist = tooling.ToolAssist(self)
		self.scenesmenu = QStringListModel()
		self.hiddens = set()
		self.displayzones = []
		self.neverused = set()
		
		self.scenes = WeakSet()
		self.views = WeakSet()
		self.mainwindow = None
		self.active_sceneview = None
		self.active_scriptview = None
		self.active_errorview = None
		self.active_solid = None
		
		self.selection = set()
		self.exectrigger = 1
		self.exectarget = 0
		self.editors = {}
		self.details = {}
		
		self.currentfile = None
		self.currentexport = None
		
		self.startup()
	
	@staticmethod
	def create_config():
		''' create and fill the config directory if not already existing '''
		from os.path import dirname
		file = settings.locations['settings']
		if not os.exists(file):
			os.makedirs(dirname(file), exist_ok=True)
			settings.dump()
		file = settings.locations['startup']
		if not os.exists(file):
			os.makedirs(dirname(file), exist_ok=True)
			open(file, 'w').write('from madcad import *\n\n')
	
	def startup(self):
		''' set madcad in the startup state (software openning state) '''
		self.create_config()
		settings.load()
		cursor = QTextCursor(self.script)
		cursor.insertText(open(settings.locations['startup'], 'r').read())
	

def iter_scenetree(obj):
	for disp in obj.displays.values():
		yield disp
		if isinstance(disp, Group):
			yield from iter_scenetree(disp)		


class Main(QMainWindow):
	''' the main madcad window '''
	
	# signals
	exectarget_changed = pyqtSignal()
	executed = pyqtSignal()
	
	# BEGIN --- paneling and initialization ---
	
	def __init__(self, parent=None, filename=None):
		super().__init__(parent)
		# window setup
		self.setWindowRole('madcad')
		self.setWindowIcon(QIcon.fromTheme('madcad'))
		self.setMinimumSize(500,300)
		
		# main components
		self.script = QTextDocument(self)
		self.script.setDocumentLayout(QPlainTextDocumentLayout(self.script))
		self.script.contentsChange.connect(self._contentsChange)
		self.interpreter = Interpreter()
		self.scenelist = SceneList(self)
		self.assist = tooling.ToolAssist(self)
		self.scenesmenu = SceneList(self)
		self.hiddens = set()
		self.displayzones = []
		self.neverused = set()
		
		self.scenes = []	# objets a afficher sur les View
		self.views = []
		self.active_sceneview = None
		self.active_scriptview = None
		self.active_errorview = None
		self.active_solid = None
		
		self.selection = set()
		self.exectrigger = 1
		self.exectarget = 0
		self.editors = {}
		self.details = {}
		
		self.standardcameras = {
			'-Z': fquat(fvec3(0, 0, 0)),
			'+Z': fquat(fvec3(pi, 0, 0)),
			'-X': fquat(fvec3(pi/2, 0, 0)),
			'+X': fquat(fvec3(pi/2, 0, pi)),
			'-Y': fquat(fvec3(pi/2, 0, -pi/2)),
			'+Y': fquat(fvec3(pi/2, 0, pi/2)),
			}
		
		self.currentfile = None
		self.currentexport = None
		
		# insert components to docker
		self.script.modificationChanged.connect(self.setWindowModified)
		self.setDockNestingEnabled(True)
		self.addDockWidget(Qt.LeftDockWidgetArea, dock(ScriptView(self), 'script view'))
		self.addDockWidget(Qt.RightDockWidgetArea, dock(SceneView(self), 'scene view'))
		#self.scenelistdock = dock(SceneList(self), 'forced variables display')
		#self.addDockWidget(Qt.LeftDockWidgetArea, self.scenelistdock)
		self.addDockWidget(Qt.LeftDockWidgetArea, dock(self.assist, 'tool assist'))
		#self.addDockWidget(Qt.BottomDockWidgetArea, dock(self.console, 'console'))
		#self.resizeDocks([self.scenelistdock], [0], Qt.Horizontal)	# Qt 5.10 hack to avoid issue of docks reseting their size after user set it
		
		#self.details = DictView(self, 3, {'type': 'flat', 'precision':5.232311e-3, 'color':fvec3(0.1,0.2,0.3), 'comment':'this is a raw surface, TODO'})
		#self.details.show()
		#self.views.append(self.details)
		
		self.init_menus()
		self.init_toolbars()
		self.restoreState(b'\x00\x00\x00\xff\x00\x00\x00\x00\xfd\x00\x00\x00\x02\x00\x00\x00\x00\x00\x00\x01q\x00\x00\x02+\xfc\x02\x00\x00\x00\x03\xfb\xff\xff\xff\xff\x01\x00\x00\x00\x1c\x00\x00\x02+\x00\x00\x00\x87\x01\x00\x00\x03\xfb\xff\xff\xff\xff\x00\x00\x00\x01\x8e\x00\x00\x00\xb9\x00\x00\x00:\x01\x00\x00\x03\xfb\xff\xff\xff\xff\x00\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00z\x01\x00\x00\x03\x00\x00\x00\x01\x00\x00\x02:\x00\x00\x02+\xfc\x02\x00\x00\x00\x01\xfb\xff\xff\xff\xff\x01\x00\x00\x00\x1c\x00\x00\x02+\x00\x00\x000\x01\x00\x00\x03\x00\x00\x00\x00\x00\x00\x02+\x00\x00\x00\x04\x00\x00\x00\x04\x00\x00\x00\x08\x00\x00\x00\x08\xfc\x00\x00\x00\x03\x00\x00\x00\x00\x00\x00\x00\x02\xff\xff\xff\xff\x03\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\x00\x00\x00\x00\x00\xff\xff\xff\xff\x03\x00\x00\x014\x00\x00\x00L\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x03\xff\xff\xff\xff\x03\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\x00\x00\x00\x00\x00\xff\xff\xff\xff\x03\x00\x00\x00\xda\xff\xff\xff\xff\x00\x00\x00\x00\x00\x00\x00\x00\xff\xff\xff\xff\x03\x00\x00\x01,\x00\x00\x00d\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x02\x00\x00\x00\x00')
		self.update_title()
		
		cursor = QTextCursor(self.script)
		cursor.insertText('from madcad import *\n\n')
	
	def closeEvent(self, evt):
		# close all the subwindows
		for view in self.views:
			view.close()
		evt.accept()
	
	def init_menus(self):
		menubar = self.menuBar()
		menu = menubar.addMenu('&File')
		menu.addAction(QIcon.fromTheme('document-open'), 'open', self._open, QKeySequence('Ctrl+O'))
		menu.addAction(QIcon.fromTheme('document-save'), 'save', self._save, QKeySequence('Ctrl+S'))
		menu.addAction(QIcon.fromTheme('document-save-as'), 'save as', self._save_as, QKeySequence('Ctrl+Shift+S'))
		menu.addAction(QIcon.fromTheme('emblem-shared'), 'export +', self._export, QKeySequence('Ctrl+E'))
		menu.addAction(QIcon.fromTheme('insert-image'), 'screenshot +', self._screenshot, QKeySequence('Ctrl+I'))
		menu.addSeparator()
		menu.addAction(QIcon.fromTheme('emblem-system'), 'settings +')
		
		menu = menubar.addMenu('&Edit')
		menu.addAction(QIcon.fromTheme('edit-undo'), 'undo', self.script.undo, QKeySequence('Ctrl+Z'))
		menu.addAction(QIcon.fromTheme('edit-redo'), 'redo', self.script.redo, QKeySequence('Ctrl+Shift+Z'))
		menu.addAction(QIcon.fromTheme('media-playback-start'), 'execute', self.execute, QKeySequence('Ctrl+Return'))
		menu.addAction(QIcon.fromTheme('view-refresh'), 'reexecute all', self.reexecute, QKeySequence('Ctrl+Shift+Return'))
		menu.addAction('target to cursor', self._targettocursor, QKeySequence('Ctrl+T'))
		menu.addSeparator()
		menu.addAction('disable line +')
		menu.addAction('enable line +')
		menu.addAction('disable line dependencies +')
		menu.addSeparator()
		menu.addAction(self.createaction('rename object', tooling.tool_rename, shortcut=QKeySequence('F2')))
		menu.addSeparator()
		menu.addAction(QIcon.fromTheme('edit-select-all'), 'deselect all', self._deselectall, QKeySequence('Ctrl+A'))
		
		menu = menubar.addMenu('&View')
		menu.addAction(QAction('display navigation controls +', self, checkable=True))
		menu.addSeparator()
		menu.addAction('new 3D view', self.new_sceneview)
		menu.addAction('new text view', 
			lambda: self.addDockWidget(Qt.RightDockWidgetArea, dock(ScriptView(self), 'build script')))
		menu.addSeparator()
		#action = self.scenelistdock.toggleViewAction()
		#action.setShortcut(QKeySequence('Shift+D'))
		#menu.addAction(action)
		menu.addAction('reset solids poses', self.reset_poses)
		menu.addAction('set as current solid', self._set_current_solid)
		menu.addSeparator()
		
		themes = menu.addMenu('theme preset')
		themes.addAction('system +')
		themes.addAction('blue +')
		themes.addAction('orange +')
		themes.addAction('grey +')
		themes.addAction('white +')
		themes.addAction('dark +')
		
		layouts = menu.addMenu('layout preset')
		layouts.addAction('simple +')
		layouts.addAction('side toolbar +')
		layouts.addAction('multiview +')
		layouts.addAction('compact +')
		layouts.addAction('vertical +')
		
		menu.addAction('harvest toolbars on window side +')
		menu.addAction('take floating toolbars to mouse +')
		menu.addAction('save window layout', lambda: print(self.saveState()))
		
		menu = menubar.addMenu('&Scene')
		action = QAction('display points', self, checkable=True, shortcut=QKeySequence('Shift+P'))
		action.setChecked(madcad.settings.scene['display_points'])
		action.toggled.connect(self._display_points)
		menu.addAction(action)
		action = QAction('display wire', self, checkable=True, shortcut=QKeySequence('Shift+W'))
		action.setChecked(madcad.settings.scene['display_wire'])
		action.toggled.connect(self._display_wire)
		menu.addAction(action)
		action = QAction('display groups', self, checkable=True, shortcut=QKeySequence('Shift+G'))
		action.setChecked(madcad.settings.scene['display_groups'])
		action.toggled.connect(self._display_groups)
		menu.addAction(action)
		action = QAction('display faces', self, checkable=True, shortcut=QKeySequence('Shift+F'))
		action.setChecked(madcad.settings.scene['display_faces'])
		action.toggled.connect(self._display_faces)
		menu.addAction(action)
		action = QAction('display annotations +', self, checkable=True, shortcut=QKeySequence('Shift+T'))
		menu.addAction(action)
		action = QAction('display grid', self, checkable=True, shortcut=QKeySequence('Shift+B'))
		action.setChecked(madcad.settings.scene['display_grid'])
		action.toggled.connect(self._display_grid)
		menu.addAction(action)
		menu.addSeparator()
		menu.addAction('center on object', self._viewcenter, shortcut=QKeySequence('Shift+C'))
		menu.addAction('adjust to object', self._viewadjust, shortcut=QKeySequence('Shift+A'))
		menu.addAction('look to object', self._viewlook, shortcut=QKeySequence('Shift+L'))
		menu.addSeparator()
		
		
		def standardcamera(name):
			orient = self.standardcameras[name]
			nav = self.active_sceneview.navigation
			if isinstance(nav, Turntable):
				nav.yaw = roll(orient)
				nav.pitch = pi/2 - pitch(orient)
			elif isinstance(nav, Orbit):
				nav.orient = orient
			else:
				raise TypeError('navigation type {} is not supported for standardcameras'.format(type(nav)))
			self.active_sceneview.update()
		
		cameras = menu.addMenu("standard cameras")
		cameras.addAction('-Z &top',	lambda: standardcamera('-Z'), shortcut=QKeySequence('Y'))
		cameras.addAction('+Z &bottom',	lambda: standardcamera('+Z'), shortcut=QKeySequence('Shift+Y'))
		cameras.addAction('-X &front',	lambda: standardcamera('-X'), shortcut=QKeySequence('U'))
		cameras.addAction('+X &back',	lambda: standardcamera('+X'), shortcut=QKeySequence('Shift+U'))
		cameras.addAction('-Y &right',	lambda: standardcamera('-Y'), shortcut=QKeySequence('I'))
		cameras.addAction('+Y &left',	lambda: standardcamera('+Y'), shortcut=QKeySequence('Shift+I'))
		
		anims = menu.addMenu('camera animations')
		anims.addAction('rotate &world +')
		anims.addAction('rotate &local +')
		anims.addAction('rotate &random +')
		anims.addAction('cyclic &adapt +')
		
		menu.addSeparator()
		
		menu.addAction('explode objects +')
		
		
		menu = menubar.addMenu('Scrip&t')
		action = QAction('show line numbers', self, checkable=True, shortcut=QKeySequence('F11'))
		action.toggled.connect(self._show_line_numbers)
		menu.addAction(action)
		action = QAction('enable line wrapping', self, checkable=True, shortcut=QKeySequence('F10'))
		action.toggled.connect(self._enable_line_wrapping)
		menu.addAction(action)
		action = QAction('scroll on selected object +', self, checkable=True)
		#action.toggled.connect(self._enable_center_on_select)	# TODO when settings will be added
		menu.addAction(action)
		menu.addAction('find +')
		menu.addAction('replace +')
		
		menu = menubar.addMenu('&Graphic')
		menu.addAction(QAction('display curve labels +', self, checkable=True))
		menu.addAction(QAction('display curve points +', self, checkable=True))
		menu.addAction(QAction('display axis ticks +', self, checkable=True))
		menu.addAction(QAction('display grid +', self, checkable=True))
		menu.addSeparator()
		menu.addAction('adapt to curve +')
		menu.addAction('zoom on zone +')
		menu.addAction('stick to zero +')
		menu.addAction('set ratio to unit +')
		
	def init_toolbars(self):
		tooling.init_toolbars(self)
		
	def createtool(self, name, procedure, icon=None, shortcut=None):
		''' create a QAction for the main class, with the given generator procedure '''
		action = QAction(name, self)
		if shortcut:	action.setShortcut(shortcut)
		if icon:		action.setIcon(QIcon.fromTheme(icon))
		def callback():
			gen = tooling.toolcapsule(self, name, procedure)
			try:	next(gen)
			except StopIteration:	pass
			else:
				def tool(evt, view=self.active_sceneview):
					try:	gen.send(evt)
					except StopIteration:	
						view.scene.sync()
						view.tool.remove(tool)
				self.active_sceneview.tool.append(tool)
		action.triggered.connect(callback)
		return action

	def createaction(self, name, procedure, icon=None, shortcut=None):
		''' create a QAction for the main class, with a one-shot procedure '''
		action = QAction(name, self)
		if shortcut:	action.setShortcut(shortcut)
		if icon:		action.setIcon(QIcon.fromTheme(icon))
		def callback():
			try:				procedure(self)
			except tooling.ToolError as err:	
				self.assist.tool(name)
				self.assist.info('<b style="color:#ff5555">{}</b>'.format(err))
		action.triggered.connect(callback)
		
		return action
	
	def new_sceneview(self):
		''' open a new sceneview floating at the center of the main window '''
		self.addDockWidget(Qt.RightDockWidgetArea, dock(SceneView(self), 'scene view'))
	
	def update_title(self):
		if self.currentfile:
			#filename = self.currentfile[self.currentfile.rfind(os.sep)+1:]
			#self.setWindowTitle('{} - ̶-  madcad v{}'.format(filename, version))
			self.setWindowFilePath(self.currentfile)
		else:
			#self.setWindowTitle('madcad v{}'.format(version))
			self.setWindowFilePath('')
		self.script.setModified(False)
	
	def reset_poses(self):
		indev
	
	# END
	# BEGIN --- file management system ---
	
	def _open(self):
		''' callback for the button 'open'
			ask the user for a new file and then call self._load(filename)
		'''
		filename = QFileDialog.getOpenFileName(self, 'open madcad file', 
							os.curdir, 
							'madcad files (*.py *.mc);;text files (*.txt)',
							)[0]
		if filename:
			self._load(filename)
	
	def _load(self, filename):
		''' clears the current workspace and load the specified file
		'''
		extension = filename[filename.find('.')+1:]
		if extension not in ('py', 'txt'):
			box = QMessageBox(
				QMessageBox.Warning, 'bad file type', 
				"The file extension '{}' is not a standard madcad file extension and may result in problems in openning the file from a browser\n\nOpen anyway ?".format(extension),
				QMessageBox.Yes | QMessageBox.Discard,
				)
			if box.exec() == QMessageBox.Discard:	return False
			else:	extension = 'py'
		
		os.chdir(os.path.split(os.path.abspath(filename))[0])
		self.currentfile = filename
		if extension in ('py', 'txt'):
			self.script.clear()
			QTextCursor(self.script).insertText(open(filename, 'r').read())
		
		self.update_title()
		return True
				
	
	def _save(self):
		''' callback for the button 'save'
			save to the file specified in self.currentfile, using its extension
		'''
		if not self.currentfile:	self._save_as()
		else:
			extension = self.currentfile[self.currentfile.find('.')+1:]
			if extension not in ('py', 'txt'):
				box = QMessageBox(
					QMessageBox.Warning, 'bad file type', 
					"The file extension '{}' is not a standard madcad file extension and may result in problems to open the file from a browser\n\nSave anyway ?".format(extension),
					QMessageBox.Yes | QMessageBox.Discard,
					)
				if box.exec() == QMessageBox.Discard:	return
				else:
					extension = 'py'
			
			if extension in ('py', 'txt'):
				open(self.currentfile, 'w').write(self.script.toPlainText())
			
			self.update_title()
			
	def _save_as(self):
		''' callback for button 'save as' 
			ask the user for a new value for self.currentfile
		'''
		dialog = QFileDialog(self, 'save madcad file', self.currentfile or os.curdir)
		dialog.setAcceptMode(QFileDialog.AcceptSave)
		dialog.exec()
		if dialog.result() == QDialog.Accepted:
			self.currentfile = dialog.selectedFiles()[0]
			self._save()
	
	def _export(self):	pass
	def _screenshot(self):	pass
	
	# END
	# BEGIN --- editing tools ----
				
	def _contentsChange(self, position, removed, added):
		# get the added text
		cursor = QTextCursor(self.script)
		cursor.setPosition(position+added)
		cursor.setPosition(position, cursor.KeepAnchor)
		# transform it to fit the common standards
		newtext = cursor.selectedText().replace('\u2029', '\n')
		# apply change to the interpeter
		self.interpreter.change(position, removed, newtext)
		
		if self.exectarget > position:
			self.exectarget += added - removed
		else:
			self.exectarget = position + added
		
		if self.exectrigger == 2 or self.exectrigger == 1 and '\n' in newtext:
			self.exectarget_changed.emit()
			self.execute()
		else:
			self.execution_label('MODIFIED')
	
	def execute(self):
		''' execute the script until the line exectarget 
			updating the scene and the execution label
		'''
		# place the exec target at the end of line
		cursor = QTextCursor(self.script)
		cursor.setPosition(self.exectarget)
		cursor.movePosition(QTextCursor.EndOfLine)
		self.exectarget = cursor.position()
		
		self.execution_label('RUNNING')
		#print('-- execute script --\n{}\n-- end --'.format(self.interpreter.text))
		try:
			res = self.interpreter.execute(self.exectarget, autobackup=True)
		except InterpreterError as report:
			err = report.args[0]
			#traceback.print_tb(err.__traceback__)
			#print(type(err).__name__, ':', err, err.__traceback__)
			self.showerror(err)
			self.execution_label('<p style="color:#ff5555">FAILED</p>')
		else:
			self.execution_label('<p style="color:#55ff22">COMPUTED</p>')
			used, reused = res
			self.currentenv = self.interpreter.current
			self.neverused |= used
			self.neverused -= reused
			self.updatescript()
			self.executed.emit()
	
	def reexecute(self):
		''' reexecute all the script '''
		self.interpreter.change(0, 0, '')
		self.execute()
		
	def _targettocursor(self):
		# place the exec target at the cursor location
		self.exectarget = self.active_scriptview.editor.textCursor().position()
		self.exectarget_changed.emit()
	
	def showerror(self, err):
		view = self.active_errorview
		if view and not view.keep:
			view.set(err)
		else:
			self.active_errorview = ErrorView(self, err)
			self.active_errorview.show()
			self.views.append(self.active_errorview)
		self.activateWindow()
		
	def edit(self, name):
		obj = self.scene[name]
		if isinstance(obj, vec3):	editor = PointEditor
		elif isinstance(obj, Mesh):	editor = MeshEditor
		else:	return
		try:	
			self.editors[name] = e = editor(self, name)
			self.active_sceneview.scene.sync()
			self.updatescript()
		except EditionError as err:
			print('unable to edit variable', name, ':', err)
		else:
			return e
	
	def finishedit(self, name):
		if name in self.editors:
			self.editors[name].finish()
			del self.editors[name]
			self.updatescene([name])
			self.updatescript()
	
	def selectionbox(self):
		''' return the bounding box of the selection '''
		def selbox(level):
			box = Box(vec3(inf), vec3(-inf))
			for disp in level:
				if disp.selected:
					box.union(disp.box)
				elif isinstance(disp, madcad.rendering.Group):
					sub = selbox(disp.displays.values())
					if not sub.isempty():
						box.union(sub.transform(disp.pose))
			return box
		selbox(self.active_sceneview.scene.displays.values())
	
	def _viewcenter(self):
		box = self.selectionbox() or self.active_sceneview.scene.box()
		self.active_sceneview.center(box.center)
	
	def _viewadjust(self):
		box = self.selectionbox() or self.active_sceneview.scene.box()
		self.active_sceneview.adjust(box)
	
	def _viewlook(self):
		box = self.selectionbox() or self.active_sceneview.scene.box()
		self.active_sceneview.look(box.center)
	
	def _deselectall(self):
		selected = {}
		for grp,sub in self.selection:
			if grp not in selected:	selected[grp] = []
			selected[grp].append(sub)
			
		for g,subs in selected.items():
			for view in self.views:
				if isinstance(view, SceneView):
					for grp,rdr in view.stack:
						if grp == g and hasattr(rdr, 'select'):
							for sub in subs:
								rdr.select(sub, False)
					view.update()
		self.selection.clear()
		self.updatescript()
		
	def _set_current_solid(self):
		#self.active_solid = first(
				#iter_scenetree(self.active_sceneview.scene), 
				#lambda disp: isinstance(disp, Solid.display) and disp.selected,
				#)
		self.active_solid = None
		print()
		for disp in iter_scenetree(self.active_sceneview.scene):
			if disp.selected:	print(disp)
			if isinstance(disp, Solid.display) and disp.selected:
				self.active_solid = disp
				break
		print('current solid', self.active_solid)
	
	def targetcursor(self):
		cursor = self.active_scriptview.editor.textCursor()
		cursor.setPosition(self.exectarget)
		return cursor
		
	def insertexpr(self, text):
		cursor = self.targetcursor()
		cursor.movePosition(QTextCursor.NextWord)
		cursor.movePosition(QTextCursor.PreviousWord, QTextCursor.KeepAnchor)
		prev = cursor.selectedText()
		
		cursor.movePosition(QTextCursor.NextWord)
		cursor.setKeepPositionOnInsert(False)

		if not re.match(r'.*[,\n+\-\*/\=]\s*$', prev):
			cursor.insertText('\n')
		cursor.insertText(text)
		self.exectarget = cursor.position()
		if self.exectrigger:
			self.execute()
	
	def insertstmt(self, text):
		cursor = self.targetcursor()
		cursor.atBlockEnd()
		cursor.setKeepPositionOnInsert(False)
		cursor.insertText(text+'\n')
		self.exectarget = cursor.position()
		if self.exectrigger:
			self.execute()
		
		
	# END
	# BEGIN --- display system ---
	
	''' display rules
		- variables (therefore named values)
			added to scene when selected in the SceneList
			added to scene when never reused by the script (a final value)
		- temporary intermediate values (anonymous, but associated with their line number)
			added to scene when the cursor is on a line of their statement
	'''
		
	def _show_line_numbers(self, enable):
		self.active_scriptview.linenumbers = enable
		self.active_scriptview.update_linenumbers()
	def _enable_line_wrapping(self, enable):
		self.active_scriptview.editor.setWordWrapMode(enable)
	
	def _display_faces(self, enable):
		self.active_sceneview.scene.options['display_faces'] = enable
		self.active_sceneview.scene.touch()
		self.active_sceneview.update()
	def _display_groups(self, enable):
		self.active_sceneview.scene.options['display_groups'] = enable
		self.active_sceneview.scene.touch()
		self.active_sceneview.update()
	def _display_wire(self, enable):
		self.active_sceneview.scene.options['display_wire'] = enable
		self.active_sceneview.scene.touch()
		self.active_sceneview.update()
	def _display_points(self, enable):
		self.active_sceneview.scene.options['display_points'] = enable
		self.active_sceneview.scene.touch()
		self.active_sceneview.update()
	def _display_grid(self, enable):
		self.active_sceneview.scene.options['display_grid'] = enable
		self.active_sceneview.scene.touch()
		self.active_sceneview.update()
	
	def execution_label(self, label):
		for view in self.views:
			if isinstance(view, ScriptView):
				view.label_execution.setText(label)
	
	def cursorat(self, position):
		''' notice the main that the cursur is at the given (line,column) '''
		#if not self.trytrick(position):
		self.showtemps(position)
		
	def objattext(self, position):
		mscore = inf
		mname = None
		for name,interval in self.interpreter.locations.items():
			start,end = astinterval(interval)
			if start <= position and position <= end:
				score = end-start
				if score < mscore:
					mscore = score
					mname = name
		if mname:	
			return mname
	
	def showtemps(self, position):
		''' display temporary values for the given cursor location '''
		name = self.objattext(position)
		if name:
			self.displayzones = [astinterval(self.interpreter.locations[name])]
		else:
			self.displayzones = []
		for scene in self.scenes:
			scene.sync()
		self.updatescript()
	
	def addtemp(self, obj):	
		''' add a variable to the scene, that will be removed at next execution
			a new unused temp name is used and returned
		'''
		i = 0
		while True:
			name = 'temp{}'.format(i)
			if name not in self.scene:	break
			i += 1
		self.interpreter.current[name] = self.scene[name] = obj
		return name
	
	def updatescript(self):
		zonehighlight = QColor(40, 200, 240, 60)
		selectionhighlight = QColor(100, 200, 40, 80)
		editionhighlight = QColor(255, 200, 50, 60)
		background = QColor(0,0,0)
	
		cursor = QTextCursor(self.script)
		extra = []
		for zs,ze in self.displayzones:
			cursor.setPosition(zs)
			cursor.setPosition(ze, QTextCursor.KeepAnchor)
			extra.append(extraselection(cursor, charformat(background=zonehighlight)))
		
		seen = set()
		for selected,sub in self.selection:
			if selected not in seen and selected in self.interpreter.locations:
				seen.add(selected)
				zone = self.interpreter.locations[selected]
				cursor.setPosition(zone.position)
				cursor.setPosition(zone.end_position, QTextCursor.KeepAnchor)
				extra.append(extraselection(cursor, charformat(background=selectionhighlight)))
		for edited in self.editors:
			zone = self.interpreter.locations[edited]
			cursor.setPosition(zone.position)
			cursor.setPosition(zone.end_position, QTextCursor.KeepAnchor)
			extra.append(extraselection(cursor, charformat(background=editionhighlight)))
		
		for view in self.views:
			if isinstance(view, ScriptView):
				view.editor.setExtraSelections(extra)
	
	
	# END
	
