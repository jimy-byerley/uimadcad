from ast import *
from collections import Counter
from itertools import chain
from functools import partial


def process(code):
	code = annotate(code)
	ios = usage(code)
	code = parcimonize(code)
	code = flatten(code)
	code = steppize(code)
	complete(code)
	vars = locate(code)

def parcimonize(cache: dict, scope: str, args: list, code: iter, previous: dict) -> iter:
	''' make a code lazily executable by reusing as much previous results as possible '''
	assigned = Counter()
	changed = set()
	
	if isinstance(code, str):
		code = parse(code)
	if isinstance(code, Module):
		code = code.body
	code = iter(code)
	
	# new ast body
	yield from _scope_init(scope, args)
	for node in code:
		# find inputs and outputs of this statement
		deps = list(dependencies(node))
		provided = list(results(node))
		
		if not provided: 
			yield node
			continue
		
		# update the number of assignments to provided variables
		assigned.update(provided)
		# cache key for this statement
		key = '{}{}'.format(provided[0], assigned[provided[0]])
		# check if the node code or dependencies has changed
		if scope not in previous:
			previous[scope] = {}
		previous = previous[scope]
		
		if not equal(previous.get(key), node) or any(dep in changed  for dep in deps):
			# count all depending variables as changed
			changed.update(provided)
			# void cache of changed statements
			if scope in cache:
				for backups in cache[scope].values():
					backups.pop(key, None)
				if not cache[scope]:
					cache.pop(scope)
					
		previous[key] = node
		
		# functions are caching in separate scopes
		if isinstance(node, FunctionDef):
			yield _parcimonize_func(cache, scope, node, key, previous)
		
		# an expression assigned is assumed to not modify its arguments
		elif isinstance(node, Assign):
			yield from _parcimonize_assign(key, node)
		
		# an expression without result is assumed to be an inplace modification
		# a block cannot be splitted because its bodies may be executed multiple times or not at all
		elif isinstance(node, (Expr, If, For, While, Try, Match, With)):
			yield from _parcimonize_block(key, deps, node)
			
		# an expression returned is assumed to not modify its arguments
		elif isinstance(node, Return):
			yield from _parcimonize_return(key, node)
			
		# TODO: decide what to do when the target is a subscript
		
		else:
			yield node
	
def _scope_init(scope: str, args: list) -> list:
	# get the cache dictionnary for this scope
	return [Assign(
			targets = [Name('_madcad_cache', Store())],
				# all caches are coming from a global dictionnary of scope caches
			value = Call(
				Name('_madcad_global_cache', Load()),
				args = [
					Constant(scope),
					Tuple([Name(name, Load()) for name in args], Load()),
					],
				keywords = [],
				))]
				
def _parcimonize_func(
	cache: dict, 
	scope: str, 
	node: FunctionDef, 
	key: str, 
	previous: dict,
	) -> AST:
	# functions are caching in separate scopes
	subscope = scope + '.' + node.name
	# clear function caches if the function signature changed
	prev = previous.get(key)
	if not prev or node.name != prev.name or node.args != prev.args:
		cache.pop(subscope, None)
	
	args = node.args.posonlyargs + node.args.args + node.args.kwonlyargs
	if node.args.vararg:	args.append(node.args.vararg)
	if node.args.kwarg:     args.append(node.args.kwarg)
	# redefine the function with caching
	return FunctionDef(
		name = node.name,
		args = node.args,
		body = list(parcimonize(
			cache,
			# nested scope name
			scope = subscope,
			# arguments identifying the scope instance
			args = sorted([arg.arg   for arg in args]),
			code = node.body,
			previous = previous,
			)),
		decorator_list = node.decorator_list,
		)

def _parcimonize_return(key, node) -> list:
	# an expression returned is assumed to not modify its arguments
	r = _parcimonize_assign(key, Assign([Name('_return', Store())], node.value))
	r.append(Return(Name('_return', Load())))
	return r
		
def _parcimonize_assign(key, node) -> list:
	# an expression assigned is assumed to not modify its arguments
	return _cache_use(key, node.targets, [
		Assign(targets = [Name('_madcad_tmp', Store())], value = node.value), 
		_cache_set(key, value = Name('_madcad_tmp', Load())),
		Assign(targets = node.targets, value = Name('_madcad_tmp', Load())),
		])
		
