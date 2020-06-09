from PyQt5.QtCore import (
		Qt, QSize, QRect, QPoint, QPointF,
		QEvent, pyqtSignal,
		)
from PyQt5.QtWidgets import (
		QVBoxLayout, QWidget, QHBoxLayout, QStyleFactory, QSplitter, QSizePolicy, QAction,
		QPlainTextEdit, QPlainTextDocumentLayout, QScrollArea, 
		QPushButton, QLabel, QComboBox,
		QMainWindow, QDockWidget, QFileDialog, QMessageBox, QDialog
		)
from PyQt5.QtGui import (
		QFont, QFontMetrics, 
		QColor, QPalette,
		QIcon, QKeySequence, 
		QTextOption, QTextDocument, QTextCursor,
		QPainter, QPainterPath,
		)

from madcad.mathutils import vec3
from madcad.view import Scene
from madcad import displayable, isconstraint, isprimitive
from madcad.annotations import annotations
import madcad.settings

from editor import Interpreter, InterpreterError
import tricks

from copy import deepcopy, copy
from nprint import nprint
import traceback
import os


version = '0.2'


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
		self.forceddisplays = set()	# choix des variables a afficher
		self.neverused = set()
		
		self.scene = {}	# objets a afficher sur les View
		self.views = []
		self.active_sceneview = None
		self.active_scriptview = None
		self.activetrick = None
		self.selection = []
		self.exectrigger = 1
		self.exectarget = 0
		
		self.currentfile = None
		self.currentexport = None
		
		# insert components to docker
		self.setDockNestingEnabled(True)
		self.addDockWidget(Qt.LeftDockWidgetArea, dock(ScriptView(self), 'script view'))
		self.addDockWidget(Qt.RightDockWidgetArea, dock(SceneView(self), 'scene view'))
		self.scenelistdock = dock(SceneList(self), 'forced variables display')
		self.addDockWidget(Qt.LeftDockWidgetArea, self.scenelistdock)
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
		
		menu = self.menuBar().addMenu('View')
		menu.addAction('new 3D view', self.new_sceneview)
		menu.addAction('freeze view content', 
			lambda: self.active_sceneview.freeze())
		menu.addSeparator()
		menu.addAction('new text view', 
			lambda: self.addDockWidget(Qt.RightDockWidgetArea, dock(ScriptView(self), 'build script')))
		
		menu = self.menuBar().addMenu('Scene')
		menu.addAction('center on object +')
		menu.addAction('adapt to object +',
			lambda: self.activeview.look(self.selection.box()))
		menu.addSeparator()
		menu.addAction('top +')
		menu.addAction('bottom +')
		menu.addAction('front +')
		menu.addAction('back +')
		menu.addAction('right +')
		menu.addAction('left +')
		menu.addSeparator()
		menu.addAction('explode objects +')
		menu.addSeparator()
		action = self.scenelistdock.toggleViewAction()
		action.setShortcut(QKeySequence('Shift+H'))
		menu.addAction(action)
		menu.addSeparator()
		
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
		
		menu = self.menuBar().addMenu('Script')
		action = QAction('show line numbers', self, checkable=True, shortcut=QKeySequence('F11'))
		action.toggled.connect(self._show_line_numbers)
		menu.addAction(action)
		action = QAction('enable line wrapping', self, checkable=True, shortcut=QKeySequence('F10'))
		action.toggled.connect(self._enable_line_wrapping)
		menu.addAction(action)
		menu.addAction('find +')
		menu.addAction('replace +')
		
	def init_toolbars(self):
		tools = self.addToolBar('creation')
		tools.addAction(QIcon.fromTheme('madcad-import'), 'import')
		tools.addAction('select')
		tools.addAction(QIcon.fromTheme('madcad-solid'), 'solid')
		tools.addAction(QIcon.fromTheme('madcad-meshing'), 'manual meshing')
		tools.addAction(QIcon.fromTheme('madcad-point'), 'point')
		tools.addAction(QIcon.fromTheme('madcad-segment'), 'segment')
		tools.addAction(QIcon.fromTheme('madcad-arc'), 'arc')
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
	
	def new_sceneview(self):
		''' open a new sceneview floating at the center of the main window '''
		new = SceneView(self)
		if self.active_sceneview:
			new.manipulator = deepcopy(self.active_sceneview.manipulator)
		win = dock(new, 'view')
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
	
	def select(self, obji, ident):
		self.selection.append((obji, ident))
		for view in self.views:
			for grp,rdr in view.stack:
				rdr.select(ident)
				
	def _contentsChange(self, position, removed, added):
		# get the added text
		cursor = QTextCursor(self.script)
		cursor.setPosition(position+added)
		endline, _ = cursor_location(cursor)
		cursor.setPosition(position, cursor.KeepAnchor)
		# transform it to fit the common standards
		newtext = cursor.selectedText().replace('\u2029', '\n')
		# apply change to the interpeter
		location = cursor_location(cursor)
		self.interpreter.change(location, removed, newtext)
		
		if self.exectrigger == 1:	self.exectarget = max(endline, self.exectarget)
		elif self.exectrigger == 2:	self.exectarget = max(endline+1, self.exectarget)
		if endline >= self.exectarget:	self.exectarget_changed.emit()
		
		# see if reexecution is needed
		if self.exectrigger == 0:
			reexecute = False
		elif self.exectrigger == 1:
			reexecute = '\n' in newtext
		elif self.exectrigger == 2:
			reexecute = True
		
		# reexecute
		if reexecute:
			self.execute()
		else:
			self.execution_label('MODIFIED  (Ctrl+Return to execute)')
	
	def execute(self):
		''' execute the script until the line exectarget 
			updating the scene and the execution label
		'''
		self.execution_label('RUNNING')
		#print('-- execute script --\n{}\n-- end --'.format(self.interpreter.text()))
		try:
			res = self.interpreter.execute(self.exectarget)
		except InterpreterError as report:
			err = report.args[0]
			print(type(err).__name__, ':', err, err.__traceback__)
			traceback.print_tb(err.__traceback__)
			self.execution_label('<p style="color:#ff5555">FAILED</p>')
		else:
			self.execution_label('<p style="color:#55ff22">COMPUTED</p>')
			returned, env, used, reused = res
			self.currentenv = env
			self.neverused |= set(used)
			self.neverused -= set(reused)
			self.updatescene()
			self.executed.emit()
	
	def reexecute(self):
		''' reexecute all the script '''
		self.interpreter.change((0,0), 0, '')
		self.execute()
		
	def _targettocursor(self):
		self.exectarget = self.active_scriptview.editor.textCursor().blockNumber()+1
		self.exectarget_changed.emit()
		
	def trytrick(self, location):
		''' search for a trick to enable in the current expression '''
		line, column = location
		try:	end = self.interpreter.findexpressionend(line, line+1)
		except:	return
		text = self.interpreter.text((line,0), end)
		for trick in self.texttricks:
			found = trick.format.search(text)
			if found:
				t = trick(self, found)
				t.cursor = QTextCursor(self.script.findBlockByNumber(line))
				t.cursor.movePosition(QTextCursor.NextCharacter, n=found.start())
				t.cursor.movePosition(QTextCursor.NextCharacter, QTextCursor.KeepAnchor, n=found.end()-found.start())
				self.scene['<TRICK>'] = self.activetrick = t
				break
		else:
			self.activetrick = None
			if '<TRICK>' in self.scene:
				del self.scene['<TRICK>']
		self.syncviews(('<TRICK>',))
	
	# declaration of tricks available
	texttricks = [tricks.ControledAxis, tricks.ControledPoint]
		
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
	
	def cursorat(self, location):
		''' notice the main that the cursur is at the given (line,column) '''
		self.showtemps(location)
		self.trytrick(location)
	
	def updatescene(self, change=()):
		''' update self.scene with the last execution results '''
		# objects selection in env, and already present objs
		newscene = []
		for name,obj in self.scene.items():
			if not (isinstance(name, str) and name.isidentifier()):
				newscene.append((name, obj))
		for name,obj in self.currentenv.items():
			if displayable(obj) and (name in self.forceddisplays or name in self.neverused):
				newscene.append((name, obj))
		# change the scene
		update = ['<ANNOTATIONS>']
		for name,obj in newscene:
			if name not in self.scene or self.scene[name] != obj:
				update.append(name)
		self.scene = dict(newscene)
		self.scene['<ANNOTATIONS>'] = list(annotations(self.scene))	# TODO: ne pas recalculer toutes les annotations
		# update views
		self.syncviews(update)
	
	def showtemps(self, location):
		''' display temporary values for the given cursor location '''
		# find current expression's end (based on the cursor location)
		try:	end = self.interpreter.findexpressionend(location[0], location[0]+1)
		except:	return
		# remove old displayed temps
		changed = []
		toremove = []
		for name,obj in self.scene.items():
			if isinstance(name, int):
				toremove.append(name)
		for name in toremove:	del self.scene[name]
		# append temporary values of the expression
		for line in range(location[0], end[0]):
			temp = self.interpreter.results.get(line)
			if displayable(temp):
				self.scene[line] = temp
				changed.append(line)
		# update views
		self.syncviews(changed)
	
	# END
	
		
		

