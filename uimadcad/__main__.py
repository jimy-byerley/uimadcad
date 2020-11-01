
if __name__ == '__main__':
	from .gui import *

	import sys, os
	from PyQt5.QtCore import Qt
	from PyQt5.QtWidgets import QApplication
	
	QApplication.setAttribute(Qt.AA_ShareOpenGLContexts, True)
	app = QApplication(sys.argv)
	app.setApplicationName('madcad')
	app.setApplicationVersion(version)
	app.setApplicationDisplayName('madcad v{}'.format(version))
	main = Main()
	main.show()
	
	if len(sys.argv) >= 2 and os.path.exists(sys.argv[1]):
		main.open_file(sys.argv[1])
	
	sys.exit(app.exec())