def _parcimonize_block(key, deps, node) -> list:
	# an expression without result is assumed to be an inplace modification
	# a block cannot be splitted because its bodies may be executed multiple times or not at all
	outs = [Name(dep, Store())  for dep in deps]
	ins = [Name(dep, Load())  for dep in deps]
	return _cache_use(key, [Tuple(outs, Store())], [
		# run original code
		node,
		# cache results
		_cache_set(key, value = Tuple(ins, Load())),
		])

def _cache_use(key: hash, targets: list, generate: list) -> list:
	return [
		Assign([Name('_madcad_tmp', Store())], _cache_get(key)),
		If(
			# if cache is None
			test = Compare(
				left = Name('_madcad_tmp', Load()),
				ops = [Is()], 
				comparators = [Constant(value=None)]
				),
			# run the generating code
			body = generate,
			# retreive from cache
			orelse = [Assign(targets, Call(
				func = Name('_madcad_copy', Load()),
				args = [Name('_madcad_tmp', Load())],
				keywords = [],
				))],
			),
		]

def _cache_get(key) -> Expr:
	''' expression for accessing the cache value for this variable name in this function's scope '''
	return Call(Name('_madcad_copy', Load()), 
		args = [Call(
			Attribute(Name('_madcad_cache', Load()), 'get', Load()), 
			args = [Constant(key)],
			keywords = [],
			)],
		keywords = [],
		)
	
def _cache_set(key, value) -> Expr:
	''' statment for setting the given value to the given cache key '''
	return Assign(
		targets = [Subscript(
			value = Name('_madcad_cache', Load()), 
			slice = Constant(key), 
			ctx = Store())], 
		value = Call(
			Name('_madcad_copy', Load()),
			args = [value],
			keywords = [],
			),
		)

def global_cache(cache: dict, scope: str, args: tuple):
	if scope not in cache:
		cache[scope] = {}
	versions = cache[scope]
	args = ArgumentsKey(args)
	if args not in versions:
		versions[args] = {}
	return versions[args]
	
class ArgumentsKey(object):
	__slots__ = 'key', 'args'
	def __init__(self, args):
		self.key = 0
		for arg in args:
			try:	
				id = hash(arg)
			except TypeError:  
				id = 0
			self.key ^= id
		self.args = args
	def __hash__(self):
		return self.key
	def __eq__(self, other):
		return self.args == other.args
	def __repr__(self):
		return '{}({})'.format(self.__class__.__name__, ', '.join(repr(arg) for arg in self.args))
	
def test_parcimonize():
	from pnprint import nprint
	from dis import dis
	from copy import deepcopy
	
	filename = '<input>'
	code = '''
from math import sin, cos

def foo():
	a = 'a'
	return a
def bar(x, y):
	return x+y
def boo(x):
	return [x]
def fah(first, *args):
	first.extend(args)

e, f = 'e', 'f'
a = foo()
c = 'c'
{}
d = boo(c)
fah(d, c, e, f, foo())
s = dict(a=a, b=b, c=1)
s['c'] = 2

if True: pass
g = 0 if False else 1
		'''
	
	original_ast = parse(code.format('b = bar(a, c)'))
	original_bytecode = compile(original_ast, filename, 'exec')
	cache = {}
	previous = {}
	
	result = Module(
		list(parcimonize(cache=cache, scope=filename, args=(), code=original_ast, previous=previous)),
		type_ignores=[])
	nprint('\n'.join(dump(node) for node in result.body))
	complete(result)
	bytecode = compile(result, filename, 'exec')
	dis(bytecode)
	print('original', len(original_bytecode.co_code), 'parcimonized', len(bytecode.co_code))

	env = {}
	exec(bytecode, dict(
		_madcad_global_cache = partial(global_cache, cache),
		_madcad_copy = deepcopy,
		), env)
	nprint('env', env)
	nprint('cache', cache)
	assert env.get('b') == 'ac'
	assert env.get('d') == ['c', 'c', 'e', 'f', 'a']
	assert env.get('s') == {'a': 'a', 'b': 'ac', 'c': 2}

	second_ast = parse(code.format('b = bar(a, e)'))
	result = Module(
		list(parcimonize(cache=cache, scope=filename, args=(), code=second_ast, previous=previous)),
		type_ignores=[])
	complete(result)
	bytecode = compile(result, filename, 'exec')
	nprint('cache', cache)
	assert 'b1' not in cache['<input>'][ArgumentsKey(())]
	env = {}
	exec(bytecode, dict(
		_madcad_global_cache = partial(global_cache, cache),
		_madcad_copy = deepcopy,
		), env)
	nprint('cache', cache)
	assert 'b1' in cache['<input>'][ArgumentsKey(())]
	nprint('env', env)
	assert env.get('b') == 'ae'
	assert env.get('d') == ['c', 'c', 'e', 'f', 'a']
	assert env.get('s') == {'a': 'a', 'b': 'ae', 'c': 2}

