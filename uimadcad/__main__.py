
if __name__ == '__main__':

	# import the minimal runtime before checks
	import sys, os, locale

	import madcad
	from madcad.qt import (
		Qt, QTimer,
		QIcon,
		QApplication, QErrorMessage, QMessageBox,
		)
	
	from . import version, settings, resourcedir
	from .utils import *
	from .app import Madcad
		
	# parse commandline arguments
	file = None
	if len(sys.argv) >= 2:
		file = sys.argv[1]
	
	# set Qt opengl context sharing to avoid reinitialization of scenes everytime, (this is for pymadcad display)
	QApplication.setAttribute(Qt.AA_ShareOpenGLContexts, True)
	# setup Qt application
	app = QApplication(sys.argv)
	app.setApplicationName('madcad')
	app.setApplicationVersion(version)
	app.setApplicationDisplayName('madcad v{}'.format(version))
	
	# set icons if not provided by the system
	if not QIcon.themeName() and sys.platform == 'win32':
		# assume that the software is a portable version, so the icons are in the same dir as executable
		path = QIcon.themeSearchPaths()
		path.append(ressourcedir + '/icons')
		QIcon.setThemeSearchPaths(path)
		QIcon.setThemeName('breeze')		
	
	madcad.settings.install()
	madcad.settings.load()
	settings.install()
	settings.load()
	settings.use_color_preset()
	settings.use_stylesheet()
	
	# set locale settings to C default to get correct 'repr' of glm types
	locale.setlocale(locale.LC_NUMERIC, 'C')
	
	# create or load config
	if madcad.settings.display['system_theme']:
		madcad.settings.use_qt_colors()
	if settings.scriptview['system_theme']:
		settings.use_qt_colors()
	
	# start software
	madcad = Madcad(file)
	
	qtmain(app)
