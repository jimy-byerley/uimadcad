from __future__ import annotations

from copy import deepcopy
from functools import partial
from dataclasses import dataclass
from bisect import bisect_right
import traceback

from pnprint import nprint

from . import ast


class InterpreterError(Exception):	pass


class Interpreter:
	''' this class execute the uimadcad file code and exposes the resulting scope, errors and code analysis 
	
		Since the code might not have changed much between two executions, executing the code actually performs a lot of caching and reexecute only the changed portions of code and the code that depends on it
	'''
	filename: str
	source: str
	ast: AST
	scopes: dict[str, dict[str, object]]
	definitions: dict[str, dict[str, AST]]
	locations: list[Located]
	usages: dict[str, Usage]
	exception: Exception
	
	def __init__(self, filename:str):
		self.cache = {}
		self.filename = filename
		self.previous = {}
		self.ast = {}
		self.scopes = {}
		self.identified = {}
		self.definitions = {}
		self.locations = []
		self.usages = {}
		# TODO reimplement interpreter early stop
		# self.stops = []
		self.exception = None
	
	def execute(self, source:str, step:callable):
		''' execute the code in the given string
		
			- this is a lazy execution where all previous result from previous execution are reused when possible
			- step is a callback executed regularly during execuction:
				
				step(scope: str, current_line: int, total_lines: int)
		'''
		# nprint('cache', self.cache)
		
		self.exception = None
		self.source = source
		
		code = self.ast = ast.parse(source).body
		# # TODO: parcimonize flattened blocks instead of statements
		# code = list(ast.flatten(code))
		original_definitions = ast.locate(code, self.filename)
		code = ast.parcimonize(self.cache, self.filename, (), code, self.previous)
		# code = list(ast.flatten(code, filter=lambda node: 
			# type(node) in ast.flatten_selection and haslocation(node)))
		code = list(code)
		code = list(ast.steppize(code, self.filename))
		code = ast.report(code, self.filename)
		self.usages = ast.usage(code, self.filename)
		
		altered_definitions = ast.locate(code, self.filename)
		for name, scope in original_definitions.items():
			altered_definitions.get(name, scope).update(scope)
		self.definitions = altered_definitions
		
		# TODO: add stop points
		
		# build a sorted location index
		locations = []
		for scope, definitions in self.definitions.items():
			for name, node in definitions.items():
				if haslocation(node):
					located = node
				elif isinstance(node, ast.Assign) and haslocation(node.value):
					located = node.value
				else:
					continue
				locations.append(Located(
					node,
					# range(node.position, node.end_position), 
					# TODO: optimize this position search
					range(
						ast.textpos(source, (located.lineno, located.col_offset)), 
						ast.textpos(source, (located.end_lineno, located.end_col_offset)),
						),
					scope, 
					name,
					))
		self.locations = sorted(locations, key=lambda item: item.range.start)
		
		code = ast.Module(code, type_ignores=[])
		ast.fix_locations(code)
		# print(ast.dump(code, indent=4))
		bytecode = compile(code, self.filename, 'exec')
		module = dict(
			_madcad_global_cache = partial(ast.global_cache, self.cache),
			_madcad_copy = deepcopy,
			_madcad_scopes = self.scopes,
			_madcad_step = step,
			_madcad_vars = vars,
			)
		
		try:
			exec(bytecode, module, module)
		except Exception as err:
			stops = {}
			for frame, line in traceback.walk_tb(err.__traceback__):
				name = frame.f_code.co_name
				if name == '<module>':
					name = self.filename
				stops[name] = line
				# TODO: use a try finally for the scope capture
			self.usages = ast.usage(code.body, self.filename, stops=stops)
			self.exception = err
			
		print('caches', self.cache.keys())
		nprint('scopes', repr(self.scopes))
		nprint('definitions', self.definitions)
		self.identified = {
			id(self.scopes[located.scope][located.name]): located  
			for located in self.locations
			if located.scope in self.scopes
			and located.name in self.scopes[located.scope]}
		nprint('identified', self.identified)
			
	def names_crossing(self, area:range) -> Iterator[Located]:
		''' yield variables with text range crossing the given position range '''
		stop = bisect_right(self.locations, area.stop, key=lambda item: item.range.start)
		for i in reversed(range(0, stop)):
			item = self.locations[i]
			if item.range.start in area or item.range.stop in area:
				yield item
			else:
				break
					
	def name_at(self, position:int) -> Located:
		''' find the variable with the smallest text range enclosing the given position '''
		stop = bisect_right(self.locations, position, key=lambda item: item.range.start)
		for i in reversed(range(0, stop)):
			item = self.locations[i]
			if position in item.range:
				return item
		raise IndexError('no node at the given position')
	
	def scope_at(self, position:int) -> Located:
		''' find the scope with the smallest text range enclosing the given position '''
		stop = bisect_right(self.locations, position, key=lambda item: item.range.start)
		for i in reversed(range(0, stop)):
			item = self.locations[i]
			if position in item.range and isinstance(item.node, ast.FunctionDef):
				return item.scope+'.'+item.name
		return self.filename
	
	def interrupt(self):
		# TODO
		pass

@dataclass
class Located:
	node: AST
	range: range
	scope: str
	name: str

	
def haslocation(node):
	return ( 
		getattr(node, 'lineno', 0) and getattr(node, 'end_lineno', 0) 
		and getattr(node, 'col_offset', 0) and getattr(node, 'end_col_offset', 0) 
		)
		
def test_interpreter():
	indev
