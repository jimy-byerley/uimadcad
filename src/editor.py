
"""
class RWLock(object):
	''' read-write lock.
		a class inspired by rust's RWLock mutex, using threading.Lock
	'''
	__slots__ = 'readers', 'lock'
	def __init__(self):
		self.readers = 0
		self.lock = Lock()
	@property
	def read(self):
		return self
	@property
	def write(self):
		return self.lock
		
	def __start__(self):
		if self.readers == 0:	
			self.lock.acquire()
		self.readers += 1
	def __end__(self):
		self.readers -= 1
		if self.readers == 0:	
			self.lock.release()

class Interval(object):
	''' generic interval class, with comparison implemented.
		If min and max are numbers, it's classic real intervals
		If they are tuples, this can be version intervals or text zone intervals
	'''
	__slots__ = 'min', 'max'
	def __init__(self, min, max):
		self.min = min
		self.max = max
	def __contains__(self, other):
		if isinstance(other, TextZone):		return self.max <= other.min and other.max <= self.max
		else:								return NotImplemented
	def __eq__(self, other):
		if isinstance(other, TextZone):		return self.min == other.min and other.max == self.max
		else:								return NotImplemented
	def __lt__(self, other):
		if isinstance(other, TextZone):		return self.max < other.min
		else:								return NotImplemented
	def __le__(self, other):
		if isinstance(other, TextZone):		return self.max <= other.min
		else:								return NotImplemented
	def __gt__(self, other):
		if isinstance(other, TextZone):		return self.min > other.max
		else:								return NotImplemented
	def __ge__(self, other):
		if isinstance(other, TextZone):		return self.min >= other.max
		else:								return NotImplemented
	def __repr__(self):
		return '{}({}, {})'.format(type(self).__name__, self.min, self.max)
"""
		

import dis
from types import ModuleType
from copy import copy, deepcopy
from bytecode import Bytecode, Instr
from madcad.mathutils import dichotomy_index
from nprint import nprint
from time import time

class InterpreterError(Exception):	pass

