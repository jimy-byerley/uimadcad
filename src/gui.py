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

from madcad.mathutils import vec3, fvec3, Box, boundingbox, inf, length
from madcad.mesh import Mesh, Wire
from madcad import displayable, isconstraint, isprimitive
from madcad.annotations import annotations
import madcad.settings

from common import *
from interpreter import Interpreter, InterpreterError, astinterval
from scriptview import ScriptView
from sceneview import SceneView, SceneList
from errorview import ErrorView
from tricks import PointEditor, EditionError
import tooling

from copy import deepcopy, copy
from nprint import nprint
import ast
import traceback
import os


version = '0.3'


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
		self.setWindowIcon(QIcon.fromTheme('madcad-logo'))
		self.setMinimumSize(500,300)
				
		# main components
		self.script = QTextDocument(self)
		self.script.setDocumentLayout(QPlainTextDocumentLayout(self.script))
		self.script.contentsChange.connect(self._contentsChange)
		self.interpreter = Interpreter()
		self.scenelist = SceneList(self)
		self.assist = tooling.ToolAssist(self)
		self.forceddisplays = set()	# choix des variables a afficher
		self.hiddens = set()
		self.displayzones = []
		self.neverused = set()
		
		self.scene = {}	# objets a afficher sur les View
		self.views = []
		self.active_sceneview = None
		self.active_scriptview = None
		self.active_errorview = None
		self.selection = set()
		self.exectrigger = 1
		self.exectarget = 0
		self.editors = {}
		
		self.currentfile = None
		self.currentexport = None
		
		# insert components to docker
		self.setDockNestingEnabled(True)
		self.addDockWidget(Qt.LeftDockWidgetArea, dock(ScriptView(self), 'script view'))
		self.addDockWidget(Qt.RightDockWidgetArea, dock(SceneView(self), 'scene view'))
		self.scenelistdock = dock(SceneList(self), 'forced variables display')
		self.addDockWidget(Qt.LeftDockWidgetArea, self.scenelistdock)
		self.addDockWidget(Qt.LeftDockWidgetArea, dock(self.assist, 'tool assist'))
		#self.addDockWidget(Qt.BottomDockWidgetArea, dock(self.console, 'console'))
		self.resizeDocks([self.scenelistdock], [0], Qt.Horizontal)	# Qt 5.10 hack to avoid issue of docks reseting their size after user set it
		
		self.init_menus()
		self.init_toolbars()
		self.update_title()
		
		cursor = QTextCursor(self.script)
		cursor.insertText('from madcad import *\n\n')
	
	def init_menus(self):
		menu = self.menuBar().addMenu('File')
		menu.addAction(QIcon.fromTheme('document-open'), 'open', self._open, QKeySequence('Ctrl+O'))
		menu.addAction(QIcon.fromTheme('document-save'), 'save', self._save, QKeySequence('Ctrl+S'))
		menu.addAction(QIcon.fromTheme('document-save-as'), 'save as', self._save_as, QKeySequence('Ctrl+Shift+S'))
		menu.addAction(QIcon.fromTheme('emblem-shared'), 'export +', self._export, QKeySequence('Ctrl+E'))
		menu.addAction(QIcon.fromTheme('insert-image'), 'screenshot +', self._screenshot, QKeySequence('Ctrl+I'))
		menu.addSeparator()
		menu.addAction(QIcon.fromTheme('emblem-system'), 'settings +')
		
		menu = self.menuBar().addMenu('Edit')
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
		menu.addAction('rename object +')
		menu.addSeparator()
		menu.addAction('deselect all', self._deselectall, QKeySequence('Ctrl+A'))
		
		menu = self.menuBar().addMenu('View')
		menu.addAction('new 3D view', self.new_sceneview)
		menu.addAction('freeze view content', 
			lambda: self.active_sceneview.freeze())
		menu.addSeparator()
		menu.addAction('new text view', 
			lambda: self.addDockWidget(Qt.RightDockWidgetArea, dock(ScriptView(self), 'build script')))
		menu.addSeparator()
		action = self.scenelistdock.toggleViewAction()
		action.setShortcut(QKeySequence('Shift+D'))
		menu.addAction(action)
		menu.addSeparator()
		menu.addAction('harvest toolbars on window side +')
		menu.addAction('take floating toolbars to mouse +')
		
		menu = self.menuBar().addMenu('Scene')
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
		menu.addSeparator()
		menu.addAction('center on object', self._centerselection, shortcut=QKeySequence('Shift+C'))
		menu.addAction('adapt to object', self._lookselection, shortcut=QKeySequence('Shift+A'))
		menu.addSeparator()
		menu.addAction('top +')
		menu.addAction('bottom +')
		menu.addAction('front +')
		menu.addAction('back +')
		menu.addAction('right +')
		menu.addAction('left +')
		menu.addSeparator()
		menu.addAction('explode objects +')
		
		
		menu = self.menuBar().addMenu('Script')
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
	
	def init_toolbars_(self):
		tools = self.addToolBar('creation')
		tools.addAction(QIcon.fromTheme('madcad-import'), 'import', 	lambda: tooling.tool_import(self))
		tools.addAction('select')
		tools.addAction(QIcon.fromTheme('madcad-solid'), 'solid')
		tools.addAction(QIcon.fromTheme('madcad-meshing'), 'manual meshing')
		tools.addAction(QIcon.fromTheme('madcad-point'), 'point', 		lambda: tooling.tool_point(self))
		tools.addAction(QIcon.fromTheme('madcad-segment'), 'segment', 	lambda: tooling.tool_segment(self))
		tools.addAction(QIcon.fromTheme('madcad-arc'), 'arc', 			lambda: tooling.tool_arcthrough(self))
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
	
	def init_toolbars(self):
		tooling.init_toolbars(self)
	
	def new_sceneview(self):
		''' open a new sceneview floating at the center of the main window '''
		new = SceneView(self)
		if self.active_sceneview:
			new.manipulator = deepcopy(self.active_sceneview.manipulator)
		win = dock(new, 'scene view')
		self.addDockWidget(Qt.RightDockWidgetArea, win)
		win.setFloating(True)
		zone = self.geometry().center()
		size = QPoint(300,300)
		win.setGeometry(QRect(zone-size/2, zone+size/2))
	
	def update_title(self):
		if self.currentfile:
			filename = self.currentfile[self.currentfile.rfind(os.sep)+1:]
			self.setWindowTitle('{} - ̶-  madcad v{}'.format(filename, version))
		else:
			self.setWindowTitle('madcad v{}'.format(version))
	
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
		
		self.currentfile = filename
		if extension in ('py', 'txt'):
			self.script.clear()
			QTextCursor(self.script).insertText(open(filename, 'r').read())
		
		os.chdir(os.path.split(os.path.abspath(filename))[0])
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
			self.execution_label('MODIFIED  (Ctrl+Return to execute)')
	
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
			#print(type(err).__name__, ':', err, err.__traceback__)
			#traceback.print_tb(err.__traceback__)
			self.showerror(err)
			self.execution_label('<p style="color:#ff5555">FAILED</p>')
		else:
			self.execution_label('<p style="color:#55ff22">COMPUTED</p>')
			used, reused = res
			self.currentenv = self.interpreter.current
			self.neverused |= used
			self.neverused -= reused
			self.updatescene(used)
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
			self.updatescene([name])
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
		
	
	def select(self, sel, state=None):
		''' change the selection state of the given key (scene key, sub ident) 
			register the change in self.selection, and update the scene views
		'''
		# set the selection state
		if state is None:	state = sel not in self.selection
		if state:	self.selection.add(sel)
		else:		self.selection.discard(sel)
		
		# set the selection state for renderers
		for view in self.views:
			if isinstance(view, SceneView):
				for grp,rdr in view.stack:
					if grp == sel[0] and hasattr(rdr, 'select'):
						rdr.select(sel[1], state)
				view.update()
		
		# move the cursor position
		#oldcursor = self.active_scriptview.editor.textCursor()
		#cursor = QTextCursor(oldcursor)
		#cursor.setPosition(self.interpreter.locations[sel[0]].position)
		#self.active_scriptview.editor.setTextCursor(cursor)
		#self.active_scriptview.editor.ensureCursorVisible()
		#self.active_scriptview.editor.setTextCursor(oldcursor)
		
		# highlight zones
		self.updatescript()
	
	def selectionbox(self):
		''' return the bounding box of the selection '''
		box = Box(vec3(inf), vec3(-inf))
		for key,sub in self.selection:
			obj = self.scene.get(key)
			if hasattr(obj, 'group'):
				obj = obj.group(sub)
				obj.strippoints()
			box.union(boundingbox(obj))
		return box
	
	def _centerselection(self):
		self.active_sceneview.look(self.selectionbox().center)
		self.active_sceneview.update()
	
	def _lookselection(self):
		self.active_sceneview.look(self.selectionbox())
		self.active_sceneview.update()
	
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
	
	def insertexpr(self, text):
		cursor = self.active_scriptview.editor.textCursor()
		cursor.setPosition(self.exectarget)
		cursor.movePosition(QTextCursor.NextWord)
		cursor.setKeepPositionOnInsert(False)
		cursor.insertText(text)
		self.exectarget = cursor.position()
		if self.exectrigger:
			self.execute()
	def insertstmt(self, text):
		cursor = self.active_scriptview.editor.textCursor()
		cursor.setPosition(self.exectarget)
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
		self.active_sceneview.options['display_faces'] = enable
		self.active_sceneview.update()
	def _display_groups(self, enable):
		self.active_sceneview.options['display_groups'] = enable
		self.active_sceneview.update()
	def _display_wire(self, enable):
		self.active_sceneview.options['display_wire'] = enable
		self.active_sceneview.update()
	def _display_points(self, enable):
		self.active_sceneview.options['display_points'] = enable
		self.active_sceneview.update()
	
	def execution_label(self, label):
		for view in self.views:
			if isinstance(view, ScriptView):
				view.label_execution.setText(label)
	
	def syncviews(self, updated):
		''' update all the scene views with the current self.scene '''
		for view in self.views:
			if hasattr(view, 'sync'):
				view.sync(updated)
	
	def cursorat(self, position):
		''' notice the main that the cursur is at the given (line,column) '''
		#if not self.trytrick(position):
		self.showtemps(position)
	
	def updatescene(self, change=()):
		''' update self.scene with the last execution results '''
		# objects selection in env, and already present objs
		newscene = {}
		for name,obj in self.scene.items():
			if not (isinstance(name, str) and name.isidentifier()):
				newscene[name] = obj
		# display objects that are requested by the user, or that are never been used (lastly generated)
		for name,obj in self.interpreter.current.items():
			if displayable(obj) and (	name in self.forceddisplays 
									or	name in self.neverused):
				newscene[name] = obj
		# display objects in the display zones
		for zs,ze in self.displayzones:
			for name,node in self.interpreter.locations.items():
				if name not in newscene:
					ts,te = astinterval(node)
					temp = self.interpreter.current[name]
					if zs <= ts and te <= ze and displayable(temp):
						newscene[name] = temp
		for hidden in self.hiddens:
			if hidden in newscene:	del newscene[hidden]
		
		newscene.update(self.editors)
		
		# change the scene
		update = {'<ANNOTATIONS>'}.union(change)
		self.scene = newscene
		self.scene['<ANNOTATIONS>'] = list(annotations(self.scene))	# TODO: ne pas recalculer toutes les annotations
		# update views
		self.syncviews(update)
	
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
		self.updatescene()
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
		self.interpreter.current[name] = obj
		print('added')
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
			if selected not in seen:
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
	

		


		
		
if __name__ == '__main__':
	import sys
	from PyQt5.QtCore import Qt, QCoreApplication
	from PyQt5.QtWidgets import QApplication
	QCoreApplication.setAttribute(Qt.AA_ShareOpenGLContexts)
	app = QApplication(sys.argv)
	print(QStyleFactory.keys())
	main = Main()
		
	main.show()
	sys.exit(app.exec())