def dock(widget, title, closable=True):
	''' create a QDockWidget '''
	dock = QDockWidget(title)
	dock.setWidget(widget)
	dock.setFeatures(	QDockWidget.DockWidgetMovable
					|	QDockWidget.DockWidgetFloatable
					|	(QDockWidget.DockWidgetClosable if closable else 0)
					)
	dock.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
	return dock

class SceneList(QPlainTextEdit):
	''' text view to specify objects main.currentenv we want to append to main.scene '''
	def __init__(self, main):
		super().__init__()
		self.main = main
		self.document().contentsChange.connect(self._contentsChange)
		margins = self.viewportMargins()
		height = (
			QFontMetrics(self.currentCharFormat().font()).height()
			+ margins.top() + margins.bottom()
			+ 2*self.contentOffset().y()
			)
		self.setMinimumHeight(height)
		self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
	
	def sizeHint(self):
		return self.document().size().toSize()
	
	def _contentsChange(self, item):
		self.updateGeometry()
		self.main.forceddisplays = set(self.toPlainText().split())
		self.main.updatescene()

QEventGLContextChange = 215	# opengl context change event type, not yet defined in PyQt5

class SceneView(Scene):
	''' dockable and reparentable scene view widget, bases on madcad.Scene '''
	def __init__(self, main):
		super().__init__()
		self.main = main
		self.frozen = False
		self.grpidents = {}
		self.initnum = 0
		
		main.views.append(self)
		if not main.active_sceneview:	main.active_sceneview = self
		self.sync()
		
	def focusInEvent(self, event):
		super().focusInEvent(event)
		self.main.active_sceneview = self
	
	def freeze(self):
		self.frozen = True
		parent = self.parent()
		if isinstance(parent, QDockWidget):
			parent.setWindowTitle(parent.windowTitle() + ' - frozen')
	
	def sync(self, updated=()):
		if not self.frozen:
			for key,grp in self.grpidents.items():
				if self.grpidents[key] is not None and (key not in self.main.scene or key in updated):
					#print('remove', key, grp)
					self.remove(grp)
					self.grpidents[key] = None
			for key,obj in self.main.scene.items():
				if key not in self.grpidents or key in updated:
					self.grpidents[key] = self.add(obj)
					#print('added', key, self.grpidents[key])
			self.update()
	
	def closeEvent(self, event):
		for i,view in enumerate(self.main.views):
			if view is self:	
				self.main.views.pop(i)
				return
	
	def close(self):
		self.main.views.remove(self)
		if isinstance(self.parent(), QDockWidget):
			self.main.removeDockWidget(self.parent())
		else:
			super().close()
	
	def mousePressEvent(self, evt):
		self.update()
		if self.runtool(evt):		return
	
		x,y = evt.x(), evt.y()
		b = evt.button()
		# find the navigation current mode
		if b == Qt.LeftButton:
			self.mode = self.modes[self.speckeys]
		elif b == Qt.MiddleButton:
			self.mode = (self.manipulator.rotatestart, self.manipulator.rotating)
		# navigate if a mode is on
		if self.mode[0]:
			self.mouse_clicked = (x,y)	# movement origin
			self.mode[0]()
		else:
			# search for object interaction
			h,w = self.ident_frame.viewport[2:]
			clicked = self.objat((x,y), 10)
			if clicked: 
				grp,rdr = self.stack[clicked[0]]
				# right-click is the selection button
				if b == Qt.RightButton and hasattr(rdr, 'select'):
					#rdr.select(clicked[1], not rdr.select(clicked[1]))
					self.main.select(*clicked, not rdr.select(clicked[1]))
				# other clicks are for custom controls
				elif hasattr(rdr, 'control'):
					self.tool = rdr.control(self, grp, clicked[1], (x, y))
	
	# exceptional override of this method to handle the opengl context change
	def event(self, event):
		if event.type() == QEventGLContextChange:
			#print('context change', self.initnum)
			if self.initnum > 1:
				# reinit completely the scene to rebuild opengl contextual objects
				newview = SceneView(self.main)
				newview.projection = self.projection
				newview.manipulator = self.manipulator
				self.parent().setWidget(newview)
			else:
				self.initnum += 1
			return True
		else:
			return super().event(event)



