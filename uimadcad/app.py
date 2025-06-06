import sys, os
from dataclasses import dataclass

from processional import SlaveThread
from madcad.qt import (
	QObject, QApplication, QTimer,
	QTextDocument, QFileDialog, QErrorMessage, QPlainTextDocumentLayout,
	)

from . import settings
from .utils import signal, window, action, button, Initializer, qtschedule
from .interpreter import Interpreter
from .mainwindow import MainWindow
from .sceneview import Scene
from .scriptview import SubstitutionIndex


@dataclass
class Active:
	''' non-unique instances currently in use by the user '''
	sceneview = None
	scriptview = None
	errorview = None
	scope = None
	editor = None
	tool = None
	file: str = None
	date: float = 0.
	export: str = None

class Madcad(QObject):
	''' a uimadcad application instance '''
	active_changed = signal()
	file_changed = signal()
	executed = signal()

	def __init__(self, file=None):
		super().__init__()
		Initializer.process(self)
		
		self.active = Active()
		self.scenes = []
		self.views = set()
		self.interpreter = Interpreter('<uimadcad>')
		self.document = QTextDocument(self)
		self.document.setDocumentLayout(QPlainTextDocumentLayout(self.document))
		self.reindex = SubstitutionIndex()
		self.window = window(MainWindow(self))
		self.thread = SlaveThread()
		
		self._check_change_timer = QTimer(self)
		self._check_change_timer.setInterval(5000)
		self._check_change_timer.timeout.connect(self.check_change)
		
		self.document.contentsChange.connect(self.reindex.substitute)
		
		self.load_file(file)
		
	def load_file(self, file=None):
		''' load the content of the file at the given path and replace the current scritpt '''
		self.active.file = file
		self.active.date = os.path.getmtime(file) if file else 0
		self.window.setWindowFilePath(self.active.file or 'untitled')
		self.document.setPlainText(open(self.active.file or settings.locations['startup'], 'r').read())
		self.document.setModified(False)
		if not file:
			self.execute.trigger()

	def open_file_external(self, file):
		''' open a file with an appropriate software decided by the desktop '''
		if 'linux' in sys.platform:
			os.system('xdg-open {}'.format(file))
		elif 'win' in sys.platform:
			os.system('start {}'.format(file))
		else:
			raise EnvironmentError('unable to open a textfile on platform {}'.format(os.platform))

	def open_uimadcad(self, *args):
		''' execute a new instance of uimadcad in a separate process '''
		argv = [sys.executable, '-P', '-m', 'uimadcad']
		argv.extend(args)
		os.spawnv(os.P_NOWAIT, sys.executable, argv)

	
	@action(icon='madcad-configure-uimadcad')
	def open_uimadcad_settings(self):
		''' open the settings file of uimadcad '''
		self.open_file_external(settings.locations['uisettings'])
	
	@action(icon='madcad-configure-pymadcad')
	def open_pymadcad_settings(self):
		''' open the settings file of pymadcad '''
		self.open_file_external(settings.locations['pysettings'])
	
	@action(icon='media-seek-forward', checked=False, shortcut='Ctrl+Shift+T')
	def trigger_on_file_change(self, enable):
		''' trigger execution on file change
			(save from this editor, or from external editor)
			
			when disabled, you must trigger manually
		'''
		if enable:
			self.load_file(self.active.file)
			self.execute.trigger()
			self._check_change_timer.start()
		else:
			self._check_change_timer.stop()
			
	def check_change(self):
		''' if enabled, check if the file changed on disk, then reload and reexecute it '''
		if self.trigger_on_file_change.isChecked():
			disk = os.path.getmtime(self.active.file)
			if disk > self.active.date:
				self.load_file(self.active.file)
				self.execute.trigger()
	
	@action(icon='media-playback-start', shortcut='Ctrl+Return')
	def execute(self):
		''' run the script. 
			a parcimonial interpreter will take care of reexecuting only the changed code
		'''
		self.stop.trigger()
		self.window.open_panel.setChecked(True)
		code = self.document.toPlainText()
		self.reindex.clear()
		
		progress = {}
		def step(scope, step, steps):
			@qtschedule
			def update():
				progress[scope] = step/steps
				self.window.panel.set_progress(progress)
		
		step(self.interpreter.filename, 0, 1)
		
		@self.thread.schedule
		def execution():
			self.interpreter.execute(code, step)
			if self.interpreter.exception:
				@qtschedule
				def update():
					self.window.panel.set_exception(self.interpreter.exception)
			else:
				@qtschedule
				def update():
					self.window.panel.set_success()
					QTimer.singleShot(1000, lambda: self.window.open_panel.setChecked(False))
			
			self.active.sceneview.scene.sync()
			self.active.sceneview.update()
	
	@action(icon='view-refresh', shortcut='Ctrl+Shift+Backspace')
	def clear(self):
		''' clear all caches of previous executions 
			next execution will reexecute the whole script from the beginning
		'''
		self.stop.trigger()
		self.interpreter = Interpreter(self.interpreter.filename)
		self.reindex = SubstitutionIndex()
		
	@action(icon='media-playback-stop', shortcut='Ctrl+Backspace')
	def stop(self):
		''' cancel the script execution '''
		self.interpreter.interrupt()
	
	@action(icon='document-new', shortcut='Ctrl+N')
	def new(self):
		''' open a new madcad instance with a blank script '''
		self.open_uimadcad()
	
	@action(icon='document-open', shortcut='Ctrl+O')
	def open(self):
		''' close this file and open an other script file '''
		filename, _ = QFileDialog.getOpenFileName(
			self.window, 
			caption = 'open madcad file', 
			directory = os.curdir, 
			filter = 'madcad files (*.py)',
			)
		if not filename:
			return
		self.open_uimadcad(filename)
	
	@action(icon='document-save', shortcut='Ctrl+S')
	def save(self):
		''' save the current edited file '''
		if self.active.file:
			assert isinstance(PermissionError(), OSError)
			try:
				tmpfile = self.active.file+'~'
				# write to a temporary file in case madcad fails while saving, so the target file is not corrupt
				open(tmpfile, 'w').write(self.document.toPlainText())
				# erase original file in one system call once saving is done
				os.replace(tmpfile, self.active.file)
				self.active.date = os.path.getmtime(self.active.file)
			except OSError as err:
				popup = QErrorMessage(self.window)
				popup.showMessage(str(err))
			else:
				# inform Qt that the document has been saved in its current state
				self.document.setModified(False)
		else:
			self.save_as.trigger()
	
	@action(icon='document-save-as', shortcut='Ctrl+Shift+S')
	def save_as(self):
		''' save as a new file '''
		filename, _ = QFileDialog.getSaveFileName(
			self.window,
			caption = 'save madcad file',
			directory = os.curdir,
			filter = 'madcad files (*.py)',
			)
		if not filename:
			return
		self.active.file = filename
		self.window.setWindowFilePath(self.active.file)
		self.save.trigger()
