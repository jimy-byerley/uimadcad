import re
from collections import deque
from bisect import bisect_right

from arrex import typedlist
from pnprint import nformat, deformat, nprint
from madcad.mathutils import mix, vec4
from madcad.qt import (
	QWidget, QPlainTextEdit, QTextEdit, QVBoxLayout,
	QTextCursor, QSyntaxHighlighter, QFont, QFontMetrics, QColor, QBrush, QTextOption, QPalette, QPainter, QTextDocument,
	QSpinBox, QLabel, QLineEdit,
	Qt, QEvent, QMargins, QSize, QRect, QSizePolicy, QKeySequence, 
	)

from . import settings, ast
from .utils import (
	Initializer, button, action, shortcut,
	ToolBar, Action, vec_to_qcolor, charformat, extraselection, spacer, 
	vlayout, hlayout,
	qcolor_to_vec, vec_to_qcolor,
	)


class ScriptView(QWidget):
	''' text editor part of the app frame '''
	
	# NOTE:	for unknow reasons, a widget created as child of QPlainTextEdit is rendered only if created in the __init__
	
	bar_margin = 2
	
	def __init__(self, app, cursor=None, parent=None):
		self.app = app
		self.font = QFont(*settings.scriptview['font'])
		self.selection = []
		
		# set cursor position on openning
		if cursor:
			pass
		elif self.app.active.scriptview:
			cursor = app.active.scriptview.editor.textCursor()
		
		super().__init__(parent)
		self.setMinimumSize(200,100)
		self.setSizePolicy(QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred))
		Initializer.process(self, parent=self)
		
		self.editor = ScriptEdit(self)
		self.linenumbers = ScriptLines(self.font, self.editor)
		self.navigation = ScriptNavigation(self)
		self.findreplace = ScriptFindReplace(self)
		assert self.app.document is self.editor.document()
		
		# # toolbars
		self.top = ToolBar('top', [
			self.new_view,
			spacer(5, 0),
			self.open_navigation,
			self.view_selection,
			],
			orientation=Qt.Horizontal, 
			margins=QMargins(3,3,3,0),
			icon_size='small',
			parent=self.editor)
		
		self.bot = ToolBar('right', [
			self.undo,
			self.redo,
			None,
			self.indent_increase,
			self.indent_decrease,
			self.reformat,
			self.comment,
			self.uncomment,
			None,
			self.open_find,
			self.open_replace,
			self.seek_definition,
			None,
			self.fontsize_increase,
			self.fontsize_decrease,
			self.linewrap,
			self.show_linenumbers,
			],
			orientation=Qt.Horizontal, 
			margins=QMargins(0,3,3,3),
			icon_size='small',
			parent=self.editor)
		
		# global layout
		self.setLayout(vlayout([
			self.navigation,
			self.top,
			self.editor,
			self.findreplace,
			self.bot,
			], 
			margins=QMargins(0,0,0,0), 
			spacing=0))
		
		# other configurations
		self.setFocusProxy(self.editor)
		self.editor.updateRequest.connect(self._update_line_numbers)
		self.editor.cursorPositionChanged.connect(self._update_current_location)
		# self.editor.cursorPositionChanged.connect(self._update_active_selection)
		if cursor:
			self.editor.setTextCursor(cursor)
		
		self._update_colors()
		self._update_active_selection()
		self._update_current_location()
		self._retreive_settings()
		self._toolbars_visible(False)
		self.open_navigation.toggled.emit(False)
		self.open_find.toggled.emit(False)
	
	def keyPressEvent(self, event):
		event.accept()
		
		# shortcut for buttons (implemented here for priorization between widgets)
		# reimplement top bar shortcuts here because Qt cannot deambiguate which view the shortcut belongs to
		if event.key() == Qt.Key_Left and event.modifiers() & Qt.AltModifier:
			self.navigation.previous.click()
		elif event.key() == Qt.Key_Right and event.modifiers() & Qt.AltModifier:
			self.navigation.next.click()
		elif event.key() == Qt.Key_Down and event.modifiers() & Qt.AltModifier:
			self.view_selection.click()
		
		# open/close navigation widget
		elif event.key() == Qt.Key_Return and event.modifiers() & Qt.AltModifier:
			if not self.navigation.hasFocus():
				self.open_navigation.setChecked(True)
				self.navigation.setFocus()
			else:
				self.open_navigation.setChecked(False)
		
		# escape opened pannel
		elif event.key() == Qt.Key_Escape and self.open_navigation.isChecked():
			self.open_navigation.setChecked(False)
		elif event.key() == Qt.Key_Escape and self.open_find.isChecked():
			self.open_find.setChecked(False)
		
		else:
			event.ignore()
			return super().keyPressEvent(event)
	
	def showEvent(self, event):	
		self.app.views.add(self)
		if not self.app.active.scriptview:	
			self.app.active.scriptview = self
	
	def hideEvent(self, event):
		self.app.views.remove(self)
		if self.app.active.scriptview is self:
			self.app.active.scriptview = None
		
	def changeEvent(self, event):
		# detect theme change
		if event.type() == QEvent.PaletteChange and settings.scriptview['system_theme']:
			settings.use_qt_colors()
			self._update_colors()
		return super().changeEvent(event)
	
	def resizeEvent(self, event):
		super().resizeEvent(event)
		
		# self.bot.setGeometry(
		# 	self.width() - self.bot.sizeHint().width() - self.bar_margin, 
		# 	max(0, self.height()//2 - self.bot.sizeHint().height()//2),
		# 	self.bot.sizeHint().width(), 
		# 	min(self.height(), self.bot.sizeHint().height()),
		# 	)
		# scrollbar = self.editor.horizontalScrollBar()
		# scroll_margin = scrollbar.height() * scrollbar.isVisible()
		# self.bot.setGeometry(
		# 	max(0, self.editor.width()//2 - self.bot.sizeHint().width()//2), 
		# 	self.editor.height() - self.bot.sizeHint().height() - self.bar_margin - scroll_margin,
		# 	min(self.editor.width(), self.bot.sizeHint().width()),
		# 	self.bot.sizeHint().height(),
		# 	)
		# self.bot.setGeometry(
		# 	0,
		# 	self.editor.height()//2,
		# 	self.bot.sizeHint().width(),
		# 	self.bot.sizeHint().height(),
		# 	)
		# if self.top.parent() is self:
		# 	self.top.setGeometry(
		# 		self.bar_margin+self.left.width(), 
		# 		self.bar_margin,
		# 		self.width()-self.left.width() - self.bar_margin,
		# 		self.top.sizeHint().height(),
		# 		)
		
		self._update_line_numbers()
	
	def _toolbars_visible(self, enable):
		self.bot.setVisible(enable or self.findreplace.isVisible())

	def _update_colors(self):
		''' update widget colors according to settings '''
		palette = self.editor.palette()
		# background colors
		palette.setColor(QPalette.Base, vec_to_qcolor(settings.scriptview['background']))
		palette.setColor(QPalette.ColorRole.Highlight, vec_to_qcolor(settings.scriptview['selection_background']))
		# no color change for highligted text, so the syntax and extra selections will stay visible
		palette.setBrush(QPalette.ColorRole.HighlightedText, QBrush(Qt.NoBrush))
		
		self.editor.setPalette(palette)
		self.highlighter = Highlighter(self.editor.document(), self.font)
	
	def _update_line_numbers(self):
		left = 0
		
		# update the line number area
		if self.show_linenumbers.isChecked():
			# compute number of digits
			nlines = max(1, self.editor.blockCount())
			digits = 1
			while nlines >= 10:		
				nlines //= 10
				digits += 1
			# resize area
			charwidth = QFontMetrics(self.font).maxWidth()
			border = charwidth//2
			width = (digits+3)*charwidth
			left = width
			cr = self.editor.contentsRect()	# only this rect has the correct area, with the good margins with the real widget geometry
			self.linenumbers.setGeometry(QRect(cr.left(), cr.top(), width, cr.height()))
			self.linenumbers.width = width - border//2
			self.linenumbers.border = border
			self.linenumbers.update()
		
		self.editor.setViewportMargins(left, 0, 0, 0)
		self.editor.update()
	
	def _update_current_location(self):
		cursor = self.editor.textCursor()
		# update location label
		line, column = cursor_location(cursor)
		self.open_navigation.setText('position: {}:{}'.format(line+1, column+1))
		
		self.app.active.scope = self.app.interpreter.scope_at(self.app.reindex.downgrade(cursor.position()))
		if cursor.hasSelection():
			start, stop = sorted([
				self.app.reindex.downgrade(cursor.position()), 
				self.app.reindex.downgrade(cursor.anchor()),
				])
			selection = list(self.app.interpreter.names_crossing(range(start, stop)))
		else:
			try:
				item = self.app.interpreter.name_at(self.app.reindex.downgrade(cursor.position()))
			except IndexError:
				selection = []
			else:
				selection = [item]
		
		if selection != self.selection:
			self.selection = selection
			self._update_active_selection()
			self.sync()
	
	def _update_active_selection(self):
		if self.selection:
			active = self.selection[0]
			text = active.scope+'.'+active.name
			if text.startswith(self.app.interpreter.filename):
				text = text[len(self.app.interpreter.filename)+1:]
		
			font = QFont(*settings.scriptview['font'])
			pointsize = font.pointSize()
			self.view_selection.setFont(font)
			self.view_selection.setText(text)
			self.view_selection.setEnabled(True)
			self.view_selection.show()
		else:
			self.view_selection.setEnabled(False)
			self.view_selection.setFont(QFont())
			self.view_selection.setText('seek selection')
			self.view_selection.hide()
		if self.app.active.sceneview:
			self.app.active.sceneview.scene.sync()
			self.app.active.sceneview.update()
	
	def sync(self):
		''' synchronize the text rendering with what is available in the app (selections, hovers, editors, ...) '''
		s = settings.scriptview
		selected = charformat(background=vec_to_qcolor(s['selection_background']))
		highlighted = charformat(background=vec_to_qcolor(s['hover_background']))
		
		highlights = []
		# selections from the script view
		for item in self.selection:
			highlights.append(extraselection(self._reindex_cursor(item.range), highlighted))
		# selection from the scene view
		if self.app.active.sceneview:
			scene = self.app.active.sceneview.scene
			for display in scene.selection:
				for source in scene.sources(display):
					highlights.append(extraselection(self._reindex_cursor(source.range), selected))
				
		self.editor.setExtraSelections(highlights)
		
	def _reindex_cursor(self, range:range):
		cursor = self.editor.textCursor()
		cursor.setPosition(self.app.reindex.upgrade(range.start), cursor.MoveMode.MoveAnchor)
		cursor.setPosition(self.app.reindex.upgrade(range.stop-1)+1, cursor.MoveMode.KeepAnchor)
		return cursor
	
	def _retreive_settings(self):
		self.show_linenumbers.setChecked(settings.scriptview['linenumbers'])
		self.linewrap.setChecked(settings.scriptview['linewrap'])
	
	@action(icon='view-dual')
	def new_view(self):
		''' create a new view widget '''
		self.app.window.insert_view(self, ScriptView(
			self.app, 
			self.editor.textCursor(),
			))

	@button(flat=True, checked=False) #, shortcut='Alt+Return')
	def open_navigation(self, visible):
		''' cursor position in the script, click to modify 
			
			(shortcut: Alt+Return)
		'''
		self.navigation.setVisible(visible)
		if visible:
			self.navigation.setFocus()
		else:
			self.setFocus()
		
	@button(flat=True) #, shortcut='Alt+Down')
	def view_selection(self):
		''' zoom the object in selected variable in the active sceneview 
		
			(shortcut: Alt+Down)
		'''
		if not self.app.active.sceneview:
			return
		view = self.app.active.sceneview
		selected = False
		for source in self.selection:
			try:
				if source.scope == self.app.interpreter.filename:
					scope = view.scene.root
				else:
					scope = view.scene.root[source.scope]
				found = scope[source.name]
			except KeyError:
				continue
			if hasattr(found, 'selected'):
				view.scene.selection_add(found)
				selected = True
		if selected:
			view.view_adjust.trigger()
			view.setFocus()
	
	@action(icon='go-up', shortcut='Alt+Up')
	def seek_definition(self):
		''' move cursor to the definition of variable under cursor
		
			(mouse: Ctrl+click)
		'''
		indev
		
	
	@action(icon='edit-undo', shortcut='Ctrl+Z')
	def undo(self):
		''' undo previous changes in history '''
		self.app.document.undo()
		
	@action(icon='edit-redo', shortcut='Ctrl+Y')
	def redo(self):
		''' redo next changes in history '''
		self.app.document.redo()
	
	def _get_block(self) -> QTextCursor:
		''' retreive a cursor surrounding and completing the selected lines '''
		cursor = self.editor.textCursor()
		start, stop = sorted([cursor.position(), cursor.anchor()])
		cursor.setPosition(start)
		cursor.movePosition(QTextCursor.StartOfLine)
		cursor.movePosition(QTextCursor.PreviousCharacter)
		cursor.setPosition(stop, QTextCursor.KeepAnchor)
		return cursor
		
	def _set_block(self, cursor, text):
		''' set the text in the given cursor but keeps it selected '''
		view = self.editor.textCursor()
		start = min(view.position(), view.anchor())
		
		cursor.insertText(text)
		
		view.setPosition(start, cursor.KeepAnchor)
		self.editor.setTextCursor(view)
	
	@action(icon='format-indent-more') #, shortcut='Tab')
	def indent_increase(self):
		''' increase the indentation level of the current or selected lines 
		
			(shortcut: Tab)
		'''
		cursor = self._get_block()
		self._set_block(cursor, cursor.selectedText().replace('\u2029', '\u2029\t'))
	
	@action(icon='format-indent-less') #, shortcut='Shift+Tab')
	def indent_decrease(self):
		''' decrease the indentation level of the current or selected lines 
		
			(shortcut: Shift+Tab)
		'''
		cursor = self._get_block()
		self._set_block(cursor, cursor.selectedText().replace('\u2029\t', '\u2029'))
		
	@action(icon='format-justify-center', shortcut='Ctrl+Shift+F')
	def reformat(self):
		''' reformat selected code to get proper nested indentation 
			and split long expressions into multiple lines 
		'''
		cursor = self._get_block()
		raw = cursor.selectedText()
		# TODO: better handle case where first lines are empty
		i = 0
		while raw[i].isspace():
			i += 1
		indentation = raw[:i]
		reformated = '\n'+nformat(
			deformat(raw.replace(indentation, '\n')), 
			width=50
			)
		self._set_block(cursor, reformated.replace('\n', indentation))
		
	@action(icon='edit-comment', shortcut='Ctrl+D')
	def comment(self):
		''' change selected lines or current line into comments to disable them '''
		cursor = self._get_block()
		self._set_block(cursor, cursor.selectedText().replace('\u2029', '\u2029#'))
		
	@action(icon='delete-comment', shortcut='Ctrl+Shift+D')
	def uncomment(self):
		''' uncomment selected lines or current line in order to reenable them '''
		cursor = self._get_block()
		self._set_block(cursor, cursor.selectedText().replace('\u2029#', '\u2029'))
		
	@action(icon='format-font-size-more', shortcut='Ctrl++')
	def fontsize_increase(self):
		''' increase the script font size (purely visual) '''
		self.font.setPointSize(self.font.pointSize() + 1)
		self.highlighter = Highlighter(self.editor.document(), self.font)
	
	@action(icon='format-font-size-less', shortcut='Ctrl+-')
	def fontsize_decrease(self):
		''' decrease the script font size (purely visual) '''
		self.font.setPointSize(self.font.pointSize() - 1)
		self.highlighter = Highlighter(self.editor.document(), self.font)
		
	@action(icon='text-wrap', checkable=True, shortcut='F9')
	def linewrap(self, enable):
		''' wrap lines when too long for the script view '''
		if enable:
			self.editor.setWordWrapMode(QTextOption.WordWrap)
		else:
			self.editor.setWordWrapMode(QTextOption.NoWrap)
	
	@action(icon='madcad-line-numbers', checkable=True, shortcut='F10')
	def show_linenumbers(self, visible):
		''' show line numbers aside of script '''
		self.linenumbers.setVisible(visible)
		self._update_line_numbers()
		
	@action(icon='edit-find', checked=False, shortcut='Ctrl+F')
	def open_find(self, visible):
		''' find occurences of a text sequence '''
		if visible:
			self.findreplace.open(replace=False)
		else:
			self.findreplace.hide()
			self.setFocus()
		
	@action(icon='edit-find-replace', shortcut='Ctrl+R')
	def open_replace(self):
		''' replace a text sequence by an other '''
		self.open_find.setChecked(True)
		self.findreplace.open(replace=True)
	
	def seek_line(self, lineno:int):
		''' set cursor and scroll to lineno '''
		block = self.editor.document().findBlockByLineNumber(lineno-1)
		cursor = QTextCursor(block)
		cursor.movePosition(QTextCursor.EndOfLine)
		self.editor.setTextCursor(cursor)
		self.editor.ensureCursorVisible()
	
	def seek_position(self, position:int|range):
		''' set cursor and scroll to position '''
		cursor = QTextCursor(self.editor.document())
		if isinstance(position, int):
			cursor.setPosition(position)
		elif isinstance(position, range):
			cursor.setPosition(position.stop, QTextCursor.MoveMode.MoveAnchor)
			cursor.setPosition(position.start, QTextCursor.MoveMode.KeepAnchor)
		self.editor.setTextCursor(cursor)
		self.editor.ensureCursorVisible()