def dependencies(node: AST) -> iter:
	''' yield names of variables a node depends on '''
	if isinstance(node, Name) and isinstance(node.ctx, Load):
		yield node.id
	elif isinstance(node, FunctionDef):
		for expr in chain(node.args.defaults, node.args.kw_defaults):
			yield from dependencies(expr)
	else:
		for child in iter_child_nodes(node):
			yield from dependencies(child)

def results(node: AST, inplace=False) -> iter:
	''' yield names of variables assigned by a node '''
	if isinstance(node, Name) and (isinstance(node.ctx, Store) or inplace):
		yield node.id
	elif isinstance(node, (FunctionDef, ClassDef)):
		yield node.name
	elif isinstance(node, (Import, ImportFrom)):
		for alias in node.names:
			yield alias.name
	elif isinstance(node, Return):
		yield 'return'
	elif isinstance(node, Assign):
		for target in node.targets:
			yield from results(target, inplace=True)
	elif isinstance(node, (Attribute, Subscript)):
		yield from results(node.value, inplace)
	elif isinstance(node, Call):
		arg = next(iter(node.args), None) or next(iter(node.keywords), None)
		if arg:
			yield from results(arg, inplace=True)
	else:
		for child in iter_child_nodes(node):
			yield from results(child)
			
def equal(a: AST, b: AST) -> bool:
	''' check that the operations performed by node a are equivalent to operations performed by node b '''
	if type(a) != type(b):	return False
	
	if isinstance(a, Name):
		return a.id == b.id
	elif isinstance(a, alias):
		return a.name == b.name and (a.asname or a.name) == (b.asname or b.name)
	elif isinstance(a, Constant):
		return a.value == b.value
	elif isinstance(a, Attribute):
		if a.attr != b.attr:	return False
	elif isinstance(a, (FunctionDef, AsyncFunctionDef, ClassDef)):
		if a.name != b.name:	return False
	elif isinstance(a, ImportFrom):
		if a.module != b.module:   return False
	elif isinstance(a, (Global, Nonlocal)):
		if set(a.names) != set(b.names):	return False
	
	for ca, cb in zip(iter_child_nodes(a), iter_child_nodes(b)):
		if not equal(ca, cb):
			return False
	return True

def flatten(tree: Module, nodes={Call, BoolOp, BinOp, Tuple, List, Return}) -> Module:
	''' process an AST to retreive its temporary values '''
	tree = deepcopy(tree)
	
	def tempname():
		i = 0
		while True:
			i += 1
			name = '_temp'+str(i)
			if name not in knownvars and name not in oldvars:	return name

	# recursive replacement procedure
	def capture(node):
		# do not capture local scopes
		if isinstance(node, (ListComp, DictComp, SetComp, GeneratorExp)):
			return
		# assignments are already captured in their assigned variables
		# TODO: decide what to do when the target is a subscript
		if isinstance(node, Assign):
			propagate(node, descend)
		# return values are captured as assignments to the return slot
		elif isinstance(statement, Return):
			propagate(node, descend)
			if type(node) in nodes:
				return [
					Assign([Name('_return', Store())], statement.value),
					Return(Name('_return', Load())),
					]
		# capture expressions
		elif isinstance(node, (BoolOp, BinOp, Call, Tuple, List)):
			# capture sub expressions only if there is no controlflow structure at our level
			if not isinstance(node, BoolOp):
				propagate(node, capture)
			name = tempname()
			if type(node) in nodes:
				return [
					Assign([Name(name, Store())], node),
					Name(name, Load()),
					]
		# capture statement bodies
		elif isinstance(node, (Module, If, For, While, Match, Try)):
			propagate(node.body, capture)
	
	# recursive replacement only for children
	def descend(node):
		if isinstance(node, (ListComp, DictComp, SetComp, GeneratorExp)):
			return
		if isinstance(node, Expr):
			propagate(node, capture)
	
	capture(tree)
	return tree