class TextEdit(QPlainTextEdit):
	''' text editor widget for ScriptView, only here to change some QPlainTextEdit behaviors '''		
	def focusInEvent(self, event):
		self.parent().focused()
		super().focusInEvent(event)

class ScriptView(QWidget):
	''' text editor part of the main frame '''
	tabsize = 4
	wordwrap = QTextOption.WrapMode.NoWrap
	font = QFont('NotoMono', 7)
	currenthighlight = QColor(128,128,128)
	zonehighlight = QColor(50, 50, 0)
	edithighlight = QColor(20, 80, 0)
	background = QColor(0,0,0)
	
	def __init__(self, main, parent=None):
		# NOTE:	for unknow reasons, a widget created as child of QPlainTextEdit is rendered only if created in the __init__

		super().__init__(parent)
		self.main = main
		self.editor = TextEdit()
		self.editor.setDocument(main.script)
		self.editor.setWordWrapMode(self.wordwrap)
		self.editor.setTabStopDistance(self.tabsize * QFontMetrics(self.font).maxWidth())
		# default widget colors
		palette = self.editor.palette()
		palette.setColor(QPalette.Base, self.background)
		self.editor.setPalette(palette)
		self.highlighter = Highlighter(self.editor.document(), self.font)
		self.linenumbers = False
		self.wlinenumbers = LineNumbers(self.font, self.editor)
		#self.enable_linenumbers(True)
		self.targetcursor = TargetCursor(main, self.editor)
		
		# statusbar
		statusbar = QWidget()
		self.label_location = QLabel('line 1, column 1')
		self.label_execution = QLabel('READY')
		self.trigger_mode = QComboBox()
		self.trigger_mode.addItem('manual')
		self.trigger_mode.addItem('on line change')
		self.trigger_mode.addItem('on each type')
		self.trigger_mode.setFrame(False)
		self.trigger_mode.setCurrentIndex(main.exectrigger)
		button_close = QPushButton(QIcon.fromTheme('dialog-close-icon'), '')
		button_close.setSizePolicy(QSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed))
		button_close.setStyleSheet('''QPushButton {
    border-style: outset;
    border-width: 0px;
}''')
		button_close.clicked.connect(self.close)
		layout = QHBoxLayout()
		#layout.addWidget(QLabel('<b>Script</b>'))
		layout.addWidget(self.label_location)
		layout.addWidget(self.label_execution)
		layout.addWidget(self.trigger_mode)
		layout.addWidget(button_close)
		statusbar.setLayout(layout)
		self.statusbar = statusbar
		
		# global layout
		layout = QVBoxLayout()
		layout.addWidget(self.editor)
		self.setLayout(layout)
				
		# setup editor
		self.editor.cursorPositionChanged.connect(self._cursorPositionChanged)
		self.editor.blockCountChanged.connect(self._blockCountChanged)
		self.editor.updateRequest.connect(self.update_linenumbers)
		main.exectarget_changed.connect(self.targetcursor.update)
		main.executed.connect(self._executed)
		
		main.views.append(self)
		if not main.active_scriptview:	main.active_scriptview = self
	
	def focused(self):
		# set active code view
		self.main.active_scriptview = self
		# update exectrigger and exectarget
		self.main.exectrigger = mode = self.trigger_mode.currentIndex()
		
	def changeEvent(self, event):
		# detect QDockWidget integration
		if event.type() == event.ParentChange and isinstance(self.parent(), QDockWidget):
			self.parent().setTitleBarWidget(self.statusbar)
		else:
			self.layout().addWidget(self.statusbar)
		return super().changeEvent(event)
	
	def _cursorPositionChanged(self):
		# update location label
		line, column = cursor_location(self.editor.textCursor())
		self.label_location.setText('line {}, column {}'.format(line+1, column+1))
		# try graphical editing
		self.main.cursorat((line, column))
	
	def _executed(self):
		self.main.cursorat(cursor_location(self.editor.textCursor()))
	
	def _blockCountChanged(self):
		self.update_linenumbers()
	
	def resizeEvent(self, event):
		super().resizeEvent(event)
		self.update_linenumbers()

	def update_linenumbers(self):
		# update the line number area
		if self.linenumbers:
			nlines = max(1, self.editor.blockCount())
			digits = 1
			while nlines >= 10:		
				nlines /= 10
				digits += 1
			charwidth = QFontMetrics(self.font).maxWidth()
			border = charwidth/2
			width = (digits+1)*charwidth
			self.editor.setViewportMargins(width, 0, 0, 0)
			cr = self.editor.contentsRect()
			self.wlinenumbers.setGeometry(QRect(cr.left(), cr.top(), width, cr.height()))
			self.wlinenumbers.width = width - border/2
			self.wlinenumbers.border = border
			self.wlinenumbers.setVisible(True)
			self.wlinenumbers.update()
		else:
			self.wlinenumbers.setVisible(False)
			self.editor.setViewportMargins(0, 0, 0, 0)
		self.editor.update()
	
	def close(self):
		self.main.views.remove(self)
		if isinstance(self.parent(), QDockWidget):
			self.main.removeDockWidget(self.parent())
		else:
			super().close()