class ScriptEdit(QPlainTextEdit):
	''' text editor widget for ScriptView, only here to change some QPlainTextEdit behaviors '''
	
	def __init__(self, view: ScriptView):
		super().__init__(view)
		
		self.setDocument(view.app.document)
		self.setWordWrapMode(QTextOption.WrapMode.WordWrap 
									if settings.scriptview['linewrap'] else 
									QTextOption.WrapMode.NoWrap)
		self.setTabStopDistance(settings.scriptview['tabsize'] * QFontMetrics(view.font).averageCharWidth()+1.5)
		self.setCursorWidth(QFontMetrics(view.font).averageCharWidth())
		self.setCenterOnScroll(True)
	
	def focusInEvent(self, event):
		view = self.parent()
		view.app.active.scriptview = view
		view._toolbars_visible(True)
		view.app.window.clear_panel(view)
		# view.app.window.open_panel.setChecked(False)
		super().focusInEvent(event)
		
	def focusOutEvent(self, event):
		view = self.parent()
		view._toolbars_visible(False)
		super().focusOutEvent(event)
	
	def keyPressEvent(self, event):
		event.ignore()
		cursor = self.textCursor()
		if cursor.hasSelection():
			if event.key() == Qt.Key.Key_Tab:		
				self.parent().indent_increase.trigger()
				event.accept()
			elif event.key() == Qt.Key.Key_Backtab:	
				self.parent().indent_decrease.trigger()
				event.accept()
		if not event.isAccepted():
			return super().keyPressEvent(event)
	

