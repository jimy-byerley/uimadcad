
if __name__ == '__main__':
	from .gui import *

	import sys, os, locale
	from PyQt5.QtCore import Qt
	from PyQt5.QtWidgets import QApplication
	
	# set Qt opengl context sharing to avoid reinitialization of scenes everytime, (this is for pymadcad display)
	QApplication.setAttribute(Qt.AA_ShareOpenGLContexts, True)
	# setup Qt application
	app = QApplication(sys.argv)
	app.setApplicationName('madcad')
	app.setApplicationVersion(version)
	app.setApplicationDisplayName('madcad v{}'.format(version))
	
	# set locale settings to default to get correct 'repr' of glm types
	locale.setlocale(locale.LC_NUMERIC, 'C')
	
	# start software
	madcad = Madcad()
	
	if len(sys.argv) >= 2 and os.path.exists(sys.argv[1]):
		main.open_file(sys.argv[1])
	
	main = MainWindow(madcad)
	main.show()
	sys.exit(app.exec())