VIEWPORT_OFFSET = 2		# experimental offset between retrieved coordinates from a QPlainTextEdit and the matching text position

class LineNumbers(QWidget):
	''' line number display for the text view '''
	def __init__(self, font, parent):
		super().__init__(parent)
		self.font = font
	def sizeHint(self):
		return QSize(self.width, 0)
	def paintEvent(self, event):
		# paint numbers from the first visible block to the last visible
		zone = event.rect()
		painter = QPainter(self)
		view = self.parent()
		block = view.firstVisibleBlock()
		top = view.blockBoundingGeometry(block).translated(view.contentOffset()).top()
		while block.isValid() and top <= zone.bottom():
			if block.isVisible() and top >= zone.top():
				height = view.blockBoundingRect(block).height()
				painter.setFont(self.font)
				painter.drawText(0, top, self.width, height, Qt.AlignRight, str(block.blockNumber()+1))
				top += height
			block = block.next()

class TargetCursor2(QWidget):
	''' target cursor for text view
		version with the label not fixed to text
	'''
	background = QColor(10,10,10)
	targetcolor = QColor(40,100,40)
	text = '>>  target'
	
	def __init__(self, main, parent):
		super().__init__(parent)
		self.main = main
		fontmetrics = QFontMetrics(self.font())
		h = fontmetrics.height()
		w = fontmetrics.horizontalAdvance(self.text)
		self.shape = s = QPainterPath()
		s.moveTo(h, 0)
		s.lineTo(h, 0)
		s.lineTo(h+w+h, 0)
		s.lineTo(h+w, h)
		s.lineTo(0, h)
		self.box = s.boundingRect().toRect()
		self.textstart = QPointF(h, 0.75*h)
		self.cursoroffset = QPointF(2*h, 0)
	
	def sizeHint(self):
		return self.box().size()
	
	def update(self):
		block = self.main.script.findBlockByNumber(self.main.exectarget-1)
		if not block.isValid():	block = self.main.script.lastBlock()
		cursor = QTextCursor(block)
		cursor.movePosition(cursor.EndOfLine)
		pos = (		self.parent().cursorRect(cursor).topRight() 
				+	self.parent().contentOffset() 
				+	QPointF(self.parent().viewportMargins().left(), 0) 
				+	self.cursoroffset
				).toPoint()
		self.setGeometry(self.box.translated(pos))
		super().update()
	
	def mouseMoveEvent(self, event):
		cursor = self.parent().cursorForPosition(event.pos() + self.pos())
		self.main.exectarget = cursor.blockNumber()
		self.update()
			
	def paintEvent(self, event):
		painter = QPainter(self)
		painter.fillPath(self.shape, self.targetcolor)
		painter.setPen(self.background)
		painter.drawText(self.textstart, self.text)

