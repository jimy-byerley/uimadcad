
class Madcad:
	exectarget_changed = pyqtSignal()
	executed = pyqtSignal()
	
	def __init__(self):
		
		# main components
		self.script = QTextDocument(self)
		self.script.setDocumentLayout(QPlainTextDocumentLayout(self.script))
		self.script.contentsChange.connect(self._contentsChange)
		self.interpreter = Interpreter()
		self.scenelist = SceneList(self)
		
		self.forceddisplays = set()	# names of variables to display even when non active
		self.displayzones = []	# zones where all temporary objects are displayed
		self.neverused = set()	# names of variables created but never used
		
		self.scene = {}	# objets a afficher sur les View
		self.views = []
		self.active_sceneview = None
		self.active_scriptview = None
		self.activetrick = None
		self.selection = set()
		self.exectrigger = 1
		self.exectarget = 0
		
		self.currentfile = None
		self.currentexport = None
		
		self.ui = Gui()
		
		cursor = QTextCursor(self.script)
		cursor.insertText('from madcad import *\n\n')
	
