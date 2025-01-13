from .utils import action
                
                
class File(QObject):
	def __init__(self, main):
		action.init(self)
		self.main = main
		self.menu = Menu('&File', [
			self.new,
			self.open,
			self.save,
			self.save_as,
			self.save_a_copy,
			None,
			self.uimadcad_settings,
			self.pymadcad_settings,
			self.open_startup_file,
			])
	
    @action(icon='document-new', shortcut='Ctrl+N')
    def new(self):
        if sys.argv[0].endswith('.py'):
            os.spawnl(os.P_NOWAIT, sys.executable, sys.executable, sys.argv[0])
        else:
            os.spawnl(os.P_NOWAIT, sys.argv[0], sys.argv[0])
            
	@action(icon='document-open', shortcut='Ctrl+O')
	def open(self):
		filename = QFileDialog.getOpenFileName(self.mainwindow, 'open madcad file', 
							os.curdir, 
							'madcad files (*.py *.mc);;text files (*.txt)',
							)[0]
		if filename:
			self.main.open_file(filename)
	
    @action(icon='document-open', shortcut='Ctrl+N')
    def save(self):
        if not self.main.currentfile:
            self._save_as.trigger()
        else:
            self.main.save()

    @action(icon='document-save', shortcut='Ctrl+N')
    def save_as(self):
        file = self._prompt_file()
        if file:
            self.main.currentfile = file
            self.main.save()
    
    @action(icon='document-save-as', shortcut='Ctrl+N')
    def save_copy(self):
        file = self._prompt_file()
        if file:
            self.main.save(file)
    
    @action(icon='document-export', shortcut='Ctrl+N')
    def open_uimadcad_settings(self):
        open_file_external(settings.locations['uisettings'])
    
    @action(icon='preference-other', shortcut='Ctrl+N')
    def open_pymadcad_settings(self):
        open_file_external(settings.locations['pysettings'])
	
	def _prompt_file(self):
		dialog = QFileDialog(self.mainwindow, 'save madcad file', self.main.currentfile or os.curdir)
		dialog.setAcceptMode(QFileDialog.AcceptSave)
		dialog.exec()
		if dialog.result() == QDialog.Accepted:
			choice = dialog.selectedFiles()[0]
			extension = choice[choice.find('.')+1:]
			if extension not in ('py', 'txt'):
				box = QMessageBox(
					QMessageBox.Warning, 'bad file type', 
					"The file extension '{}' is not a standard madcad file extension and may result in problems to open the file from a browser\n\nSave anyway ?".format(extension),
					QMessageBox.Yes | QMessageBox.Discard,
					)
				if box.exec() == QMessageBox.Discard:	return
			
			return choice


class Edit(QObject):
	def __init__(self, main):
		action.init(self)
		self.main = main
		self.menu = Menu('&Edit', [
			Action(main.script.undo, icon='edit-undo', shortcut='Ctrl+Z'),
			Action(main.script.redo, icon='edit-redo', shortcut='Ctrl+Shift+Z'),
			None,
			Action(main.execute, icon='media-playback-start', shortcut='Ctrl+Return'),
			Action(main.reexecute, icon='view-refresh', shortcut='Ctrl+Shift+Return'),
			self.target_to_cursor,
			None,
			Action(main.deselectall, 'deselect all', 'edit-select-all', 'Ctrl+A'),
			Action(tooling.act_rename, 'rename object', 'edit-rename', 'F2'),
			self.edit,
			self.finish_edit,
			])
	
	@action(shortcut='Ctrl+T')
	def target_to_cursor(self):
		# place the exec target at the cursor location
		self.exectarget = self.active.scriptview.editor.textCursor().position()
		self.exectarget_changed.emit()
		
	@action(icon='edit-select-all', shortcut='Ctrl+A')
	def edit(self):
		for disp in scene_unroll(self.active.sceneview.scene):
			(	disp.selected 
			and hasattr(disp, 'source') 
			and id(disp.source) in self.interpreter.ids 
			and self.edit(self.interpreter.ids[id(disp.source)])
			)
	
	@action(icon='edit-paste', shortcut='Escape')
	def finish_edit(self):
		if self.active.tool:
			self.cancel_tool()
		else:
			if not self.active.editor:
				self.active.editor = next(iter(self.editors.values()), None)
			if self.active.editor:
				self.finishedit(self.active.editor.name)
				