def propagate(node, process):
	''' apply process to node's children 
		if process returns something not None, it's used to inplace replace the child in the node
	'''
	for fieldname,value in iter_fields(node):
		if isinstance(value, AST):
			child = value
			replacement = process(child)
			if replacement:
				setattr(node, fieldname, replacement)
		elif isinstance(value, list):
			for i,child in enumerate(value):
				replacement = process(child)
				if replacement:
					value[i:i+1] = replacement

def usage(node) -> (set, set, set):
	''' return two set of variable names: those used (read or write) in the given ast tree, and those only read '''
	ro = set()  # only read
	wo = set() # only written
	rw = set()  # read and written
	for node in walk(node):
		if isinstance(node, Name):
			if isinstance(node.ctx, Load):
				if node.name in rw:
					pass
				elif node.name in wo:
					wo.discard(node.name)
					rw.add(node.name)
				else:
					ro.add(node.name)
			if isinstance(node.ctx, Store):
				if node.name in rw:
					pass
				elif node.name in ro:
					ro.discard(node.name)
					rw.add(node.name)
				else:
					wo.add(node.name)
	return ro, wo, rw

def complete(parent):
	for node in walk(parent):
		node.lineno = getattr(node, 'lineno', 0)
		node.col_offset = getattr(node, 'col_offset', 0)
	
	# print(complete, type(parent), getattr(parent, 'lineno', None))
	# for name, value in iter_fields(parent):
	# 	if isinstance(value, (stmt, expr)):
	# 		complete(value)
	# 		parent.lineno = min(value.lineno, getattr(parent, 'lineno', value.lineno))
	# 	if isinstance(value, list):
	# 		for node in value:
	# 			complete(node)
				
def annotate(tree, text):
	''' enrich nodes by useful informations, such as start-end text position of tokens
		currently
			* position
			* end_position
	'''	
	# assigne a text position to each node
	currentloc = (1,0)
	currentpos = 0
	for node in walk(tree):
		if hasattr(node, 'lineno'):
			target = astloc(node)
			node.position = advancepos(text, target, currentpos, currentloc)
			currentloc = target
			currentpos = node.position
	
	
	# find the end of each node
	def recursive(node):
		# process subnodes first
		astpropagate(node, recursive)
		
		# node specific length calculation
		if isinstance(node, Name):
			node.end_position = node.position + len(node.id)
		if isinstance(node, keyword):
			node.position, node.end_position = node.value.position, node.value.end_position
		elif isinstance(node, (Num, Str, Constant)):
			i = node.position
			if isinstance(node, Constant) and isinstance(node.value, str) or isinstance(node, Str):
				marker = text[i]
				if text[i:i+3] == 3*marker:
					marker = 3*marker
				node.end_position = text.find(marker, i+len(marker)) + len(marker)
			elif isinstance(node, Constant) and node.value in {None, True, False}:
				node.end_position = node.position + len(str(node.value))
			else:
				while i < len(text) and text[i] in '0123456789+-e.rufbx':	i+=1
				node.end_position = i
		
		# generic retreival from the last child
		elif hasattr(node, 'position'):
			if not hasattr(node, 'end_position'):
				node.end_position = node.position
			for child in iter_child_nodes(node):
				if hasattr(child, 'end_position'):
					node.end_position = max(node.end_position, child.end_position)
		
		if isinstance(node, Attribute):
			i = node.end_position + len(node.attr)
			while i < len(text) and text[i].isalnum():	i+=1
			node.end_position = i
		elif isinstance(node, (Subscript, List, ListComp)):
			node.end_position = text.find(']', node.end_position)+1
		elif isinstance(node, (Dict, Set, DictComp, SetComp)):
			node.end_position = text.find('}', node.end_position)+1
		elif isinstance(node, (expr, Tuple)) and not isinstance(node, (Constant, Num)):
			start = node.position
			if not isinstance(node, (Call, Tuple)):
				start -= 1
				while start > 0 and text[start] in ' \t\n':	start -= 1
				if start >= 0 and text[start] != '(':
					return
			end = node.end_position
			if end < len(text) and text[end] == '(':	end += 1
			while end < len(text) and text[end] in ' \t\n,':	end += 1
			if end >= len(text) or text[end] != ')':
				return
			node.position = start
			node.end_position = end+1
		elif isinstance(node, alias) and node.name == '*':
			node.end_position = node.position + len(node.name)
	
	recursive(tree)


				
