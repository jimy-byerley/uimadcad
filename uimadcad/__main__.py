
if __name__ == '__main__':

	# import the minimal runtime before checks
	import sys, os, locale
	from PyQt5.QtCore import Qt, QTimer
	from PyQt5.QtGui import QIcon
	from PyQt5.QtWidgets import QApplication, QErrorMessage, QMessageBox
	
	from uimadcad import version
	from uimadcad.apputils import *
	from uimadcad.common import ressourcedir
	
	# set Qt opengl context sharing to avoid reinitialization of scenes everytime, (this is for pymadcad display)
	QApplication.setAttribute(Qt.AA_ShareOpenGLContexts, True)
	# setup Qt application
	app = QApplication(sys.argv)
	app.setApplicationName('madcad')
	app.setApplicationVersion(version)
	app.setApplicationDisplayName('madcad v{}'.format(version))
	
	# check for the presence of pymadcad (and all its dependencies)
	try:
		import madcad
	except ImportError:
		dialog = QMessageBox(
					QMessageBox.Critical, 
					'pymadcad not found', 
					'uimadcad is unable to import pymadcad, please make sure you installed it.\nPlease refer to the instructions at https://pymadcad.readthedocs.io/en/latest/installation.html\n\nuimadcad is unable to run without pymadcad.', 
					QMessageBox.Close)
		dialog.show()
		
		qtmain(app)
		raise

	# import the rest of uimadcad that depends on pymadcad
	from uimadcad.gui import *
	
	# set icons if not provided by the system
	if not QIcon.themeName() and sys.platform == 'win32':
		# assume that the software is a portable version, so the icons are in the same dir as executable
		path = QIcon.themeSearchPaths()
		path.append(ressourcedir + '/icons')
		QIcon.setThemeSearchPaths(path)
		QIcon.setThemeName('breeze')		
	
	settings.install()
	settings.load()
	settings.use_color_preset()
	settings.use_stylesheet()
	
	# set locale settings to C default to get correct 'repr' of glm types
	locale.setlocale(locale.LC_NUMERIC, 'C')
	
	# start software
	madcad = Madcad()
	main = MainWindow(madcad)
	
	def loaded():
		if not madcad.execthread:
			madcad.active_sceneview.adapt()
			madcad.executed.disconnect(loaded)
	def startup():
		if len(sys.argv) >= 2 and os.path.exists(sys.argv[1]):
			madcad.open_file(sys.argv[1])
		madcad.executed.connect(loaded)
	
	QTimer.singleShot(100, startup)
	main.show()
	
	qtmain(app)