class Interpreter:
	'''	script interpreter for optimized recalculation
		attributes defined here:
			* backups = [(line, env dict)]      execution environments backups, line is the line number just after the executed block.  the items are sorted in ascending order
			* lines	= [str]                     list of string lines ('\n' ended)
		
		NOTE ABOUT EXECUTION
			the environments is copied at each backup stage, so any value refering to precision object memory location (such as id()) wouldn't work
		
		NOTE: the tabulation size used for location is always 1
	'''
	backupstep = 0.1
	
	def __init__(self, text='', env=None, title='custom-interpreter'):
		self.persistent = ModuleType(title)
		self.results = self.persistent.RESULTS = {}
		if env is None:		env = {}
		self.backups = [(0, env)]
		self.lines = text.split('\n')
		self.lines.append('\n')
		self.lines.append('\n')	# the last line is always empty to simplify bounds checks
	
	def text(self, start=None, end=None):
		''' text content of the script '''
		if start is None:	start = (0,0)
		if end is None:		end = (len(self.lines)-1, 0)
		ls,cs = start
		le,ce = end
		if ls != le:
			return self.lines[ls][cs:] + ''.join(self.lines[ls+1:le]) + self.lines[le][:ce]
		else:
			return self.lines[ls][cs:ce]
	
	def execute(self, stop=None, backup=False):
		''' execute the code from the last backup to the given stop line (the stop line is not executed).
			if backup is True, then register the end env state as a new backup point
		'''
		if stop is None:	stop = len(self.lines)-1
		# get the initial environment
		backi = self.lastbackup(stop)
		backline, backvars = self.backups[backi]
		# assemble the script
		try:
			stopline, stopcol = self.findexpressionend(backline, stop)
		except EOFError:
			stopline, stopcol = len(self.lines)-1, 0
		script = ''.join(self.lines[backline:stopline]) + self.lines[stopline][:stopcol]
		
		# parse the bytecode (using the native python tools here)
		try:
			code = compile(script, 'block', 'exec')
		except SyntaxError or EOFError as err:
			raise InterpreterError(err)
		# get the code to execute until the stop line
		code, reused = self.transformcode(code, stop, backline)
		
		# copy the environment variables used
		env = copyvars(backvars, code.co_names)				
		# remove old temporary values
		for line in range(backline, stopline):
			self.results.pop(line, None)
		
		self.starttime = time()
		# execute the code
		try:
			# SECURITY WARNING the executed user code access the whole process here
			result = eval(code, vars(self.persistent), env)
		except Exception as err:
			raise InterpreterError(err)
		
		#for varname,lineno in assigned:
			#self.results[lineno-1] = env[varname]
		if backup:
			backi = self.lastbackup(stop)
			self.backups.insert(backi+1, (stop, env))
			
		for i,(backline,backenv) in enumerate(self.backups):
			print('backup', i, backline, backenv.keys() & {'part', 'vis', 'cone', 'place', 'part', 'big', 'pl', 'sel', 'loop', 'w', 'line'})
		#print('intermediate results', self.results)
		return result, env, code.co_names, reused
	
	def lastbackup(self, line):
		''' get the index of the last env backup before line or for line '''
		i = dichotomy_index(self.backups, line, key=lambda backup: backup[0])
		if i == len(self.backups) or self.backups[i][0] > line:	i -= 1
		return i
	
	def findexpressionend(self, start, end=None):
		''' find the line at which the expression starting at line ends.
			assumes that the given line starts really at an expression/statement location
		'''
		# NOTE:  it doesn't support multiline comments yet
		# count the number of parentheses and brackets, when level is 0, a python expression ends with the line
		# the only exceptions are comments and strings, where anything can be in, but that can't be stacked
		if end is None:		end = start
		line = start
		level = 0
		waiting = None
		#print()
		while line < len(self.lines):
			#print('level', level, 'continues on ', self.lines[line])
			if level == 0 and not waiting and line >= end:	return line, 0
			#if waiting == '\n':		waiting = None
			for col,c in enumerate(self.lines[line]):
				if waiting:
					if c == waiting:	waiting = None
				else:
					if   c in '({[':	level += 1
					elif c in ')}]':	level -= 1
					elif c == "'":	waiting = "'"
					elif c == '"':	waiiing = '"'
					elif c == '#':	waiting = '\n'
					if level == 0 and not waiting and line >= end:	return line, col+1
			line += 1
		raise EOFError("the expression doesn't end in the current text")
	
	def change(self, location, oldsize, newcontent):
		''' change a zone in the text, keeping the internal structure good 
			return the line the change's end is on
		'''
		line, col = location
		if line == len(self.lines):
			self.lines.extend(splitlines(newcontent))
			return len(self.lines)-1
		# find the old line for old size
		s = -col
		l = line
		while l < len(self.lines) and s <= oldsize:
			s += len(self.lines[l])
			l += 1
		l -= 1
		# get the new lines, replacing the former
		script = self.lines[line][:col] + newcontent + self.lines[l][len(self.lines[l])+oldsize-s:]
		self.lines[line:l+1] = splitlines(script)
		# invalidate further backups
		self.backups[self.lastbackup(line)+1:] = []
		return l
	
	def execchange(self, location, oldsize, newcontent):
		return self.execute(self.change(location, oldsize, newcontent)+1)
	
	def transformcode(self, code, stop, offset):
		''' transform a code object to return the part to execute until the stop line 
			offset is the line offset with the current code line numbers (and therefore the start line number)
			stop is the line number the code stop juste before
		'''
		# remove instructions that doesn't end before the stop line
		bytecode = Bytecode.from_code(code)[:-2]
		i = 0
		while i < len(bytecode):
			instr = bytecode[i]
			if isinstance(instr, Instr) and instr.lineno+offset > stop:	break
			i += 1
		# process the code   NOTE this can be very dependent to the python version, current is 3.7
		code = Bytecode(bytecode[:i])
		code.insert(0, Instr('LOAD_NAME', 'RESULTS'))
		
		# make it return the last stack value if there is (remove the loading of None that is instead)
		if len(code) and isinstance(code[-1], Instr) and code[-1].name == 'POP_TOP':
			code[-1] = Instr('RETURN_VALUE')
		else: 
			code.append(Instr('LOAD_CONST', None))
			code.append(Instr('RETURN_VALUE'))
		
		# store temporary values
		reused = set()
		temploaded = []
		assigned = []
		stacksize = 0
		for i,instr in enumerate(code):
			if not isinstance(instr, Instr):	continue
			
			stacksize += instr.stack_effect()
			# store temporary values into results
			if instr.name.startswith('CALL_') or instr.name.startswith('BINARY_') or instr.name.startswith('BUILD_'):
				if i+1 < len(code) and isinstance(code[i+1], Instr) and code[i+1].name.startswith('STORE_'):
					varname = code[i+1].arg
					assigned.append((varname, instr.lineno))
					reused.update(temploaded)
					reused.discard(varname)
					temploaded = []
				else:
					code[i+1:i+1] = [
						Instr('DUP_TOP'),
						Instr('LOAD_CONST', instr.lineno-1+offset),
						Instr('MAP_ADD', stacksize),
						]
			# mark loaded variables as reused at next assignment
			if instr.name == 'LOAD_NAME':
				temploaded.append(instr.arg)
		
		stacksize = 0
		for instr in code:
			print(stacksize, instr)
			if isinstance(instr, Instr):
				stacksize += instr.stack_effect()
								
		# automatic backup between statements
		lastline = 1
		stacksize = 0
		used = set()
		i = 0
		while i < len(code):
			instr = code[i]
			if not isinstance(instr, Instr) or instr.lineno is None:
				i += 1
				continue
			# statement ends when the stack is empty and the line changes
			if used and instr.lineno != lastline and stacksize <= 1:
				block = [
					Instr('LOAD_CONST', self._insbackup),
					Instr('LOAD_CONST', instr.lineno-1+offset),
					Instr('LOAD_CONST', set(used)),
					Instr('LOAD_CONST', vars),
					Instr('CALL_FUNCTION', 0),
					Instr('CALL_FUNCTION', 3),
					Instr('POP_TOP'),
					]
				code[i:i] = block
				used = set()
				i += len(block)
			if instr.name == 'LOAD_NAME' or instr.name == 'STORE_NAME':		
				used.add(instr.arg)
			stacksize += instr.stack_effect()
			lastline = instr.lineno
			i += 1
		
		nprint(code)
		return code.to_code(), reused

	def _insbackup(self, stop, used, vars):
		t = time()
		if t - self.starttime > self.backupstep:
			self.starttime = t
			
			# get the initial environment
			backi = self.lastbackup(stop)
			backline, backenv = self.backups[backi]
			
			# create a copy of the variables used
			env = copyvars(vars, used)
			# insert
			if backline == stop:
				self.backups[backi] = (stop, env)
			else:
				self.backups.insert(backi+1, (stop, env))

def copyvars(vars, deep=(), memo=None):
	''' copy a dinctionnary of variables, with only the variables present in deep that are deepcopied '''
	if memo is None:	memo = {}
	new = copy(vars)
	for name in deep:
		if name in vars:
			new[name] = deepcopy(vars[name], memo)
	return new


def splitlines(text):
	i = 0
	l = len(text)
	while i < l:
		n = text.find('\n', i)
		if n<0:	
			yield text[i:]
			return
		yield text[i:n+1]
		i = n+1

def textsize(text, tab=4):
	l = c = 0
	for char in text:
		if char == '\n':
			l += 1
			c = 0
		elif char == '\t':
			c += tab
			c -= c%tab
		else:
			c += 1
	return l,c
		
def textposition(text, pos, tab=4):
	''' string index of the given text position (line,column) '''
	l = c = 0
	for i,char in enumerate(text):
		if (l,c) >= pos:	break
		if char == '\n':
			l += 1
			c = 0
		elif char == '\t':
			c += tab
			c -= c%tab
		else:
			c += 1
	return i