def shift(tree, loc, pos):
	''' shift the position attributes of the tree nodes, as if the parsed text was appent to an other string '''
	def recursive(node):
		if hasattr(node, 'lineno'):			
			node.lineno += loc[0]
			if hasattr(node, 'end_lineno'):		node.end_lineno += loc[0]
			if hasattr(node, 'position'):		node.position += pos
			if hasattr(node, 'end_position'):	node.end_position += pos
			if node.lineno == 0:
				node.col_offset += loc[1]
				if hasattr(node, 'end_col_offset'):		node.end_col_offset += loc[1]
		propagate(node, recursive)
	recursive(tree)

def _advancepos(text, loc, startpos=0, startloc=(1,0), tab=1):
	''' much like textpos but starts from a point (with startpos and startloc) and can advance forward or backward '''
	i = startpos
	l,c = startloc
	while l < loc[0]:	
		i = text.find('\n', i)+1
		l += 1
	while l > loc[0]:
		i = text.rfind('\n', 0, i)
		l -= 1
	i = text.rfind('\n', 0, i)+1
	i += loc[1]
	return i
		
	
		
def _atpos(tree, pos):
	''' get the AST node from a list of nodes, that contains the given text location '''
	for i,statement in enumerate(tree.body):
		if statement.position >= pos:		
			return i
		if getattr(statement, 'end_position', 0) > pos:
			return i
	return len(tree.body)
		
def _loc(node):
	''' text location of an AST node '''
	return (node.lineno, node.col_offset)

def textpos(text, loc, tab=1):
	''' string index of the given text location (line,column) '''
	i = 0
	l, c = 1, 0
	while l < loc[0]:	
		i = text.find('\n', i)+1
		l += 1
	while c < loc[1]:
		if text[i] == '\t':	c += tab
		else:				c += 1
		i += 1
	return i

def textloc(text, pos, tab=1, start=(1,0)):
	''' text location for the given string index '''
	if pos < 0:	pos += len(text)
	l, c = start
	if pos > len(text):	
		raise IndexError('the given position is not in the string')
	for i,char in enumerate(text):
		if i >= pos:	break
		if char == '\n':
			l += 1
			c = 1
		elif char == '\t':
			c += tab
			c -= c%tab
		else:
			c += 1
	return (l,c)
	
def normalizeindent(text):
	''' remove the indentation level of the first line from all lines '''
	indent = None
	for i,c in enumerate(text):
		if not c.isspace():
			indent = text[:i]
			break
	if indent:
		return text[len(indent):].replace('\n'+indent, '\n')
	elif indent is not None:
		return text
	else:
		return ''
	
def _expruntil(tree, pos):
	remains = []
	def recur(node):
		if isinstance(node, expr) and node.end_position <= pos:
			if isinstance(node, Name) and not isinstance(node.ctx, Load):	return
			remains.append(node)
		else:
			for child in iter_child_nodes(node):
				recur(child)
	recur(tree)
	return [Expr(r, 
				lineno=r.lineno, 
				col_offset=r.col_offset,
				position=r.position, 
				end_position=r.end_position) 	
			for r in remains]
