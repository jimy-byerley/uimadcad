import ast, inspect
from types import ModuleType
from copy import copy, deepcopy
from time import time
from madcad.mathutils import bisect
from nprint import nprint


class InterpreterError(Exception):	pass

class Interpreter:
	''' script interpreter using caching '''
	# TODO: make this class thread-safe
	backupstep = 0.2

	def __init__(self, text='', env=None, zone=None, name='custom-interpreter'):
		self.name = name
		self.backups = [(0,env or {})]	# local variables used
		self.text = text
		self.zone = zone or [0, len(text)]
		self.ast = ast.Module(body=[], type_ignores=[])
		self.ast_end = self.zone[0]
		self.altered_ast = None
		
		self.target = 0
		self.current = {}	# current env (after last execution)
		self.reused = set()
		self.neverused = set()
		self.ids = {}	# object names indexed by their id
		self.locations = {}	# objects location intervals indexed by object name
	
	def change(self, position, oldsize, newcontent):
		''' change a part of the text, invalidating all backups and AST statements after position '''
		if position < self.zone[0] or self.zone[1] < position:
			raise IndexError('the given position is not editable')
		
		oldsize = min(oldsize, len(self.text))
		self.zone[1] += len(newcontent) - oldsize
		print('change', self.zone, oldsize, len(newcontent))
		self.text = self.text[:position] + newcontent + self.text[position+oldsize:]
		
		# get the position in the AST (the position of the line beginning, because change occuring on an existing line can change its semantic)
		i = astatpos(self.ast, self.text.rfind('\n', 0, position)+1)
		if i < len(self.ast.body):
			self.ast_end = self.ast.body[i-1].end_position if i else 0
			self.ast.body[i:] = []
			self.backups[self.lastbackup(self.ast_end)+1:] = []
		elif self.ast.body:
			self.ast_end = self.ast.body[-1].end_position
		else:
			self.ast_end = 0
		
	def lastbackup(self, position):
		''' get the index of the last env backup before position '''
		i = bisect(self.backups, position, key=lambda backup: backup[0])
		if i == len(self.backups) or self.backups[i][0] > position:	i -= 1
		return i
	
	def execute(self, target=-1, autobackup=False):
		''' execute the code from last backups to the target string position '''
		if target < 0:	target += self.zone[1]
		self.target = target
		
		# rebuild AST to target
		if target > self.ast_end:
			part = normalizeindent(self.text[self.ast_end:self.zone[1]])
			try:
				addition = ast.parse(part, self.name)
			except SyntaxError as err:
				raise InterpreterError(err)
			astannotate(addition, part)
			endloc = textloc(self.text, self.ast_end)
			astshift(addition, (endloc[0]-1, endloc[1]), self.ast_end)
			self.ast.body.extend(addition.body)
			self.ast_end += len(part)
		
		# get the code to execute from the last backup
		backpos, backenv = self.backups[self.lastbackup(target)]
		ast_target = astatpos(self.ast, target)
		# ast until target
		part = self.ast.body[astatpos(self.ast, backpos):ast_target]
		# remaining expressions before target in the AST
		if ast_target < len(self.ast.body):
			part += astexpruntil(self.ast.body[ast_target], target)
		part = ast.Module(body=part, type_ignores=[])
		
		processed, locations = self.process(part, backenv.keys())
		
		if autobackup:
			env = copyvars(backenv, locations.keys())
			
			starttime = time()
			for stmt in processed.body:
				code = compile(ast.Module(
									body=[stmt], 
									type_ignores=[]), 
								self.name, 
								'exec')
				
				# execute the code
				try:
					exec(code, env)
				except Exception as err:
					raise InterpreterError(err)
				
				# autobackup
				t = time()
				if t - starttime > self.backupstep:
					self.backups[self.lastbackup(stmt.position)+1
								:self.lastbackup(target)+1] = [(stmt.end_position, copyvars(env, locations.keys()))]
					starttime = time()
				
		else:
			code = compile(processed, self.name, 'exec')
			env = copyvars(backenv, locations.keys())
			
			# execute the code
			try:
				exec(code, env)
			except Exception as err:
				raise InterpreterError(err)
		
		# publish results
		self.altered_ast = processed
		self.current = env
		for name,obj in self.locations.items():
			if name not in locations and name in env:
				locations[name] = obj
		self.locations = locations
		self.ids = {id(obj): name	for name,obj in env.items()}
		
		used, reused = varusage(processed)
		self.used = used
		self.neverused |= used
		self.neverused -= reused
	
	def process(self, tree, oldvars):
		''' process an AST to retreive its temporary values 
			the returned AST can be executed, but doesn't represent anymore the last code, it represents the new code, doing exactly the same thing, but keeping temporary values in additional variables
		'''
		tree = deepcopy(tree)
		knownvars = {}
		
		def tempname():
			i = 0
			while True:
				i += 1
				name = 'temp'+str(i)
				if name not in knownvars and name not in oldvars:	return name
		
		i = 0
		while i < len(tree.body):
			statement = tree.body[i]
			begin = []
			
			if isinstance(statement, ast.Return):
				statement = tree.body[i] = ast.Assign(
										[ast.Name(
											'__return__', 
											ast.Store(),
											lineno=statement.lineno,
											col_offset=statement.col_offset,
											)], 
										statement.value,
										lineno=statement.lineno,
										col_offset=statement.col_offset,
										position=statement.position,
										end_position=statement.end_position,
										)
			
			# recursive replacement procedure
			def capture(node):
				# capture the whole assignment (name included)
				if isinstance(node, ast.Assign):
					astpropagate(node, descend)
					for target in node.targets:
						if isinstance(target, ast.Name):
							knownvars[target.id] = node
				elif isinstance(node, (ast.FunctionDef, ast.ClassDef)):
					knownvars[node.name] = node
				# capture expressions
				elif isinstance(node, (ast.BoolOp, ast.BinOp, ast.Call, ast.Tuple, ast.List)):
					# capture sub expressions only if there is no controlflow structure at our level
					if isinstance(node, (ast.BinOp, ast.Call, ast.Tuple, ast.List)):
						astpropagate(node, capture)
					
					psts = {'lineno':node.lineno, 'col_offset':node.col_offset, 'position':node.position, 'end_position':node.end_position}
					name = tempname()
					knownvars[name] = node
					begin.append(ast.Assign(
						[ast.Name(name, ast.Store(), **psts)], 
						node, 
						**psts))
					return ast.Name(name, ast.Load(), **psts)
				# capture sub expressions
				elif isinstance(node, (ast.expr, ast.Expr)):
					astpropagate(node, capture)
				# other node types are not relevant for capture
			
			# recursive replacement only for children
			def descend(node):
				astpropagate(node, capture)
			
			capture(statement)
			#tree.body.insert(i+1, ast.Expr(value=ast.Call(
							#func=ast.Name(id='_autobackup', ctx=ast.Load(), **placement), 
							#args=[	ast.Constant(value=statement.end_position, **placement), 
									#ast.Constant(value=list(knownvars), **placement),
									#ast.Call(
										#func=ast.Name(id='vars', ctx=ast.Load(), **placement), 
										#args=[], 
										#keywords=[],
										#**placement),
									#],
							#keywords=[],
							#**placement), **placement))
			tree.body[i:i] = begin
			i += len(begin)+1
		
		return tree, knownvars
		
	def enter(self, position):
		''' return a new interpreter to edit the inside of a function defined in this scope '''
		# find the function call node under the cursor (if there is)
		callnode = None
		for node in ast.walk(self.ast):
			if (	isinstance(node, ast.Call) 
				and	isinstance(node.func, ast.Name) 
				and	node.func.id in self.locations
				):
				if node.position <= position and position <= node.end_position and (	
						not callnode
					or	callnode.position <= node.position and node.end_position <= callnode.position
					):
					callnode = node
		# return if no matching function node under cursor
		if not callnode:
			raise ValueError('no function to enter')
		else:
			nprint('found', ast.dump(callnode))
		
		# get function definition
		funcname = callnode.func.id
		defnode = self.locations[funcname]
		
		# create the start state for the function scope
		self.execute(callnode.position)
		env = copy(self.current)
		
		# pass arguments
		f = env[funcname]
		env[funcname] = lambda *args, **kwargs: (args, kwargs)
		args, kwargs = eval(compile(
								ast.Expression(callnode), 
								self.name, 'eval'), env, {})
		env[funcname] = f
		env.update(inspect.signature(f).bind(*args, **kwargs).arguments)
		
		# change the current context
		it = Interpreter(
					text=self.text, 
					env=env, 
					zone=[self.text.rfind('\n', 0, defnode.body[0].position)+1, defnode.end_position],
					name=funcname,
					)
		it.locations = copy(self.locations)
		return it


