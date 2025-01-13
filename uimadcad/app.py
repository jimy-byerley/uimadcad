'''	Definition of the mainframe of the MADCAD gui

	Architecture
	============
	
		At contrary to usual data structures, in a gui and using Qt events in particular, the user will is received by the bottom nodes of the data tree: the user is not controling the top classes but interacting with the bottom unit objects.
		Therefore the data access is inverted allowing the user will to be better used: the unit classes are referencing their parents and manage their content.
		
		More specifically the gui is centered around a main non-graphical class Madcad, which most of the top widgets are referencing and exploiting as a shared ressource. The same is true for subwidgets of these top widgets.
'''


from PyQt5.QtCore import (
		Qt, QSize, QRect, QPoint, QPointF,
		QEvent, pyqtSignal, QObject, 
		QStringListModel,
		QUrl,
		)
from PyQt5.QtWidgets import (
		QApplication, QVBoxLayout, QWidget, QHBoxLayout, QStyleFactory, QSplitter, QSizePolicy, QAction, QActionGroup, QShortcut,
		QPlainTextDocumentLayout, 
		QPushButton, QLabel, QComboBox, QProgressBar,
		QMainWindow, QDockWidget, QFileDialog, QMessageBox, QDialog,
		QWhatsThis,
		)
from PyQt5.QtGui import (
		QFont, QFontMetrics, 
		QColor, QPalette,
		QIcon, QKeySequence, 
		QTextOption, QTextDocument, QTextCursor,
		QDesktopServices,
		)

import madcad
import madcad.settings
from madcad import *
from madcad.rendering import Display, Group, Turntable, Orbit, Displayable
from madcad.nprint import nprint, nformat, deformat

from .common import *
from .interpreter import Interpreter, InterpreterError, astinterval, astatpos
from .scriptview import ScriptView
from .sceneview import Scene, SceneView, SceneList, scene_unroll
from .errorview import ErrorView
from .detailview import DetailView
from .tooling import ToolAssist, ToolError, Modification
from .apputils import *
from . import tricks
from . import tooling
from . import settings

from copy import deepcopy, copy
from threading import Thread
from functools import partial
from dataclasses import dataclass
import ast, traceback
import os, sys
import re


