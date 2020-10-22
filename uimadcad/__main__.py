
if __name__ == '__main__':
	from .gui import *

	import sys
	from PyQt5.QtCore import Qt
	from PyQt5.QtWidgets import QApplication
	
	QApplication.setAttribute(Qt.AA_ShareOpenGLContexts, True)
	app = QApplication(sys.argv)
	app.setApplicationName('madcad')
	app.setApplicationVersion(version)
	app.setApplicationDisplayName('madcad v{}'.format(version))
	main = Main()
	main.show()
	sys.exit(app.exec())
