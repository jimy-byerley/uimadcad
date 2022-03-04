import sys
import traceback
import locale
import signal
from threading import Thread, Lock
from collections import deque
	
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QApplication

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