class ScriptLines(QWidget):
	''' line number display for the text view '''
	def __init__(self, font, parent):
		super().__init__(parent)
		self.font = font
		self.width = 0
	def sizeHint(self):
		return QSize(self.width, 0)
	def paintEvent(self, event):
		# paint numbers from the first visible block to the last visible
		zone = event.rect()
		painter = QPainter(self)
		painter.setFont(self.font)
		painter.setPen(vec_to_qcolor(settings.scriptview['normal_color'] * 0.4))
		view = self.parent()
		block = view.firstVisibleBlock()
		top = int(view.blockBoundingGeometry(block).translated(view.contentOffset()).top())
		charwidth = QFontMetrics(self.font).maxWidth()
		while block.isValid() and top <= zone.bottom():
			if block.isVisible() and top >= zone.top():
				height = int(view.blockBoundingRect(block).height())
				painter.drawText(0, top, self.width-2*charwidth, height, Qt.AlignRight, str(block.blockNumber()+1))
				top += height
			block = block.next()


class ScriptNavigation(QWidget):
	''' cursor navigation panel '''
	def __init__(self, view, parent=None):
		self.view = view
		self.history = deque(maxlen=20)
		self.index = -1
		self.last_line = 0
		self.last_edit = 0
		
		super().__init__(parent)
		self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Maximum)
		Initializer.process(self)
		
		self.view.editor.cursorPositionChanged.connect(self._update_location_cursor)
		self.view.editor.document().contentsChange.connect(self._update_location_edit)
		
		self.line = QSpinBox()
		self.setLayout(hlayout([
			self.previous,
			self.next,
			QLabel('line:'),
			self.line,
			self.go,
			]))
			
		self.setFocusProxy(self.line)
		self._update_range()
		
	def _update_location_cursor(self):
		''' update location history with a cursor position change '''
		cursor = self.view.editor.textCursor()
		line = cursor.blockNumber()
		if abs(line - self.last_line) > 1:
			self._append(cursor.position())
		self.last_line = line
			
	def _update_location_edit(self, position, removed, added):
		''' update location history with a document change '''
		if abs(position - self.last_edit) > 1:
			self.history.append(position)
		self.last_edit = position
		
	def _append(self, position):
		''' register a position change in the history '''
		if self.index < 0 or self.history[self.index] != position:
			while self.index < len(self.history)-1:
				self.history.pop()
			self.history.append(position)
			self.index = len(self.history)-1
		self._update_range()
		
	def _update_range(self):
		''' update displays when the index or history size changes '''
		self.previous.setEnabled(self.index > 0)
		self.next.setEnabled(self.index < len(self.history)-1)
		
	def showEvent(self, event):
		self.line.setValue(self.view.editor.textCursor().blockNumber()+1)
		self.line.setMinimum(1)
		self.line.setMaximum(self.view.editor.document().lineCount())
		self.line.lineEdit().selectAll()
		
	def keyPressEvent(self, event):
		event.accept()
		if event.key() == Qt.Key_Return:
			self.go.click()
		else:
			event.ignore()
			super().keyPressEvent(event)
	
	@button(icon='go-previous', flat=True) #, shortcut='Alt+Left')
	def previous(self):
		''' move cursor to previous historical position 
		
			(shortcut: Alt+Left)
		'''
		self.index = max(self.index-1, 0)
		self.seek_position(self.history[self.index])
		
	@button(icon='go-next', flat=True) #, shortcut='Alt+Right')
	def next(self):
		''' move cursor to next historical position 
		
			(shortcut: Alt+Right)
		'''
		self.index = min(self.index+1, self.history.maxlen)
		self.seek_position(self.history[self.index])
		
	@button(icon='go-jump', flat=True) #, shortcut='Enter')
	def go(self):
		''' go to selected line 
		
			(shortcut: Enter)
		'''
		self.seek_line(self.line.value()-1)
		self.view.open_navigation.setChecked(False)
		self.view.setFocus()

	def seek_line(self, line, column=0):
		''' move cursor to the given line in document '''
		cursor = self.view.editor.textCursor()
		cursor.setPosition(column)
		cursor.movePosition(QTextCursor.Down, QTextCursor.MoveAnchor, line)
		self.view.editor.setTextCursor(cursor)
		self.view.editor.setFocus()
	
	def seek_position(self, position):
		''' move cursor to the position in document '''
		cursor = self.view.editor.textCursor()
		cursor.setPosition(position)
		self.view.editor.setTextCursor(cursor)
		self.view.editor.setFocus()

