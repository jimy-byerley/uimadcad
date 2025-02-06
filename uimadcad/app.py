from dataclasses import dataclass

from madcad.qt import QObject, QTextDocument

from . import settings
from .utils import signal, window
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

	def __init__(self):
		super().__init__()
		
		self.active = Active()
		self.scenes = []
		self.views = []
		self.interpreter = Interpreter('<uimadcad>')
		self.document = QTextDocument(self)
		self.window = window(MainWindow(self))
		# self.progress = Progress()

