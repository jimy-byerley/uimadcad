import sys, os
from dataclasses import dataclass

from madcad.qt import QObject, QTextDocument, QFileDialog, QErrorMessage, QPlainTextDocumentLayout, QApplication

from . import settings
from .utils import signal, window, action, Initializer
from .interpreter import Interpreter
from .mainwindow import MainWindow
from .sceneview import Scene
# from .progressbar import Progress


@dataclass
class Active:
	sceneview = None
	scriptview = None
	errorview = None
	editor = None
	tool = None
	file: str = None
	export: str = None

class Madcad(QObject):
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
		self.window = window(MainWindow(self))
		
		self.load_file(file)
		
	def load_file(self, file=None):
		''' load the content of the file at the given path and replace the current scritpt '''
		self.active.file = file
		self.window.setWindowFilePath(self.active.file or 'untitled')
		self.document.setPlainText(open(self.active.file or settings.locations['startup'], 'r').read())
		self.document.setModified(False)

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
	def trigger_on_file_change(self):
		''' trigger execution on file change
			(save from this editor, or from external editor)
			
			when disabled, you must trigger manually
		'''
		...
	
	@action(icon='media-playback-start', shortcut='Ctrl+Return')
	def execute(self):
		''' run the script. 
			a parcimonial interpreter will take care of reexecuting only the changed code
		'''
		indev
		
	@action(icon='view-refresh', shortcut='Ctrl+Backspace')
	def clear(self):
		''' clear all caches of previous executions 
			next execution will reexecute the whole script from the beginning
		'''
		indev
		
	
	@action(icon='document-new-symbolic', shortcut='Ctrl+N')
	def new(self):
		''' open a new madcad instance with a blank script '''
		self.open_uimadcad()
	
	@action(icon='document-open-symbolic', shortcut='Ctrl+O')
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
	
	@action(icon='document-save-symbolic', shortcut='Ctrl+S')
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
			except OSError as err:
				popup = QErrorMessage(self.window)
				popup.showMessage(str(err))
			else:
				# inform Qt that the document has been saved in its current state
				self.document.setModified(False)
		else:
			self.save_as.trigger()
	
	@action(icon='document-save-as-symbolic', shortcut='Ctrl+Shift+S')
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