class TargetCursor(QWidget):
	''' target cursor display for the text view 
		version fixed to text
	'''
	background = QColor(10,10,10)
	targetcolor = QColor(40,100,40)
	font = QFont('NotoMono', 7)
	text = '>>  target'
	
	def __init__(self, main, parent):
		super().__init__(parent)
		self.setAttribute(Qt.WA_TransparentForMouseEvents)	# keep all the mouse events for the text view, (none will reach this widget :-/)
		self.main = main
		fontmetrics = QFontMetrics(self.font)
		h = fontmetrics.height()
		w = fontmetrics.horizontalAdvance(self.text)
		self.shape = s = QPainterPath()
		s.moveTo(h, 0)
		s.lineTo(h, 0)
		s.lineTo(h+w+h, 0)
		s.lineTo(h+w, h)
		s.lineTo(0, h)
		self.box = s.boundingRect().toRect()
		self.textstart = QPointF(h, 0.8*h)
		self.cursoroffset = QPointF(2*h, 0)
	
	def sizeHint(self):
		return self.parent().size()
	
	def update(self):
		self.setGeometry(self.parent().contentsRect())
		super().update()
	
	#def mouseMoveEvent(self, event):
		#print('coucou')
		#cursor = self.parent().cursorForPosition(event.pos() + self.pos())
		#self.main.exectarget = cursor.blockNumber()
		#self.update()
		#event.ignore()
	
	def paintEvent(self, event):
		block = self.main.script.findBlockByNumber(self.main.exectarget-1)
		if not block.isValid():	block = self.main.script.lastBlock()
		cursor = QTextCursor(block)
		cursor.movePosition(cursor.EndOfLine)
		pos = (		self.parent().cursorRect(cursor).topRight()
				+	QPointF(self.parent().viewportMargins().left(), 0) 
				+	self.cursoroffset
				)
		if event.rect().contains(pos.toPoint()):
			painter = QPainter(self)
			painter.fillPath(self.shape.translated(pos), self.targetcolor)
			painter.setPen(self.background)
			painter.setFont(self.font)
			painter.drawText(self.textstart + pos, self.text)


