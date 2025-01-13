from PyQt5.QtWidgets import QMenuBar, QMenu
from PyQt5.QtCore import QAction, Qt, QTimer
from PyQt5.QtWidgets import QApplication

import sys
import traceback
import locale
import signal
from threading import Thread, Lock
from collections import deque

__all__ = ['singleton', 'spawn', 'qtmain', 'qtschedule', 'qtinvoke', 'qtquit']


qtstopped = False

# setup that Ctrl+C will stop the python interpreter and the Qt application
def signal_interrupt(signal, frame):
	global qtstopped
	# immediately exit the program
	#import os
	#os._exit(1)
	
	# raise in the current thread
	if QApplication.instance() and not qtstopped:	
		qtstopped = True
		print(' quit Qt')
		qtquit()
	else:
		raise KeyboardInterrupt

signal.signal(signal.SIGINT, signal_interrupt)


class singleton(object):
	''' function decorator that caches the result and never reexecute a second time'''
	__slots__ = 'func', 'executed', 'value'
	def __init__(self, func):
		self.func = func
		self.executed = False
		
	def __call__(self):
		if not self.executed:
			self.value = self.func()
			self.executed = True
		return self.value
		

def spawn(func):
	''' spawn a thread running the given function '''
	thread = Thread(target=func)
	thread.start()
	return thread


qttasks = deque()
qttasks_timer = None
def qtmain(app=None):
	''' create and run the QApplication and the Qt main loop '''
	global qttasks_timer, qtstopped
	
	if not app:	
		app = QApplication(sys.argv)
	
	locale.setlocale(locale.LC_ALL, 'C')
	
	def process_tasks():
		while qttasks:
			qttasks.popleft() ()
			
	qttasks_timer = QTimer()
	qttasks_timer.setInterval(50)
	qttasks_timer.timeout.connect(process_tasks)
	qttasks_timer.start()
	
	qtstopped = False
	app.exec()

def qtschedule(callback):
	''' put a task for the Qt thread to execute as soon as possible '''
	qttasks.append(callback)

def qtinvoke(callback):
	''' same as qtschedule but wait for the task end '''
	lock = Lock()
	lock.acquire()
	result = [None, None]
	def wrapper():
		try:	result[0] = callback()
		except Exception as err:
			print_exc()
			result[1] = err
		lock.release()
	qtschedule(wrapper)
	lock.acquire()
	if result[1]:	raise result[1]
	return result[0]
	
def qtquit():
	''' close the QApplication it it exists '''
	app = QApplication.instance()
	if app:
		app.quit()



class MenuBar(QMenuBar):
    def __init__(self, menus:list=()):
        for name, menu in menus:
            self.addMenu(Menu(name, menu))

class Menu(QMenu):
    def __init__(self, name, actions:list=None):
        for name, action in actions:
            icon = None
            if isinstance(action, tuple):
                action, icon = action
            elif isinstance(action, QMenu):
                self.addMenu(menu)
            elif isinstance(action, QAction):
                self.addAction(action)
                
class Action(QAction):
    def __init__(self, 
			callback:callable=None, 
            name:str=None, 
            icon:str|QIcon=None, 
            shortcut:str|QKeySequence=None, 
            description:str=None, 
            checked:bool=None,
            parent=None):
        super().__init__(parent)
        if callback:
			if checked is None:
				self.triggered.connect(callback)
			else:
				self.toggled.connect(callback)
            if not name:    
				name = callback.__name__.replace('_', ' ')
            if not description: 
				description = callback.__doc__
        if name:  
            self.setText(name)
            self.setIconText(name)
        if description: 
            self.setToolTip(description)
            self.setWhatsThis(description)
        if icon:    
            if isinstance(icon, str):
                icon = QAction.fromTheme(icon)
            self.setIcon(icon)
        if shortcut:
            if isinstance(shortcut, str):
                shortcut = QKeySequence(shortcut)
            self.setShortcut(shortcut)
        if checked is not None:
            self.setCheckable(True)
            self.setChecked(checked)
        if group:
            group.addAction(self)

class Initializer: 
	'''
		>>> decorator = Initializer.decorator(MyClass)
		>>> initializer = decorator(*args, **kwargs)(f)
		>>> action = initializer(*args, **kwargs)
		>>> Initializer.init(obj)
	'''
	def decorator(cls):
		return partial(partial, Initializer, cls)
	def __init__(self, cls, *args, **kwargs):
		self.cls = cls
		self.args = args
		self.kwargs = kwargs
	def __call__(self, *args, **kwargs):
		return self.cls(*args, *self.args, **kwargs, **self.kwargs)
	def init(obj):
		for name, value in vars(obj).items():
			if isinstance(obj, Initializer):
				setattr(obj, name, value(obj))
			
action = Initializer(Action)

