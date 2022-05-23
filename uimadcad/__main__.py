def qpalette_gray():
	''' return a QPalette for gray theme '''
	palette = QPalette()
	
	palette .setColor(QPalette.Window, QColor(53,53,53))
	palette .setColor(QPalette.WindowText, Qt.white)
	palette .setColor(QPalette.Base, QColor(25,25,25))
	palette .setColor(QPalette.AlternateBase, QColor(53,53,53))
	palette .setColor(QPalette.ToolTipBase, Qt.white)
	palette .setColor(QPalette.ToolTipText, Qt.white)
	palette .setColor(QPalette.Text, Qt.white)
	palette .setColor(QPalette.Button, QColor(53,53,53))
	palette .setColor(QPalette.ButtonText, Qt.white)
	palette .setColor(QPalette.BrightText, Qt.red)
	palette .setColor(QPalette.Link, QColor(42, 130, 218))

	palette .setColor(QPalette.Highlight, QColor(42, 130, 218))
	palette .setColor(QPalette.HighlightedText, Qt.black)
	
	return palette
	
def qpalette_black():
	''' return a QPalette for a black theme '''
	palette = QPalette()
	
	palette .setColor(QPalette.Window, QColor(10,11,18))
	palette .setColor(QPalette.WindowText, QColor(190,207,210))
	palette .setColor(QPalette.Base, QColor(10,11,18))
	palette .setColor(QPalette.AlternateBase, QColor(18,19,31))
	palette .setColor(QPalette.ToolTipBase, Qt.white)
	palette .setColor(QPalette.ToolTipText, Qt.white)
	palette .setColor(QPalette.Text, QColor(212,231,234))
	palette .setColor(QPalette.Button, QColor(10,11,18))
	palette .setColor(QPalette.ButtonText, QColor(190,207,210))
	palette .setColor(QPalette.BrightText, Qt.red)
	palette .setColor(QPalette.Link, QColor(46,139,139))

	palette .setColor(QPalette.Highlight, QColor(0,150,150))
	palette .setColor(QPalette.HighlightedText, QColor(15,16,25))
	
	palette.setColor(QPalette.Active, QPalette.Button, QColor(10,11,18))
	palette.setColor(QPalette.Inactive, QPalette.Button, QColor(10,11,18))
	palette.setColor(QPalette.Disabled, QPalette.ButtonText, Qt.darkGray)
	palette.setColor(QPalette.Disabled, QPalette.WindowText, Qt.darkGray)
	palette.setColor(QPalette.Disabled, QPalette.Text, Qt.darkGray)
	palette.setColor(QPalette.Disabled, QPalette.Light, QColor(53, 53, 53))
	
	return palette


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
		print('no icon theme set')
		# assume that the software is a portable version, so the icons are in the same dir as executable
		path = QIcon.themeSearchPaths()
		path.append(ressourcedir + '/icons')
		QIcon.setThemeSearchPaths(path)
		QIcon.setThemeName('breeze')		
	
	settings.use_color_preset()
	settings.use_stylesheet()
	
	# set locale settings to default to get correct 'repr' of glm types
	locale.setlocale(locale.LC_NUMERIC, 'C')
	
	# start software
	madcad = Madcad()
	main = MainWindow(madcad)
	
	def startup():
		if len(sys.argv) >= 2 and os.path.exists(sys.argv[1]):
			madcad.open_file(sys.argv[1])
		madcad.active_sceneview.adjust()
	
	QTimer.singleShot(100, startup)
	main.show()
	
	qtmain(app)