class Window(QObject):
	def __init__(self, main):
		action.init(self, main)
		self.menu = Menu('&Window', [
			Action(main._display_quick, 'display quick access toolbars', checked=settings.view['quick_toolbars']),
			None,
			Menu('style sheet', [Action(
				name = name, 
				checked = name == settings.view['stylesheet'],
				callback = partial(settings.use_stylesheet, name),
				group = style,
				) for name in settings.list_stylesheets() ]),
			Menu('theme', [Action(
				name = name,
				checked = name == settings.view['color_preset'],
				callback = partial(settings.use_color_preset, name),
				group = theme,
				) for name in settings.list_color_presets() ]),
			Menu('layout preset', []),
			None,
			self.save_layout_state,
			None,
			self.new_3d_view,
			self.new_text_view,
			]),
	
	@action()
	def save_layout_state(self):
		print(self.main.mainwindow.saveState())
	
	@action(icon='object')
	def new_3d_view(self):
		self.main.mainwindow.addDockWidget(Qt.RightDockWidgetArea, dock(SceneView(self.main), 'scene view'))
	
	@action(icon='dialog-script')
	def new_text_view(self):
		self.main.mainwindow.addDockWidget(Qt.RightDockWidgetArea, dock(ScriptView(self.main), 'build script'))

			
class Scene(QObject):
	def __init__(self, main):
		action.init(self, main)
		self.menu = Menu('&Scene' [
			self.display_faces,
			self.display_groups,
			self.display_groups,
			self.display_wire,
			self.display_points,
			self.display_grid,
			self.display_annotations,
			self.display_all,
			None,
			self.switch_projection,
			self.view_center,
			self.view_adjust,
			self.view_toward,
			self.view_normal,
			])
	
	@action(shortcut='Shift+F')
	def display_faces(self, enable):
		if self.active.sceneview:
			self.active.sceneview.scene.options['display_faces'] = enable
			self.active.sceneview.scene.touch()
	
	@action(shortcut='Shift+G')
	def display_groups(self, enable):
		if self.active.sceneview:
			self.active.sceneview.scene.options['display_groups'] = enable
			self.active.sceneview.scene.touch()
	
	@action(shortcut='Shift+W')
	def display_wire(self, enable):
		if self.active.sceneview:
			self.active.sceneview.scene.options['display_wire'] = enable
			self.active.sceneview.scene.touch()
	
	@action(shortcut='Shift+P')
	def display_points(self, enable):
		if self.active.sceneview:
			self.active.sceneview.scene.options['display_points'] = enable
			self.active.sceneview.scene.touch()
	
	@action(shortcut='Shift+G')
	def display_grid(self, enable):
		if self.active.sceneview:
			self.active.sceneview.scene.options['display_grid'] = enable
			self.active.sceneview.scene.touch()
	
	@action(shortcut='Shift+D')
	def display_annotations(self, enable):
		if self.active.sceneview:
			self.active.sceneview.scene.options['display_annotations'] = enable
			self.active.sceneview.scene.touch()
	
	@action(shortcut='Shift+V')
	def display_all(self, enable):
		if self.active.sceneview:
			self.active.sceneview.scene.displayall = enable
			self.active.sceneview.scene.sync()
	
	def display_none(self, enable):
		if self.active.sceneview:
			self.active.sceneview.scene.displaynone = enable
			self.active.sceneview.scene.sync()
	
	@action(shortcut='Shift+S')
	def switch_projection(self):
		if self.active.sceneview:
			self.active.sceneview.projectionswitch()
	
	def switch_kinematic_mode(self, mode):
		if self.active.sceneview:
			self.active.sceneview.scene.options['kinematic_manipulation'] = mode
			self.active.sceneview.scene.sync()
	
	@action(shortcut='Shift+C')
	def view_center(self):
		if self.active.sceneview:
			scene = self.active.sceneview.scene
			box = scene.selectionbox() or scene.box()
			self.active.sceneview.center(box.center)
	
	@action(shortcut='Shift+A')
	def view_adjust(self):
		if self.active.sceneview:
			scene = self.active.sceneview.scene
			box = scene.selectionbox() or scene.box()
			self.active.sceneview.adjust(box)
	
	@action(shortcut='Shift+L')
	def view_toward(self):
		if self.active.sceneview:
			scene = self.active.sceneview.scene
			box = scene.selectionbox() or scene.box()
			self.active.sceneview.look(box.center)
		
	@action(shortcut='Shift+N')
	def view_normal(self):
		if self.active.sceneview:
			self.active.sceneview.normalview()
	
	
