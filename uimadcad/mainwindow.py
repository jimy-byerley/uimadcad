import warnings

from madcad.qt import Qt, QWidget, QMainWindow, QDockWidget

from . import settings
from .sceneview import SceneView
from .scriptview import ScriptView
from .utils import ToolBar, Button, button, Initializer, hlayout, spacer

class MainWindow(QMainWindow):
	def __init__(self, app):
		super().__init__()
		# allows docks to stack horizontally or vertically
		self.setDockNestingEnabled(True)
		Initializer.init(self)
		
		self.app = app
		self.toolbar = ToolBar('app', [
			# menu.File(),
			None,
			self.clear,
			self.execute,
			None,
			# self.execution_trigger,
			# self.error_window,
			])

		self.layout_preset(settings.window['layout'])

	@button(icon='media-playback-start')
	def execute(self):
		indev
		
	@button(icon='view-refresh')
	def clear(self):
		indev
	
	def layout_preset(self, name):
		method = getattr(self, '_layout_'+name, None)
		if method:
			# clear
			for child in self.children():
				if isinstance(child, QDockWidget):
					self.removeDockWidget(child)
			# repopulate
			method()
		else:
			warnings.warn('unknown layout preset {}'.format(repr(name)))
	
	def _layout_default(self):
		# insert components to docker
		self.new_scriptview()
		self.new_sceneview()
		
		# use state to get the proper layout until we have a proper state backup
		self.restoreState(b'\x00\x00\x00\xff\x00\x00\x00\x00\xfd\x00\x00\x00\x02\x00\x00\x00\x00\x00\x00\x01\r\x00\x00\x01\xd8\xfc\x02\x00\x00\x00\x02\xfb\xff\xff\xff\xff\x01\x00\x00\x00\x1c\x00\x00\x01\xd8\x00\x00\x00\x87\x01\x00\x00\x03\xfb\xff\xff\xff\xff\x00\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00z\x01\x00\x00\x03\x00\x00\x00\x01\x00\x00\x02*\x00\x00\x01\xd8\xfc\x02\x00\x00\x00\x01\xfb\xff\xff\xff\xff\x01\x00\x00\x00\x1c\x00\x00\x01\xd8\x00\x00\x00\x94\x01\x00\x00\x03\x00\x00\x00\x00\x00\x00\x01\xd8\x00\x00\x00\x04\x00\x00\x00\x04\x00\x00\x00\x08\x00\x00\x00\x08\xfc\x00\x00\x00\n\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x01\x00\x00\x00\x00\x00\x00\x00\x01\x00\x00\x00\x00\x00\x00\x00\x01\x00\x00\x00\x04\x00\x00\x00\x14\x00t\x00o\x00o\x00l\x00b\x00a\x00r\x00-\x00i\x00o\x03\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00 \x00t\x00o\x00o\x00l\x00b\x00a\x00r\x00-\x00c\x00r\x00e\x00a\x00t\x00i\x00o\x00n\x03\x00\x00\x00R\xff\xff\xff\xff\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00$\x00t\x00o\x00o\x00l\x00b\x00a\x00r\x00-\x00a\x00n\x00n\x00o\x00t\x00a\x00t\x00i\x00o\x00n\x03\x00\x00\x01@\x00\x00\x00T\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x16\x00t\x00o\x00o\x00l\x00b\x00a\x00r\x00-\x00w\x00e\x00b\x03\x00\x00\x01\x8c\xff\xff\xff\xff\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x01\x00\x00\x00\x03\x00\x00\x00\x18\x00t\x00o\x00o\x00l\x00b\x00a\x00r\x00-\x00m\x00e\x00s\x00h\x03\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00&\x00t\x00o\x00o\x00l\x00b\x00a\x00r\x00-\x00c\x00o\x00n\x00s\x00t\x00r\x00a\x00i\x00n\x00t\x00s\x03\x00\x00\x00R\xff\xff\xff\xff\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00&\x00t\x00o\x00o\x00l\x00b\x00a\x00r\x00-\x00a\x00m\x00e\x00l\x00i\x00r\x00a\x00t\x00i\x00o\x00n\x03\x00\x00\x01\x8c\x00\x00\x01\x0e\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x02\x00\x00\x00\x00')
	
	def _layout_double(self):
		indev
	
	def _layout_triple(self):
		indev
		
	def _layout_minimal(self):
		indev

	def new_scriptview(self):
		''' insert a new code view into the window layout '''
		self.addDockWidget(Qt.TopDockWidgetArea, DockedView(ScriptView(self.app), 'script view'))
	
	def new_sceneview(self):
		''' insert a new 3d view into the window layout '''
		self.addDockWidget(Qt.TopDockWidgetArea, DockedView(SceneView(self.app), 'scene view'))

		
class DockedView(QDockWidget):
	def __init__(self, content:QWidget, title:str=None, closable=True, floatable=True):
		super().__init__()
		self.setWidget(content)
		if title:
			self.setWindowTitle(title)
		self.setFeatures(	QDockWidget.DockWidgetMovable
						|	(QDockWidget.DockWidgetFloatable if floatable else 0)
						|	(QDockWidget.DockWidgetClosable if closable else 0)
						)
		self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
		
		if isinstance(getattr(content, 'top', None), QWidget):
			title = QWidget()
			title.setLayout(hlayout([
				content.top,
				spacer(5,0),
				Button(self.setFloating, flat=True, minimal=True,
					icon='window-restore-symbolic', shortcut='Ctrl+Shift+F',
					description="detach view from main window"),
				Button(self.close, flat=True, minimal=True,
					icon='window-close-symbolic', shortcut='Ctrl+Shift+V',
					description="close view"),
				], spacing=0, margins=(0,0,0,0)))
			self.setTitleBarWidget(title)