class ScriptFindReplace(QWidget):
	''' find and replace form for `ScriptEdit` '''
	def __init__(self, view, parent=None):
		self.view = view
		super().__init__(None)
		Initializer.process(self)
		
		self.src = QLineEdit()
		self.dst = QLineEdit()
		
		# same font as editor
		self.src.setFont(view.font)
		self.dst.setFont(view.font)
		# line labels are nicer when same size
		lfind = QLabel('find')
		lreplace = QLabel('replace')
		lfind.setMinimumSize(lreplace.sizeHint())
		# allow fields to expand since buttons may take more space
		self.src.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
		self.dst.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
		self.src.textChanged.connect(self._reset_colors)
		self.dst.textChanged.connect(self._reset_colors)
		
		self.setLayout(vlayout([
			hlayout([lfind, spacer(10,0), self.src, self.previous, self.next]),
			hlayout([lreplace, spacer(10,0), self.dst, self.one, self.all]),
			],
			margins = QMargins(15,0,3,3),
			))
			
	def open(self, replace=False):
		''' run the find/replace tool, use the editor selected text if any '''
		self.show()
		self.src.setFocus()
		
		pattern = self.view.editor.textCursor().selectedText()
		self.src.setText(pattern)
		if replace:
			if pattern:
				self.dst.setFocus()
		else:
			self.dst.clear()
	
	@button()
	def one(self):
		''' replace one occurence '''
		self._find_next()
		self.view.editor.textCursor().insertText(self.dst.text())
		
	@button()
	def all(self):
		''' replace all occurences '''
		editor = self.view.editor
		src = self.src.text()
		dst = self.dst.text()
		
		# progress in file replacing everything
		cursor = editor.textCursor()
		# create an edition block, for later reuse
		cursor.beginEditBlock()
		cursor.endEditBlock()
		cursor.setPosition(1)
		found = False
		while True:
			cursor = editor.document().find(
				src,
				cursor,
				QTextDocument.FindFlags(0))
			# check result and move cursor
			if cursor.isNull():
				break
			found = True
			# proceed by joining blocks, because create a big edition block at once may crash Qt
			cursor.joinPreviousEditBlock()
			cursor.insertText(dst)
			cursor.endEditBlock()
		
		# taint the replacing text entry according to the success
		self.dst.setPalette(self._colorize(found))
		
	@button(icon='go-up', flat=True, shortcut='Shift+Return')
	def previous(self):
		''' find previous occurence '''
		self._find_next(True)
		
	@button(icon='go-down', flat=True, shortcut='Return')
	def next(self):
		''' find next occurence '''
		self._find_next(False)
		
	def _find_next(self, reverse=False):
		''' find next occurence, with custom search direction '''
		editor = self.view.editor
		target = editor.document().find(
			self.src.text(),
			editor.textCursor(),
			QTextDocument.FindFlags(0
				| QTextDocument.FindBackward * reverse
				))
		# check result and move cursor
		if not target.isNull():
			editor.setTextCursor(target)
			
		# taint the pattern text entry according to the success
		self.src.setPalette(self._colorize(not target.isNull()))
		
	def _colorize(self, positive=True):
		''' create a palette to color text entries like the given color '''
		color = vec4(0,1,0,0) if positive else vec4(1,0,0,0)
		palette = self.palette()
		background = mix(
			qcolor_to_vec(palette.color(QPalette.Base)), 
			color, 
			0.1)
		palette.setColor(QPalette.Base, vec_to_qcolor(background))
		return palette
		
	def _reset_colors(self):
		''' reset entries background colors '''
		palette = self.palette()
		self.src.setPalette(palette)
		self.dst.setPalette(palette)
		
		
