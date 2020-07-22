
class Generated(object):
	__slots__ = 'generator', 'value'
	def __init__(self, generator):	self.generator = generator
	def __iter__(self):				self.value = yield from self.generator

class Dispatcher(object):
	''' iterable object that holds a generator built by passing self as first argument
		it allows the generator code to dispatch references to self.
		NOTE:  at contrary to current generators, the code before the first yield is called at initialization
	'''
	__slots__ = 'generator', 'value'
	def __init__(self, func=None, *args, **kwargs):
		self.generator = self._run(func, *args, **kwargs)
		next(self.generator)
	def _run(self, func, *args, **kwargs):
		self.value = yield from func(self, *args, **kwargs)
		
	def send(self, value):	return self.generator.send(value)
	def __iter__(self):		return self.generator
	def __next__(self):		return next(self.generator)


def tutu(self, main):
	gnagna
	scene.tool = self.send
	budu.iterator = self
	
Dispatcher(tutu, main)