def cursor_location(cursor):
	return cursor.blockNumber(), cursor.positionInBlock()
def move_text_cursor(cursor, location, movemode=QTextCursor.MoveAnchor):
	line, column = location
	if cursor.blockNumber() < line:		cursor.movePosition(cursor.NextBlock, movemode, line-cursor.blockNumber())
	if cursor.blockNumber() < line:		cursor.movePosition(cursor.PreviousBlock, movemode, cursor.blockNumber()-line)
	if cursor.columnNumber() < column:	cursor.movePosition(cursor.NextCharacter, movemode, column-cursor.columnNumber())
	if cursor.columnNumber() > column:	cursor.movePosition(cursor.PreviousCharacter, movemode, cursor.columnNumber()-column)



from PyQt5.QtGui import QSyntaxHighlighter, QTextCharFormat, QColor
import re
def charformat(background=None, foreground=None, italic=None, overline=None, weight=None, font=None):
	''' create a QTextCharFormat '''
	fmt = QTextCharFormat()
	if background:	fmt.setBackground(background)
	if foreground:	fmt.setForeground(foreground)
	if italic is not None:		fmt.setFontItalic(italic)
	if overline is not None:	fmt.setFontOverline(overline)
	if weight:					fmt.setFontWeight(weight)
	if font:	fmt.setFont(font)
	return fmt