class Highlighter(QSyntaxHighlighter):
	''' python syntax highlighter for `ScriptEdit` '''
	def __init__(self, document, font):
		super().__init__(document)
		# default font applies everywhere the highlighter doesn't pass, like empty lines
		document.setDefaultFont(font)
		# precompute formatting for every case
		s = settings.scriptview
		self.fmt_default = charformat(foreground=vec_to_qcolor(s['normal_color']), font=font)
		self.fmt_keyword = charformat(foreground=vec_to_qcolor(s['keyword_color']), font=font, weight=QFont.ExtraBold)
		self.fmt_call = charformat(foreground=vec_to_qcolor(s['call_color']), font=font)
		self.fmt_constant = charformat(foreground=vec_to_qcolor(s['number_color']), font=font)
		self.fmt_string = charformat(foreground=vec_to_qcolor(s['string_color']), font=font)
		self.fmt_comment = charformat(foreground=vec_to_qcolor(s['comment_color']), font=font, italic=True, weight=QFont.Thin)
		self.fmt_operator = charformat(foreground=vec_to_qcolor(s['operator_color']), font=font)
		# state machine description
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
	
	keywords = {'pass', 'and', 'or', 'if', 'elif', 'else', 'match', 'case', 'for', 'while', 'break', 'continue', 'is', 'in', 'not', 'def', 'lambda', 'class', 'yield', 'async', 'await', 'with', 'try', 'except', 'finally', 'raise', 'from', 'import', 'as', 'with', 'return', 'assert'}
	constants = {'None', 'True', 'False', 'Ellipsis'}
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
	
	def highlightBlock(self, text):
		# state machine execution on a block of text (a line of code)
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