def copyvars(vars, deep=(), memo=None):
	''' copy a dictionnary of variables, with only the variables present in deep that are deepcopied '''
	if memo is None:	memo = {}
	new = copy(vars)
	for name in deep:
		if name in vars:
			new[name] = deepcopy(vars[name], memo)
	return new

def varusage(node):
	used = set()
	reused = set()
	for child in ast.walk(node):
		if isinstance(child, ast.Name): 
			used.add(child.id)
			if isinstance(child.ctx, ast.Load):
				reused.add(child.id)
	return used, reused

def astpropagate(node, process):
	''' apply process to node's children 
		if process returns something not None, it's used to inplace replace the child in the node
	'''
	for fieldname,value in ast.iter_fields(node):
		if isinstance(value, ast.AST):
			child = value
			replacement = process(child)
			if replacement:
				setattr(node, fieldname, replacement)
		elif isinstance(value, list):
			for i,child in enumerate(value):
				replacement = process(child)
				if replacement:
					value[i] = replacement

def astannotate(tree, text):
	''' enrich nodes by useful informations, such as start-end text position of tokens
		currently
			* position
			* end_position
	'''	
	# assigne a text position to each node
	currentloc = (1,0)
	currentpos = 0
	for node in ast.walk(tree):
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
		if isinstance(node, ast.Name):
			node.end_position = node.position + len(node.id)
		elif isinstance(node, ast.Num):
			i = node.position
			while i < len(text) and text[i].isalnum():	i+=1
			node.end_position = i
		elif isinstance(node, ast.Attribute):
			i = node.position+1
			while i < len(text) and text[i].isalnum():	i+=1
			node.end_position = i
		
		# generic retreival from the last child
		elif hasattr(node, 'position'):
			if not hasattr(node, 'end_position'):
				node.end_position = node.position
			for child in ast.iter_child_nodes(node):
				if hasattr(child, 'end_position'):
					node.end_position = max(node.end_position, child.end_position)
		
		if isinstance(node, (ast.Call,ast.Tuple)):
			node.end_position = text.find(')', node.end_position)+1
			#print(node, node.position, node.end_position, text[node.position:node.end_position])
		elif isinstance(node, (ast.Subscript, ast.List)):
			node.end_position = text.find(']', node.end_position)+1
		
		#if isinstance(node, ast.expr) or isinstance(node, ast.stmt):
			#nprint('annotated', ast.dump(node), repr(text[node.position:node.end_position]))
	recursive(tree)
				
def astshift(tree, loc, pos):
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
		astpropagate(node, recursive)
	recursive(tree)

def advancepos(text, loc, startpos=0, startloc=(1,0), tab=1):
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
		
	
		
def astatpos(tree, pos):
	''' get the AST node from a list of nodes, that contains the given text location '''
	for i,statement in enumerate(tree.body):
		if statement.position >= pos:		
			return max(0, i)
		if hasattr(statement, 'end_position') and statement.end_position > pos:		
			return max(0, i)
	return len(tree.body)
		
def astloc(node):
	''' text location of an AST node '''
	return (node.lineno, node.col_offset)

def astinterval(node):
	return (node.position, node.end_position)
		
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
	
def astexpruntil(tree, pos):
	remains = []
	def recur(node):
		if isinstance(node, ast.expr) and node.end_position <= pos:
			if isinstance(node, ast.Name) and not isinstance(node.ctx, ast.Load):	return
			remains.append(node)
		else:
			for child in ast.iter_child_nodes(node):
				recur(child)
	recur(tree)
	return [ast.Expr(r, 
				lineno=r.lineno, 
				col_offset=r.col_offset,
				position=r.position, 
				end_position=r.end_position) 	
			for r in remains]
