'''	Definition of the mainframe of the MADCAD gui

	Architecture
	============
	
		At contrary to usual data structures, in a gui and using Qt events in particular, the user will is received by the bottom nodes of the data tree: the user is not controling the top classes but interacting with the bottom unit objects.
		Therefore the data access is inverted allow the user will to be better used: the unit classes are referencing their parents and manage their content.
		
		More specifically the gui is centered around a main non-graphical class Madcad, which most of the top widgets are referencing and exploiting as a shared ressource. The same is true for subwidgets of these top widgets.
'''


from PyQt5.QtCore import (
		Qt, QSize, QRect, QPoint, QPointF,
		QEvent, pyqtSignal, QObject, 
		QStringListModel,
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
from madcad.rendering import Display, Group, Turntable, Orbit, Displayable
import madcad.settings

from .common import *
from .interpreter import Interpreter, InterpreterError, astinterval, astatpos
from .scriptview import ScriptView
from .sceneview import Scene, SceneView, SceneList, scene_unroll
from .errorview import ErrorView
from .detailview import DetailView
from .tricks import PointEditor, EditionError
from .tooling import ToolAssist, ToolError
from . import tooling
from . import settings

from copy import deepcopy, copy
from nprint import nprint, nformat
import ast, traceback
import os, sys
import re


version = '0.5'


class Madcad(QObject):
	'''
		Main class of the madcad gui. It represents the gui software itself and is meant to be used as a shared ressource across all widgets.
	'''
	# madcad signals
	executed = pyqtSignal()
	exectarget_changed = pyqtSignal()
	file_changed = pyqtSignal()
	active_changed = pyqtSignal()
	
	def __init__(self):
		super().__init__()
		
		# madcad state
		self.currentfile = None
		self.currentexport = None
		
		self.active_sceneview = None
		self.active_scriptview = None
		self.active_errorview = None
		self.active_solid = None
		
		self.exectrigger = 1
		self.exectarget = 0
		self.editors = {}
		self.details = {}
		self.hiddens = set()
		self.displayzones = {}
		self.neverused = set()
		
		# madcad ressources (and widgets)
		self.standardcameras = {
			'-Z': fquat(fvec3(0, 0, 0)),
			'+Z': fquat(fvec3(pi, 0, 0)),
			'-X': fquat(fvec3(pi/2, 0, 0)),
			'+X': fquat(fvec3(pi/2, 0, pi)),
			'-Y': fquat(fvec3(pi/2, 0, -pi/2)),
			'+Y': fquat(fvec3(pi/2, 0, pi/2)),
			}
		
		# madcad widgets
		self.script = QTextDocument(self)
		self.script.setDocumentLayout(QPlainTextDocumentLayout(self.script))
		self.script.contentsChange.connect(self._contentsChange)
		self.scenesmenu = SceneList(self)
		self.interpreter = Interpreter()
		
		self.scenes = []	# objets a afficher sur les View
		self.views = []		# widgets d'affichage (textview, sceneview, graphicview, ...)
		self.assist = ToolAssist(self)
		self.mainwindow = None
		
		self.startup()
	
	def close(self):
		# close all the subwindows
		for view in self.views:
			view.close()
		if self.mainwindow:	self.mainwindow.close()

	def startup(self):
		''' set madcad in the startup state (software openning state) '''
		# create or load config
		if madcad.settings.display['system_theme']:
			madcad.settings.use_qt_colors()
		settings.install()
		madcad.settings.install()
		try:	settings.load()
		except:	settings.clean()
		# load startup file
		cursor = QTextCursor(self.script)
		cursor.insertText(open(settings.locations['startup'], 'r').read())

	
	def createtool(self, name, procedure, icon=None, shortcut=None):
		''' create a QAction for the main class, with the given generator procedure '''
		action = QAction(name, self)
		if shortcut:	action.setShortcut(shortcut)
		if icon:		action.setIcon(QIcon.fromTheme(icon))
		
		# generator packing the given procedure to handle exceptions
		def capsule():
			self.assist.generator = gen = procedure(self)
			self.assist.tool(name)
			self.assist.info('')
			try:
				yield from gen
			except ToolError as err:
				self.assist.info('<b style="color:#ff5555">{}</b>'.format(err))
			except Exception as err:
				traceback.print_exception(type(err), err, err.__traceback__)
				self.assist.info('<b style="color:#ff5555">internal error, check console</b>')
				self.assist.info('internal error')
			else:
				if self.exectrigger:	self.execute()
				else:	self.active_sceneview.update()
				self.assist.tool('')
				self.assist.info('')
		
		# button callback
		def callback():
			gen = capsule()
			# tools can run in one-sot
			try:	next(gen)
			except StopIteration:	return
			# or ask for more interactions
			scene = self.active_sceneview.scene
			for view in self.views:
				if not isinstance(view, SceneView) or view.scene is not scene:
					continue
				def tool(evt, view=view):
					try:	gen.send(evt)
					except StopIteration:	
						view.tool.remove(tool)
					else:
						view.scene.touch()
				view.tool.append(tool)
		
		action.triggered.connect(callback)
		
		return action

	def createaction(self, name, procedure, icon=None, shortcut=None):
		''' create a QAction for the main class, with a one-shot procedure '''
		action = QAction(name, self)
		if shortcut:	action.setShortcut(shortcut)
		if icon:		action.setIcon(QIcon.fromTheme(icon))
		
		# simple on-shot callback
		def callback():
			try:				
				procedure(self)
			except ToolError as err:	
				self.assist.tool(name)
				self.assist.info('<b style="color:#ff5555">{}</b>'.format(err))
			else:
				if self.exectrigger:	self.execute()
				else:	self.active_sceneview.update()
		action.triggered.connect(callback)
		
		return action
	
	
	# END
	# BEGIN --- file management system ---
	
	def _open(self):
		''' callback for the button 'open'
			ask the user for a new file and then call self.open_file(filename)
		'''
		filename = QFileDialog.getOpenFileName(self.mainwindow, 'open madcad file', 
							os.curdir, 
							'madcad files (*.py *.mc);;text files (*.txt)',
							)[0]
		if filename:
			self.open_file(filename)
	
	def open_file(self, filename):
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
		
		filename = os.path.abspath(filename)
		os.chdir(os.path.split(filename)[0])
		self.currentfile = filename
		if extension in ('py', 'txt'):
			self.script.clear()
			QTextCursor(self.script).insertText(open(filename, 'r').read())
		
		self.script.setModified(False)
		self.file_changed.emit()
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
			
			self.script.setModified(False)
			self.file_changed.emit()
			
	def _save_as(self):
		''' callback for button 'save as' 
			ask the user for a new value for self.currentfile
		'''
		dialog = QFileDialog(self.mainwindow, 'save madcad file', self.currentfile or os.curdir)
		dialog.setAcceptMode(QFileDialog.AcceptSave)
		dialog.exec()
		if dialog.result() == QDialog.Accepted:
			self.currentfile = dialog.selectedFiles()[0]
			self._save()
	
	def _export(self):	pass
	def _screenshot(self):	pass
	
	def _open_uimadcad_settings(self):
		open_file_external(settings.locations['uisettings'])
	
	def _open_pymadcad_settings(self):
		open_file_external(settings.locations['pysettings'])
	
	def _open_startup_file(self):
		open_file_external(settings.locations['startup'])
	
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
			self.exectarget = position + added - removed
		self.exectarget_changed.emit()
		
		if self.exectrigger == 2 or self.exectrigger == 1 and '\n' in newtext:
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
			self.update_endzone()
			self.updatescript()
			self.hideerror()
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
		if self.mainwindow:
			self.mainwindow.activateWindow()
	
	def hideerror(self):
		view = self.active_errorview
		if view and not view.keep:
			view.hide()
		
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
			
	
	def _viewcenter(self):
		scene = self.active_sceneview.scene
		box = scene.selectionbox() or scene.box()
		self.active_sceneview.center(box.center)
	
	def _viewadjust(self):
		scene = self.active_sceneview.scene
		box = scene.selectionbox() or scene.box()
		self.active_sceneview.adjust(box)
	
	def _viewlook(self):
		scene = self.active_sceneview.scene
		box = scene.selectionbox() or scene.box()
		self.active_sceneview.look(box.center)
	
	def targetcursor(self):
		cursor = self.active_scriptview.editor.textCursor()
		cursor.setPosition(self.exectarget)
		return cursor
		
	def insertexpr(self, text, format=True):
		# indentation
		cursor = self.active_scriptview.editor.textCursor()
		cursor.movePosition(QTextCursor.StartOfLine, QTextCursor.KeepAnchor)
		line = cursor.selectedText()
		cursor.clearSelection()
		cursor.movePosition(QTextCursor.NextWord, QTextCursor.KeepAnchor)
		indent = cursor.selectedText()
		if not indent.isspace():	indent = ''
		newline = len(line) > 30 or line and not (line.endswith(',') or line.isspace())
		
		# put cursor to target line
		cursor = self.active_scriptview.editor.textCursor()
		cursor.setKeepPositionOnInsert(False)
		cursor.beginEditBlock()
		# integration
		if newline:
			cursor.insertText('\n'+indent)
		# insertion
		cursor.insertText((nformat(text.replace('dvec', 'vec')) if format else text).replace('\n', '\n'+indent))
		cursor.endEditBlock()
	
	def insertstmt(self, text):
		# check if there is already something on the line
		cursor = self.active_scriptview.editor.textCursor()
		cursor.movePosition(QTextCursor.StartOfLine, QTextCursor.KeepAnchor)
		newline = not cursor.selectedText().isspace()
		# indentation
		cursor.clearSelection()
		cursor.movePosition(QTextCursor.NextWord, QTextCursor.KeepAnchor)
		indent = cursor.selectedText()
		if not indent.isspace():	indent = ''
		
		# put cursor to target line
		cursor = self.active_scriptview.editor.textCursor()
		cursor.setKeepPositionOnInsert(False)
		cursor.beginEditBlock()
		# integration
		if newline:
			cursor.insertText('\n'+indent)
		# insertion
		cursor.insertText((text.replace('dvec', 'vec')+'\n').replace('\n', '\n'+indent))
		cursor.endEditBlock()
		
		
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
	
	def addtemp(self, obj):	
		''' add a variable to the scene, that will be removed at next execution
			a new unused temp name is used and returned
		'''
		env = self.interpreter.current
		i = 0
		while True:
			name = 'temp{}'.format(i)
			if name not in env:	break
			i += 1
		env[name] = obj
		return name
		
	def posvar(self, position):
		mscore = inf
		mname = None
		for name,interval in self.interpreter.locations.items():
			start,end = astinterval(interval)
			if start <= position and position <= end:
				score = end-start
				if score < mscore:
					mscore = score
					mname = name
		return mname
	
	def updatescript(self):
		zonehighlight = QColor(40, 200, 240, 60)
		selectionhighlight = QColor(100, 200, 40, 80)
		editionhighlight = QColor(255, 200, 50, 60)
		it = self.interpreter
	
		cursor = QTextCursor(self.script)
		extra = []
		for zs,ze in self.displayzones.values():
			cursor.setPosition(zs)
			cursor.setPosition(ze, QTextCursor.KeepAnchor)
			extra.append(extraselection(cursor, charformat(background=zonehighlight)))
		
		if self.active_sceneview:
			seen = set()
			for obj in scene_unroll(self.active_sceneview.scene):
				if not hasattr(obj, 'source'):	continue
				i = id(obj.source)
				if (obj.selected and obj.source 
				and i not in seen 
				and	i in it.ids):
					seen.add(i)
					zone = it.locations[it.ids[i]]
					cursor.setPosition(zone.position)
					cursor.setPosition(zone.end_position, QTextCursor.KeepAnchor)
					extra.append(extraselection(cursor, charformat(background=selectionhighlight)))
		
		for edited in self.editors:
			zone = it.locations[edited]
			cursor.setPosition(zone.position)
			cursor.setPosition(zone.end_position, QTextCursor.KeepAnchor)
			extra.append(extraselection(cursor, charformat(background=editionhighlight)))
		
		for view in self.views:
			if isinstance(view, ScriptView):
				view.editor.setExtraSelections(extra)
	
	def update_endzone(self):
		i = astatpos(self.interpreter.ast, self.exectarget)
		if i < len(self.interpreter.ast.body):
			around = self.interpreter.ast.body[i]
			self.displayzones['aroundtarget'] = around.position, around.end_position
		else:
			self.displayzones.pop('aroundtarget', None)
	
	# END
	

def scene_unroll(obj):
	for disp in obj.displays.values():
		yield disp
		if isinstance(disp, Group):
			yield from scene_unroll(disp)		

def open_file_external(file):
	if 'linux' in sys.platform:
		os.system('xdg-open {}'.format(file))
	elif 'win' in sys.platform:
		os.system('start {}'.format(file))
	else:
		raise EnvironmentError('unable to open a textfile on platform {}'.format(os.platform))

class MainWindow(QMainWindow):
	''' The main window of the gui. 
		Only here to organize the other top-level widgets
	'''
	
	# signals
	exectarget_changed = pyqtSignal()
	executed = pyqtSignal()
	
	# BEGIN --- paneling and initialization ---
	
	def __init__(self, main, parent=None):
		super().__init__(parent)
		# window setup
		self.setWindowRole('madcad')
		self.setWindowIcon(QIcon.fromTheme('madcad'))
		self.setMinimumSize(700,300)
		self.setDockNestingEnabled(True)
		
		self.main = main
		self.main.mainwindow = self
		
		main.script.modificationChanged.connect(self.setWindowModified)
		main.file_changed.connect(self._file_changed)
		self._create_menus()
		tooling.create_toolbars(self.main, self)
		self._file_changed()
		
		# insert components to docker
		self.addDockWidget(Qt.LeftDockWidgetArea, dock(ScriptView(main), 'script view'))
		self.addDockWidget(Qt.RightDockWidgetArea, dock(SceneView(main), 'scene view'))
		self.addDockWidget(Qt.LeftDockWidgetArea, dock(self.main.assist, 'tool assist'))
		
		# use state to get the proper layout until we have a proper state backup
		self.restoreState(b'\x00\x00\x00\xff\x00\x00\x00\x00\xfd\x00\x00\x00\x02\x00\x00\x00\x00\x00\x00\x01q\x00\x00\x02+\xfc\x02\x00\x00\x00\x03\xfb\xff\xff\xff\xff\x01\x00\x00\x00\x1c\x00\x00\x02+\x00\x00\x00\x87\x01\x00\x00\x03\xfb\xff\xff\xff\xff\x00\x00\x00\x01\x8e\x00\x00\x00\xb9\x00\x00\x00:\x01\x00\x00\x03\xfb\xff\xff\xff\xff\x00\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00z\x01\x00\x00\x03\x00\x00\x00\x01\x00\x00\x02:\x00\x00\x02+\xfc\x02\x00\x00\x00\x01\xfb\xff\xff\xff\xff\x01\x00\x00\x00\x1c\x00\x00\x02+\x00\x00\x000\x01\x00\x00\x03\x00\x00\x00\x00\x00\x00\x02+\x00\x00\x00\x04\x00\x00\x00\x04\x00\x00\x00\x08\x00\x00\x00\x08\xfc\x00\x00\x00\x03\x00\x00\x00\x00\x00\x00\x00\x02\xff\xff\xff\xff\x03\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\x00\x00\x00\x00\x00\xff\xff\xff\xff\x03\x00\x00\x014\x00\x00\x00L\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x03\xff\xff\xff\xff\x03\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\x00\x00\x00\x00\x00\xff\xff\xff\xff\x03\x00\x00\x00\xda\xff\xff\xff\xff\x00\x00\x00\x00\x00\x00\x00\x00\xff\xff\xff\xff\x03\x00\x00\x01,\x00\x00\x00d\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x02\x00\x00\x00\x00')
	
	
	def closeEvent(self, evt):
		self.main.close()
		evt.accept()
		
	def _file_changed(self):
		self.setWindowFilePath(self.main.currentfile or '')
	
	def _create_menus(self):
		main = self.main
		menubar = self.menuBar()
		menu = menubar.addMenu('&File')
		menu.addAction(QIcon.fromTheme('document-open'), 'open', main._open, QKeySequence('Ctrl+O'))
		menu.addAction(QIcon.fromTheme('document-save'), 'save', main._save, QKeySequence('Ctrl+S'))
		menu.addAction(QIcon.fromTheme('document-save-as'), 'save as', main._save_as, QKeySequence('Ctrl+Shift+S'))
		menu.addAction(QIcon.fromTheme('emblem-shared'), 'export +', main._export, QKeySequence('Ctrl+E'))
		menu.addAction(QIcon.fromTheme('insert-image'), 'screenshot +', main._screenshot, QKeySequence('Ctrl+I'))
		menu.addSeparator()
		menu.addAction(QIcon.fromTheme('preferences-other'), 'interface settings', main._open_uimadcad_settings)
		menu.addAction(QIcon.fromTheme('text-x-generic'), 'pymadcad settings', main._open_pymadcad_settings)
		menu.addAction(QIcon.fromTheme('text-x-generic'), 'startup file', main._open_startup_file)
		
		menu = menubar.addMenu('&Edit')
		menu.addAction(QIcon.fromTheme('edit-undo'), 'undo', main.script.undo, QKeySequence('Ctrl+Z'))
		menu.addAction(QIcon.fromTheme('edit-redo'), 'redo', main.script.redo, QKeySequence('Ctrl+Shift+Z'))
		menu.addAction(QIcon.fromTheme('media-playback-start'), 'execute', main.execute, QKeySequence('Ctrl+Return'))
		menu.addAction(QIcon.fromTheme('view-refresh'), 'reexecute all', main.reexecute, QKeySequence('Ctrl+Shift+Return'))
		menu.addAction(QIcon.fromTheme('go-bottom'), 'target to cursor', main._targettocursor, QKeySequence('Ctrl+T'))
		menu.addSeparator()
		menu.addAction(QIcon.fromTheme('format-indent-more'), 'disable line +')
		menu.addAction(QIcon.fromTheme('format-indent-less'), 'enable line +')
		menu.addAction('disable line dependencies +')
		menu.addSeparator()
		menu.addAction(main.createaction('rename object', tooling.act_rename, shortcut=QKeySequence('F2')))
		menu.addSeparator()
		menu.addAction(main.createaction('deselect all', tooling.deselectall, 'edit-select-all', shortcut=QKeySequence('Ctrl+A')))
		
		menu = menubar.addMenu('&View')
		menu.addAction(QAction('display navigation controls +', main, checkable=True))
		menu.addSeparator()
		menu.addAction(QIcon.fromTheme('image-x-generic'), 'new 3D view', 
			lambda: self.addDockWidget(Qt.RightDockWidgetArea, dock(SceneView(main), 'scene view')))
		menu.addAction(QIcon.fromTheme('text-x-script'), 'new text view', 
			lambda: self.addDockWidget(Qt.RightDockWidgetArea, dock(ScriptView(main), 'build script')))
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
		menu.addAction('save window layout', lambda: print(main.saveState()))
		
		menu = menubar.addMenu('&Scene')
		action = QAction('display points', main, checkable=True, shortcut=QKeySequence('Shift+P'))
		action.setChecked(madcad.settings.scene['display_points'])
		action.toggled.connect(main._display_points)
		menu.addAction(action)
		action = QAction('display wire', main, checkable=True, shortcut=QKeySequence('Shift+W'))
		action.setChecked(madcad.settings.scene['display_wire'])
		action.toggled.connect(main._display_wire)
		menu.addAction(action)
		action = QAction('display groups', main, checkable=True, shortcut=QKeySequence('Shift+G'))
		action.setChecked(madcad.settings.scene['display_groups'])
		action.toggled.connect(main._display_groups)
		menu.addAction(action)
		action = QAction('display faces', main, checkable=True, shortcut=QKeySequence('Shift+F'))
		action.setChecked(madcad.settings.scene['display_faces'])
		action.toggled.connect(main._display_faces)
		menu.addAction(action)
		action = QAction('display grid', main, checkable=True, shortcut=QKeySequence('Shift+B'))
		action.setChecked(madcad.settings.scene['display_grid'])
		action.toggled.connect(main._display_grid)
		menu.addAction(action)
		action = QAction('display annotations +', main, checkable=True, shortcut=QKeySequence('Shift+D'))
		action.setChecked(madcad.settings.scene['display_annotations'])
		menu.addAction(action)
		action = QAction('display all variables +', main, checkable=True, shortcut=QKeySequence('Shift+V'))
		menu.addAction(action)
		menu.addSeparator()
		menu.addAction('center on object', main._viewcenter, shortcut=QKeySequence('Shift+C'))
		menu.addAction('adjust to object', main._viewadjust, shortcut=QKeySequence('Shift+A'))
		menu.addAction('look to object', main._viewlook, shortcut=QKeySequence('Shift+L'))
		menu.addSeparator()
		
		
		def standardcamera(name):
			orient = self.main.standardcameras[name]
			nav = self.main.active_sceneview.navigation
			if isinstance(nav, Turntable):
				nav.yaw = roll(orient)
				nav.pitch = pi/2 - pitch(orient)
			elif isinstance(nav, Orbit):
				nav.orient = orient
			else:
				raise TypeError('navigation type {} is not supported for standardcameras'.format(type(nav)))
			self.main.active_sceneview.update()
		
		cameras = menu.addMenu("standard cameras")
		cameras.addAction('-Z &top',	lambda: standardcamera('-Z'), shortcut=QKeySequence('Y'))
		cameras.addAction('+Z &bottom',	lambda: standardcamera('+Z'), shortcut=QKeySequence('Shift+Y'))
		cameras.addAction('+Y &front',	lambda: standardcamera('-X'), shortcut=QKeySequence('U'))
		cameras.addAction('-Y &back',	lambda: standardcamera('+X'), shortcut=QKeySequence('Shift+U'))
		cameras.addAction('-X &right',	lambda: standardcamera('-Y'), shortcut=QKeySequence('I'))
		cameras.addAction('+X &left',	lambda: standardcamera('+Y'), shortcut=QKeySequence('Shift+I'))
		
		anims = menu.addMenu('camera animations')
		anims.addAction('rotate &world +')
		anims.addAction('rotate &local +')
		anims.addAction('rotate &random +')
		anims.addAction('cyclic &adapt +')
		
		menu.addSeparator()
		
		menu.addAction(main.createaction('set active solid', tooling.set_active_solid, shortcut=QKeySequence('Shift+S')))
		menu.addAction('explode objects +')
		
		
		menu = menubar.addMenu('Scrip&t')
		action = QAction('show line numbers', main, checkable=True, shortcut=QKeySequence('F11'))
		action.toggled.connect(main._show_line_numbers)
		menu.addAction(action)
		action = QAction('enable line wrapping', main, checkable=True, shortcut=QKeySequence('F10'))
		action.toggled.connect(main._enable_line_wrapping)
		menu.addAction(action)
		action = QAction('scroll on selected object +', main, checkable=True)
		#action.toggled.connect(main._enable_center_on_select)	# TODO when settings will be added
		menu.addAction(action)
		menu.addAction(QIcon.fromTheme('edit-find'), 'find +', lambda: None, shortcut=QKeySequence('Ctrl+F'))
		menu.addAction(QIcon.fromTheme('edit-find-replace'), 'replace +', lambda: None, shortcut=QKeySequence('Ctrl+R'))
		
		menu = menubar.addMenu('&Plot')
		menu.addAction(QAction('display curve labels +', main, checkable=True))
		menu.addAction(QAction('display curve points +', main, checkable=True))
		menu.addAction(QAction('display axis ticks +', main, checkable=True))
		menu.addAction(QAction('display grid +', main, checkable=True))
		menu.addSeparator()
		menu.addAction('adapt to curve +')
		menu.addAction('zoom on zone +')
		menu.addAction('stick to zero +')
		menu.addAction('set ratio to unit +')
		
		menu = menubar.addMenu('&Node')
		menu.addAction(QAction('display defaults +', main, checkable=True))
		menu.addAction(QAction('display borders +', main, checkable=True))
		menu.addAction(QAction('display grid +', main, checkable=True))
		menu.addAction(QAction('simplify with icons +', main, checkable=True))
		link = menu.addMenu('link shape')
		link.addAction('cubic +')
		link.addAction('straight +')
		link.addAction('bezier +')
		menu.addSeparator()
		menu.addAction('center on selection +')
		menu.addAction('adapt to selection +')
	
	