def cursor_location(cursor):
	return cursor.blockNumber(), cursor.positionInBlock()

def move_text_cursor(cursor, location, movemode=QTextCursor.MoveAnchor):
	line, column = location
	if cursor.blockNumber() < line:		cursor.movePosition(cursor.NextBlock, movemode, line-cursor.blockNumber())
	if cursor.blockNumber() < line:		cursor.movePosition(cursor.PreviousBlock, movemode, cursor.blockNumber()-line)
	if cursor.columnNumber() < column:	cursor.movePosition(cursor.NextCharacter, movemode, column-cursor.columnNumber())
	if cursor.columnNumber() > column:	cursor.movePosition(cursor.PreviousCharacter, movemode, cursor.columnNumber()-column)


class SubstitutionIndex:
	''' reindexation between a fixed sequence and a changed sequence '''
	def __init__(self):
		self._src = typedlist((0,), int)  # represent the index in the original sequence
		self._dst = typedlist((0,), int)  # represent the index in the modified sequence
	
	def clear(self):
		''' clear all discontiguities '''
		del self._src[1:]
		del self._dst[1:]
		self._src[0] = 0
		self._dst[0] = 0
	
	def substitute(self, position:int, remove:int=0, add:int=0):
		''' change the index to remove and add a number of elements
			
			complexity is O(n)
		'''
		i = bisect_right(self._dst, position)-1
		change = add - remove
		new_src = position - self._dst[i] + self._src[i]
		new_dst = position + change
		if self._src[i] == new_src or self._dst[i] >= new_dst:
			self._src[i] = new_src
			self._dst[i] = new_dst
		else:
			self._src.insert(i+1, position - self._dst[i] + self._src[i])
			self._dst.insert(i+1, position + change)
			i += 1
		for j in range(i+1, len(self._dst)):
			self._dst[j] += change
	
	def upgrade(self, position:int) -> int:
		''' convert the given position before substitution to position after substitution 
		
			complexity is O(log(n))
		'''
		i = bisect_right(self._src, position)-1
		up = position - self._src[i] + self._dst[i]
		if up < self._dst[i]:
			up = self._dst[i]
		elif i+1 < len(self._src) and up > self._dst[i+1]:
			up = self._dst[i+1]
		return up
		
	def downgrade(self, position:int) -> int:
		''' convert the given position after substitution to position before substitution 
		
			complexity is O(log(n))
		'''
		i = bisect_right(self._dst, position)-1
		down = position - self._dst[i] + self._src[i]
		if down < self._src[i]:
			down = self._src[i]
		elif i+1 < len(self._src) and down > self._src[i+1]:
			down = self._src[i+1]
		return down
	
	def steps(self) -> int:
		''' return the number of index discontiguities '''
		return len(self._src) -1