@dataclass
class Active:
	sceneview = None
	scriptview = None
	errorview = None
	editor = None
	tool = None

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
		
		self.active = Active()
		
		self.exectrigger = settings.execution['trigger']
		self.exectarget = 0
		self.execthread = None
		self.editzone = [0,1]
		self.editors = {}
		self.details = {}
		self.hiddens = set()
		self.displayzones = {}
		self.lastinsert = None
		
		# madcad ressources (and widgets)
		self.standardcameras = {
			'-Z': fquat(fvec3(0, 0, 0)),
			'+Z': fquat(fvec3(pi, 0, 0)),
			'-X': fquat(fvec3(pi/2, 0, 0)),
			'+X': fquat(fvec3(pi/2, 0, pi)),
			'-Y': fquat(fvec3(pi/2, 0, -pi/2)),
			'+Y': fquat(fvec3(pi/2, 0, pi/2)),
			}
		
		self.script = QTextDocument(self)
		self.script.setDocumentLayout(QPlainTextDocumentLayout(self.script))
		self.script.contentsChange.connect(self._contentsChange)
		self.mod = Modification()
		self.base = mat4(1)
		self.scenesmenu = SceneList(self)
		self.interpreter = Interpreter(backuptime = settings.execution['backup'])
		self.scopes = []
		
		# madcad widgets
		self.scenes = []	# objets a afficher sur les View
		self.views = []		# widgets d'affichage (textview, sceneview, graphicview, ...)
		self.assist = ToolAssist(self)
		self.progressbar = ComputationProgress(self)
		self.mainwindow = None
		
		self.boot()

	def boot(self):
		''' set madcad in the startup state (software openning state) '''
		settings.install()
		madcad.settings.install()
		# create or load config
		if madcad.settings.display['system_theme']:
			madcad.settings.use_qt_colors()
		if settings.scriptview['system_theme']:
			settings.use_qt_colors()
		# load startup file
		cursor = QTextCursor(self.script)
		cursor.insertText(open(settings.locations['startup'], 'r').read())
	
	def close(self):
		# close all the subwindows
		for view in self.views:
			view.close()
		if self.mainwindow:	self.mainwindow.close()

	
	def createtool(self, name, procedure, icon=None, shortcut=None):
		''' create a QAction for the main class, with the given generator procedure '''
		action = QAction(name, self)
		if shortcut:	action.setShortcut(shortcut)
		if icon:		action.setIcon(QIcon.fromTheme(icon))
		
		# generator packing the given procedure to handle exceptions
		def capsule():
			self.cancel_tool()
			self.active.tool = procedure(self)
			self.assist.tool(name)
			self.assist.info('')
			try:
				yield from self.active.tool
			except ToolError as err:
				self.assist.info('<b style="color:#ff5555">{}</b>'.format(err))
			except Exception as err:
				traceback.print_exception(type(err), err, err.__traceback__)
				self.assist.info('<b style="color:#ff5555">internal error, check console</b>')
				self.assist.info('internal error')
			else:
				self.mod.commit(self.script)
				self.mod.clear()
				if self.exectrigger:	self.execute()
				else:	self.active.sceneview.update()
				self.assist.tool('')
				self.assist.info('')
			self.active.tool = None
		
		# button callback
		def callback():
			gen = capsule()
			# tools can run in one-sot
			try:	next(gen)
			except StopIteration:	return
			# or ask for more interactions
			scene = self.active.sceneview.scene
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
				self.mod.commit(self.script)
				self.mod.clear()
				if self.exectrigger:	self.execute()
				else:	self.active.sceneview.update()
		action.triggered.connect(callback)
		
		return action
	
	def cancel_tool(self):
		if self.active.tool:
			try:	self.active.tool.throw(ToolError('action canceled'))
			except ToolError:	pass
			except StopIteration:	pass
		self.assist.tool(None)
		self.active.tool = None
	
	# BEGIN --- file management system ---
	
	def open_file(self, filename):
		''' clears the current workspace and load the specified file
		'''
		extension = os.path.splitext(filename)[1][1:]
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
			import locale
			print('locale', locale.getpreferredencoding(False))
			QTextCursor(self.script).insertText(open(filename, 'r', encoding='UTF-8').read())
		
		self.script.setModified(False)
		self.script.clearUndoRedoStacks()
		self.file_changed.emit()
		return True
	
	def save(self, file=None):
		if not file:	file = self.currentfile
		if not file:	raise ValueError('no file is given and no current file')
		open(file, 'w').write(self.script.toPlainText())
		self.main.script.setModified(False)
		

	
	# END
	# BEGIN --- editing tools ----
				
	def _contentsChange(self, position, removed, added):
		if position < self.editzone[0] or self.editzone[1] < position:
			self.script.undo()
			return
		self.editzone[1] += added - removed
		# get the added text
		cursor = QTextCursor(self.script)
		cursor.setPosition(position+added)
		# there is an odd behavior with Qt in the case where we past text at position 0: Qt is telling that added is 1 character more than what it should be.
		# when so, the end position can then be out of text and QTextCursor reset it to 0, this will detect it.
		if cursor.position() != position+added:
			added -= 1
			cursor.setPosition(position+added)
		# select added text
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
		if self.execthread:
			self.execthread.join()
		
		self.progressbar.show()
		
		# place the exec target at the end of line
		cursor = QTextCursor(self.script)
		cursor.setPosition(self.exectarget)
		cursor.movePosition(QTextCursor.EndOfLine)
		self.exectarget = cursor.position()
		
		self.execution_label('RUNNING')
		self.interpreter.backups[0][1]['__file__'] = self.currentfile or './untitled.py'
		
		def job():
			#print('-- execute script --\n{}\n-- end --'.format(self.interpreter.text))
			try:
				res = self.interpreter.execute(self.exectarget, 
							autobackup=True, 
							onstep=lambda x: qtschedule(lambda: self.progressbar.set_state(x)),
							)
			except InterpreterError as report:
				@qtschedule
				def show(err=report.args[0]):
					self.showerror(err)
					self.execution_label('<p style="color:#ff5555">FAILED</p>')
			else:
				@qtschedule
				def show():
					self.execution_label('<p style="color:#55ff22">COMPUTED</p>')
					self.hideerror()
			self.currentenv = self.interpreter.current
			self.execthread = None
			
			@qtschedule
			def update():
				if not self.execthread:
					self.progressbar.hide()
				self.update_endzone()
				self.updatescript()
				self.executed.emit()
		
		self.execthread = Thread(target=job)
		self.execthread.start()
	
	def reexecute(self):
		''' reexecute all the script '''
		self.interpreter.change(self.editzone[0], 0, '')
		self.execute()
		
	def _targettocursor(self):
		# place the exec target at the cursor location
		self.exectarget = self.active.scriptview.editor.textCursor().position()
		self.exectarget_changed.emit()
	
	def showerror(self, err):
		view = self.active.errorview
		if view and not view.keep:
			view.set(err)
		else:
			self.active.errorview = view = ErrorView(self, err)
			self.views.append(view)
			view.show()
			if self.mainwindow:
				view.move(self.mainwindow.geometry().center())
				self.mainwindow.activateWindow()
	
	def hideerror(self):
		view = self.active.errorview
		if view and not view.keep:
			view.hide()
		
	def edit(self, name):
		if name in self.editors:
			return self.editors[name]
		obj = self.interpreter.current[name]
		editor = tricks.editors.get(type(obj))
		if not editor:
			return
		try:	
			self.editors[name] = e = editor(self, name)
		except tricks.EditionError as err:
			print('unable to edit variable', name, ':', err)
		else:
			self.active.sceneview.scene.sync()
			self.updatescript()
			return e
	
	def finishedit(self, name):
		if name in self.editors:
			self.editors[name].finalize()
			del self.editors[name]
			self.active.sceneview.scene.sync()
			self.updatescript()
			self.active.editor = next(iter(self.editors.values()), None)
			
	def _viewcenter(self):
		if self.active.sceneview:
			scene = self.active.sceneview.scene
			box = scene.selectionbox() or scene.box()
			self.active.sceneview.center(box.center)
	
	def _viewadjust(self):
		if self.active.sceneview:
			scene = self.active.sceneview.scene
			box = scene.selectionbox() or scene.box()
			self.active.sceneview.adjust(box)
	
	def _viewlook(self):
		if self.active.sceneview:
			scene = self.active.sceneview.scene
			box = scene.selectionbox() or scene.box()
			self.active.sceneview.look(box.center)
		
	def _viewnormal(self):
		if self.active.sceneview:
			self.active.sceneview.normalview()
	
	def targetcursor(self):
		cursor = self.active.scriptview.editor.textCursor()
		cursor.setPosition(self.exectarget)
		return cursor
	
	def insertexpr(self, text, format=True):
		# take note of that insertion
		self.lastinsert = partial(self.insertexpr, text[:])
		
		cursor = self.active.scriptview.editor.textCursor()
		original = text
		
		# replace selection if any
		if cursor.hasSelection():
			# pick interval in document
			start, stop = cursor.selectionStart(), cursor.selectionEnd()
			# pick indentation
			cursor.clearSelection()
			cursor.movePosition(QTextCursor.StartOfLine)
			cursor.movePosition(QTextCursor.EndOfWord, QTextCursor.KeepAnchor)
			indent = cursor.selectedText()
			assert not indent or indent.isspace(), repr(indent)
			# insert
			self.mod[start:stop] = text.replace('\n', '\n'+indent)
		
		else:
			# pick position to insert
			place = cursor.position()
			
			cursor.movePosition(QTextCursor.PreviousWord, QTextCursor.KeepAnchor)
			if '\u2029' in cursor.selectedText():
				last = '\n'
			else:
				cursor.movePosition(QTextCursor.EndOfWord)
				if cursor.position() > place:
					cursor.setPosition(place)
				cursor.movePosition(QTextCursor.PreviousCharacter, QTextCursor.KeepAnchor)
				last = cursor.selectedText()
				
			cursor.setPosition(place)
			cursor.movePosition(QTextCursor.EndOfWord)
			cursor.movePosition(QTextCursor.PreviousCharacter, QTextCursor.KeepAnchor)
			next = cursor.selectedText()
			
			# pick the indentation
			cursor.setPosition(place)
			cursor.movePosition(QTextCursor.StartOfLine)
			cursor.movePosition(QTextCursor.NextWord, QTextCursor.KeepAnchor)
			indent = cursor.selectedText().replace('\u2029', '')
			
			if not indent.isspace():
				indent = ''
						
			# insert in an expression
			if last in ',=+-*/([{' or next in ')]}':
				
				# pick the number of parenthesis in the current line
				cursor.setPosition(place)
				cursor.movePosition(QTextCursor.StartOfLine, QTextCursor.KeepAnchor)
				line = cursor.selectedText()
				openning = line.count('(') + line.count('[') + line.count('{') - line.count('}') - line.count(']') - line.count(')')
				
				if openning > 0:
					indent += '\t'
				elif openning < 0:
					indent = indent[:-1]
					
				if last in ',([{':
					text = '\n'+text+','
				elif next in ')]}':
					text = ',\n'+text
					
				self.mod[place] = text.replace('\n', '\n'+indent)
				
			# insert in an empty line
			elif not last or last in '\u2029\n \t':
				# check if there is something at the end of line
				cursor.setPosition(place)
				cursor.movePosition(QTextCursor.EndOfLine, QTextCursor.KeepAnchor)
				suite = cursor.selectedText()
				if suite and not suite.isspace():
					text += '\n'
				
				self.mod[place] = text.replace('\n', '\n'+indent)
				
			# break line and insert new statement
			else:
				indent = '\t' * len(self.scopes)
				self.mod[place] = '\n'+indent + text.replace('\n', '\n'+indent)
				
			
	
	def insertstmt(self, text):
		# take note of that insertion
		self.lastinsert = partial(self.insertstmt, text[:])
		print('lastinsert', self.lastinsert)
	
		# check if there is already something on the line
		cursor = self.active.scriptview.editor.textCursor()
		cursor.movePosition(QTextCursor.StartOfLine, QTextCursor.KeepAnchor)
		newline = not cursor.selectedText().isspace()
		# indentation
		cursor.clearSelection()
		cursor.movePosition(QTextCursor.NextWord, QTextCursor.KeepAnchor)
		indent = cursor.selectedText()
		if not indent.isspace():	indent = ''
		
		block = ''
		# integration
		if newline:
			block += '\n'+indent
		# insertion
		block += (text+'\n').replace('\n', '\n'+indent)
		self.mod[self.active.scriptview.editor.textCursor().position()] = block
		
	def redo_insert(self):
		if self.lastinsert:
			self.lastinsert()
			self.mod.commit(self.script)
			self.mod.clear()
		
	def _commentline(self):
		editor = self.active.scriptview.editor
		cursor = editor.textCursor()
		start, stop = sorted([cursor.position(), cursor.anchor()])
		# start operation
		cursor.beginEditBlock()
		cursor.setPosition(start)
		cursor.movePosition(QTextCursor.StartOfLine)
		while cursor.position() < stop:
			# comment
			cursor.insertText('#')
			# advance
			cursor.movePosition(QTextCursor.EndOfLine)
			cursor.movePosition(QTextCursor.NextCharacter)
		cursor.endEditBlock()
	
	def _uncommentline(self):
		editor = self.active.scriptview.editor
		cursor = editor.textCursor()
		start, stop = sorted([cursor.position(), cursor.anchor()])
		# start operation
		cursor.beginEditBlock()
		cursor.setPosition(start)
		cursor.movePosition(QTextCursor.StartOfLine)
		while cursor.position() < stop:
			# get the beginning of line
			cursor.movePosition(QTextCursor.NextCharacter, QTextCursor.KeepAnchor)
			while cursor.selectedText().isspace():
				cursor.clearSelection()
				cursor.movePosition(QTextCursor.NextCharacter, QTextCursor.KeepAnchor)
			# check for comment
			if cursor.selectedText() == '#':
				cursor.removeSelectedText()
				stop -= 1
			# advance
			cursor.movePosition(QTextCursor.EndOfLine)
			cursor.movePosition(QTextCursor.NextCharacter)
		cursor.endEditBlock()
		
	def _reformatcode(self):
		cursor = self.active.scriptview.editor.textCursor()
		anchor = min(cursor.anchor(), cursor.position())
		cursor.insertText(nformat(
							deformat(
								cursor.selectedText().replace('\u2029', '\n')), 
							width=50))
		cursor.setPosition(anchor, QTextCursor.KeepAnchor)
		self.active.scriptview.editor.setTextCursor(cursor)
		
	def _createlist(self):
		pass
	
	def _createfunction(self):	
		pass
		
	def deselectall(self):
		for disp in scene_unroll(self.active.sceneview.scene):
			if disp.selected:	disp.selected = False
			if type(disp).__name__ in ('SolidDisplay', 'WebDisplay'):
				disp.vertices.flags &= 0b11111110
				disp.vertices.flags_updated = True
		self.active.sceneview.scene.active_selection = None
		self.active.sceneview.update()
		self.active.sceneview.update_active_selection()
		self.updatescript()
		
	def set_active_solid(self):
		found = next((disp	for disp in scene_unroll(self.active.sceneview.scene)
							if isinstance(disp, Solid.display) and disp.selected), 
						None)
		self.active.sceneview.scene.active_solid = found
		self.active.sceneview.update()
		
	def lock_solid(self):
		view = self.active.sceneview
		locked = False
		for manip in scene_unroll(view.scene):
			if isinstance(manip, kinematic.Kinemanip):
				for i,disp in manip.displays.items():
					if isinstance(disp, Solid.display) and disp.selected:
						solid = manip.solids[i]
						manip.lock(view.scene, solid, not manip.islocked(solid))
						locked = True
		if not locked:
			view.scene.options['lock_solids'] = not view.scene.options['lock_solids']
		view.update()
	
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
		self.active.scriptview.linenumbers = enable
		self.active.scriptview.update_linenumbers()
	def _enable_line_wrapping(self, enable):
		self.active.scriptview.editor.setWordWrapMode(enable)
		
	def _display_quick(self, enable):
		settings.view['quick_toolbars'] = enable
		for view in self.views:
			if hasattr(view, 'quick'):
				view.quick.setHidden(not enable)
	
	
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
		for name,node in self.interpreter.locations.items():
			start,stop = astinterval(node)
			if start <= position and position <= stop:
				score = stop-start
				if score < mscore:
					mscore = score
					mname = name
		return mname
	
	def updatescript(self):
		zonehighlight = QColor(40, 200, 240, 60)
		selectionhighlight = QColor(100, 200, 40, 80)
		editionhighlight = QColor(255, 200, 50, 60)
		frozenhighlight = QColor(150, 150, 150)
		it = self.interpreter
	
		# highlight expression under cursor
		cursor = QTextCursor(self.script)
		extra = []
		for zs,ze in self.displayzones.values():
			cursor.setPosition(zs)
			cursor.setPosition(ze, QTextCursor.KeepAnchor)
			extra.append(extraselection(cursor, charformat(background=zonehighlight)))
		
		# highlight view selections
		if self.active.sceneview:
			seen = set()
			for obj in scene_unroll(self.active.sceneview.scene):
				if not hasattr(obj, 'source'):	continue
				i = id(obj.source)
				if (obj.selected and obj.source 
				and i not in seen 
				and	i in it.ids
				and it.ids[i] in it.locations):
					seen.add(i)
					zone = it.locations[it.ids[i]]
					cursor.setPosition(zone.position)
					cursor.setPosition(zone.end_position, QTextCursor.KeepAnchor)
					extra.append(extraselection(cursor, charformat(background=selectionhighlight)))
		
		# highlight zones edited by a view editor
		for edited in self.editors:
			zone = it.locations[edited]
			cursor.setPosition(zone.position)
			cursor.setPosition(zone.end_position, QTextCursor.KeepAnchor)
			extra.append(extraselection(cursor, charformat(background=editionhighlight)))
		
		# highlight text edition zone
		cursor.movePosition(cursor.Start)
		cursor.setPosition(self.editzone[0], QTextCursor.KeepAnchor)
		extra.append(extraselection(cursor, charformat(foreground=frozenhighlight)))
		
		cursor.setPosition(self.editzone[1]-1)
		cursor.movePosition(cursor.End, QTextCursor.KeepAnchor)
		extra.append(extraselection(cursor, charformat(foreground=frozenhighlight)))
		
		# commit all zones
		for view in self.views:
			if isinstance(view, ScriptView):
				view.editor.setExtraSelections(extra)
	
	def update_endzone(self):
		if self.interpreter.part:
			i = astatpos(self.interpreter.part, self.exectarget)
			if i < len(self.interpreter.part.body):
				around = self.interpreter.part.body[i]
				self.displayzones['aroundtarget'] = around.position, around.end_position
			else:
				self.displayzones.pop('aroundtarget', None)
	
	# END
	

def open_file_external(file):
	if 'linux' in sys.platform:
		os.system('xdg-open {}'.format(file))
	elif 'win' in sys.platform:
		os.system('start {}'.format(file))
	else:
		raise EnvironmentError('unable to open a textfile on platform {}'.format(os.platform))