class Highlighter(QSyntaxHighlighter):
	''' python syntax highlighter for QTextDocument '''
	def __init__(self, document, font):
		super().__init__(document)
		self.format = QTextCharFormat()
		self.format.setForeground(QColor(255,100,0))
		self.fmt_default = charformat(foreground=QColor(255,255,255), font=font)
		self.fmt_keyword = charformat(foreground=QColor(50,210,150), font=font)
		self.fmt_call = charformat(foreground=QColor(200,255,150), font=font)
		self.fmt_constant = charformat(foreground=QColor(50,100,255), font=font)
		self.fmt_string = charformat(foreground=QColor(100,200,255), font=font)
		self.fmt_comment = charformat(foreground=QColor(150,150,150), font=font, italic=True)
		self.fmt_operator = charformat(foreground=QColor(50,100,150), font=font)
		self.states = {
			# normal context
			-1: [self.fmt_default,
				(re.compile(r'([a-zA-Z]\w*)\('), self.match_function),
				(re.compile(r'([a-zA-Z]\w*)'), self.match_word),
				(re.compile(r'#.*$'), self.match_comment),
				(re.compile(r'[+-]?\d+\.?\d*(e[+-]\d+)?'), self.fmt_constant),
				(re.compile(r'[+\-\*/@<>=!~&\|]+'), self.fmt_operator),
				
				(re.compile(r"^\s*'''"), self.match_commentstart1), 
				(re.compile(r"^\s*'"),   self.match_commentstart2), 
				(re.compile(r'^\s*"""'), self.match_commentstart3), 
				(re.compile(r'^\s*"'),   self.match_commentstart4), 
				(re.compile(r"'''"), self.match_stringstart1), 
				(re.compile(r"'"),   self.match_stringstart2), 
				(re.compile(r'"""'), self.match_stringstart3), 
				(re.compile(r'"'),   self.match_stringstart4), 
				],
			# string
			0: [self.fmt_string, (re.compile("'''"), self.match_stringend)],
			1: [self.fmt_string, (re.compile("'"),   self.match_stringend)],
			2: [self.fmt_string, (re.compile('"""'), self.match_stringend)],
			3: [self.fmt_string, (re.compile('"'),   self.match_stringend)],
			# comment
			4: [self.fmt_comment, (re.compile("'''"), self.match_commentend)],
			5: [self.fmt_comment, (re.compile("'"),   self.match_commentend)],
			6: [self.fmt_comment, (re.compile('"""'), self.match_commentend)],
			7: [self.fmt_comment, (re.compile('"'),   self.match_commentend)],
			}
			
	keywords = {'and', 'or', 'if', 'elif', 'else', 'for', 'while', 'in', 'not', 'def', 'class', 'yield', 'with', 'try', 'except', 'raise', 'return', 'from', 'import', 'as'}
	constants = {'None', 'True', 'False'}
	def match_word(self, match):
		word = match.group(1)
		if word in self.keywords:
			self.setFormat(match.start(1), match.end(1)-match.start(0), self.fmt_keyword)
		elif word in self.constants:
			self.setFormat(match.start(0), match.end(0)-match.start(0), self.fmt_constant)
		else:
			self.setFormat(match.start(0), match.end(0)-match.start(0), self.fmt_default)
		return match.end(1)
	def match_function(self, match):
		self.setFormat(match.start(1), match.end(1)-match.start(1), self.fmt_call)
		return match.end(1)
	def match_comment(self, match):
		self.setFormat(match.start(0), match.end(0)-match.start(0), self.fmt_comment)
		return match.end(0)
		
	def match_stringstart1(self, match):
		self.setFormat(match.start(0), match.end(0)-match.start(0), self.fmt_string)
		self.setCurrentBlockState(0)
		return match.end(0)
	def match_stringstart2(self, match):
		self.setFormat(match.start(0), match.end(0)-match.start(0), self.fmt_string)
		self.setCurrentBlockState(1)
		return match.end(0)
	def match_stringstart3(self, match):
		self.setFormat(match.start(0), match.end(0)-match.start(0), self.fmt_string)
		self.setCurrentBlockState(2)
		return match.end(0)
	def match_stringstart4(self, match):
		self.setFormat(match.start(0), match.end(0)-match.start(0), self.fmt_string)
		self.setCurrentBlockState(3)
		return match.end(0)
	def match_stringend(self, match):
		self.setFormat(match.start(0), match.end(0)-match.start(0), self.fmt_string)
		self.setCurrentBlockState(-1)
		return match.end(0)
		
	def match_commentstart1(self, match):
		self.setFormat(match.start(0), match.end(0)-match.start(0), self.fmt_comment)
		self.setCurrentBlockState(4)
		return match.end(0)
	def match_commentstart2(self, match):
		self.setFormat(match.start(0), match.end(0)-match.start(0), self.fmt_comment)
		self.setCurrentBlockState(5)
		return match.end(0)
	def match_commentstart3(self, match):
		self.setFormat(match.start(0), match.end(0)-match.start(0), self.fmt_comment)
		self.setCurrentBlockState(6)
		return match.end(0)
	def match_commentstart4(self, match):
		self.setFormat(match.start(0), match.end(0)-match.start(0), self.fmt_comment)
		self.setCurrentBlockState(7)
		return match.end(0)
	def match_commentend(self, match):
		self.setFormat(match.start(0), match.end(0)-match.start(0), self.fmt_comment)
		self.setCurrentBlockState(-1)
		return match.end(0)
	
	def highlightBlock_(self, text):
		#print('highlightBlock', type(text), text)
		self.setFormat(0, len(text), self.fmt_default)
		for pattern, func in self.patterns:
			start = 0
			while True:
				match = pattern.search(text, start)
				if match:
					start = func(match)+1
				else:
					break
	
	def highlightBlock(self, text):
		self.setCurrentBlockState(self.previousBlockState())
		start = 0
		end = len(text)
		while start < end:
			patterns = iter(self.states[self.currentBlockState()])
			default = next(patterns)
			self.setFormat(start, 1, default)
			for pattern, func in patterns:
				match = pattern.match(text, start)
				if match:
					if callable(func):
						start = func(match)-1
					else:
						self.setFormat(match.start(0), match.end(0)-match.start(0), func)
						start = match.end(0)-1
					break
			start += 1
				
		
		
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
