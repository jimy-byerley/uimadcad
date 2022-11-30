import ast, inspect
from types import ModuleType
from copy import copy, deepcopy
from time import time
from madcad.mathutils import bisect
from madcad.nprint import nprint


class InterpreterError(Exception):	pass

class Interpreter:
	''' script interpreter using caching '''
	backupstep = 0.2

	def __init__(self, text='', env=None, extract=None, name='custom-interpreter'):
		self.name = name	# module name of the interpreter
		self.text = text	# complete text edited
		self.extract = extract or (lambda p: p)	# extractor of the ast part to execute
		
		self.part = None			# last ast parts executed
		self.part_altered = None	# last ast actually executed, with all alterations meant to retrieve data
		
		self.target = 0
		self.current = env or {}		# current env (after last execution)
		self.reused = set()
		self.neverused = set()
		self.ids = {}			# object names indexed by their id
		self.locations = {}		# objects location intervals indexed by object name
		
		self.backups = [(0, self.current)]						# local variables used
		self.ast = ast.Module(body=[], type_ignores=[])		# last complete ast compiled
		self.ast_end = 0							# end position of the last ast in the text
	
	def change(self, position, oldsize, newcontent):
		''' change a part of the text, invalidating all backups and AST statements after position '''
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
	
	def execute(self, target=-1, autobackup=False, onstep=None):
		''' execute the code from last backups to the target string position '''
		if target < 0:	target += len(self.text)
		self.target = target
		
		# rebuild AST to target
		if target > self.ast_end:
			part = self.text[self.ast_end:]
			try:
				addition = ast.parse(part, self.name)
			except SyntaxError as err:
				raise InterpreterError(err)
			astannotate(addition, part)
			endloc = textloc(self.text, self.ast_end)
			astshift(addition, (endloc[0]-1, endloc[1]), self.ast_end)
			self.ast.body.extend(addition.body)
			self.ast_end += len(part)
		
		# get ast subnode if an extractor is defined
		scope = self.extract(self.ast)
		if not scope:	raise ValueError('unable to extract the current scope from the ast')
		
		# get the code to execute from the last backup
		backpos, backenv = self.backups[self.lastbackup(target)]
		ast_current = astatpos(scope, backpos)
		ast_target = astatpos(scope, target)
		# ast until target
		part = scope.body[ast_current:ast_target]
		# pick possible backup points
		stops = set(stmt.end_position  for stmt in part)
		# remaining expressions before target in the AST
		if ast_target < len(scope.body):
			part += astexpruntil(scope.body[ast_target], target)
		
		self.part = part = ast.Module(body=part, type_ignores=[])
		processed, locations = self.process(part, backenv.keys())
		env = copy(backenv)
		
		error = None
		if autobackup:
			
			starttime = time()
			for i, stmt in enumerate(processed.body):
				code = compile(ast.Module(
									body=[stmt], 
									type_ignores=[]), 
								self.name, 
								'exec')
				
				# execute the code
				try:
					exec(code, env)
				except Exception as err:
					error = err
					break
					
				if onstep:
					onstep(i/len(processed.body))
				
				# autobackup if this is between 2 statements
				if stmt.end_position in stops and time() - starttime > self.backupstep:
					self.backups[self.lastbackup(stmt.position)+1
								:self.lastbackup(target)+1] = [(stmt.end_position, copy(env))]
					starttime = time()
				
		else:
			code = compile(processed, self.name, 'exec')
			
			# execute the code
			try:
				exec(code, env)
			except Exception as err:
				error = err
				pass
		
		# publish results
		self.part_altered = processed
		self.current = env
		for name,obj in self.locations.items():
			if name not in locations and name in env:
				locations[name] = obj
		self.locations = locations
		self.ids = {id(obj): name	for name,obj in env.items()}
		
		used, reused = varusage(part)
		self.used = used
		self.neverused |= used
		self.neverused -= reused
		
		if error:	
			raise InterpreterError(error)
	
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
											'return', 
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
				elif isinstance(node, (ast.ListComp, ast.DictComp, ast.SetComp, ast.GeneratorExp, ast.stmt)) and not isinstance(node, ast.Expr):
					return
				# capture sub expressions
				elif isinstance(node, (ast.expr, ast.Expr)):
					astpropagate(node, capture)
				# other node types are not relevant for capture
			
			# recursive replacement only for children
			def descend(node):
				if isinstance(node, (ast.ListComp, ast.DictComp, ast.SetComp, ast.GeneratorExp, ast.stmt)) and not isinstance(node, ast.Expr):
					return
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
		for node in ast.walk(self.ast):		# TODO: utiliser un parcours conditionnel pour eviter d'entrer dans les sections de definitions (classes fonctions)
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
		
		# get function definition
		funcname = callnode.func.id
		defnode = self.locations[funcname]
		
		# create the start state for the function scope
		self.execute(callnode.position)
		env = copy(self.current)
		
		# pass arguments to a replacement function
		f = env[funcname]
		env[funcname] = lambda *args, **kwargs: (args, kwargs)
		code = compile(ast.Expression(callnode), self.name, 'eval')
		try:
			args, kwargs = eval(code, env, {})
		except Exception as err:
			raise InterpreterError(err)
		env[funcname] = f
		# put arguments in env
		binding = inspect.signature(f).bind(*args, **kwargs)
		binding.apply_defaults()
		env.update(binding.arguments)
		
		def extract(part):
			current = self.extract(part)
			for node in reversed(current.body):
				if isinstance(node, ast.FunctionDef) and node.name == funcname:
					return node
			if current is not part:
				for node in reversed(part.body):
					if isinstance(node, ast.FunctionDef) and node.name == funcname:	
						return node
		
		# change the current context
		it = Interpreter(
					text=self.text, 
					env=env, 
					#zone=[self.text.rfind('\n', 0, defnode.body[0].position)+1, defnode.end_position],
					name=funcname,
					extract=extract,
					)
		it.locations = copy(self.locations)
		it.ast = self.ast
		return it, callnode, defnode


def copyvars(vars, deep=(), memo=None):
	''' copy a dictionnary of variables, with only the variables present in deep that are deepcopied '''
	if memo is None:	memo = {}
	new = copy(vars)
	for name in deep:
		if name in vars:
			new[name] = deepcopy(vars[name], memo)
	return new

def varusage(node):
	''' return two set of variable names: those used (read or write) in the given ast tree, and those only read '''
	used = set()
	reused = set()
	def use(node):
		if isinstance(node, ast.Assign):
			astpropagate(node, reuse)
			for target in node.targets:
				if isinstance(target, ast.Name):
					used.add(target.id)
					reused.discard(target.id)
		else:
			astpropagate(node, use)
	def reuse(node):
		if isinstance(node, ast.Name): 
			used.add(node.id)
			if isinstance(node.ctx, ast.Load):
				reused.add(node.id)
		else:
			astpropagate(node, reuse)
	astpropagate(node, use)
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
		if isinstance(node, ast.keyword):
			node.position, node.end_position = node.value.position, node.value.end_position
		elif isinstance(node, (ast.Num, ast.Str, ast.Constant)):
			i = node.position
			if isinstance(node, ast.Constant) and isinstance(node.value, str) or isinstance(node, ast.Str):
				marker = text[i]
				if text[i:i+3] == 3*marker:
					marker = 3*marker
				node.end_position = text.find(marker, i+len(marker)) + len(marker)
			elif isinstance(node, ast.Constant) and node.value in {None, True, False}:
				node.end_position = node.position + len(str(node.value))
			else:
				while i < len(text) and text[i] in '0123456789+-e.rufbx':	i+=1
				node.end_position = i
		
		# generic retreival from the last child
		elif hasattr(node, 'position'):
			if not hasattr(node, 'end_position'):
				node.end_position = node.position
			for child in ast.iter_child_nodes(node):
				if hasattr(child, 'end_position'):
					node.end_position = max(node.end_position, child.end_position)
		
		if isinstance(node, ast.Attribute):
			i = node.end_position + len(node.attr)
			while i < len(text) and text[i].isalnum():	i+=1
			node.end_position = i
		elif isinstance(node, (ast.Subscript, ast.List, ast.ListComp)):
			node.end_position = text.find(']', node.end_position)+1
		elif isinstance(node, (ast.Dict, ast.Set, ast.DictComp, ast.SetComp)):
			node.end_position = text.find('}', node.end_position)+1
		elif isinstance(node, (ast.expr, ast.Tuple)) and not isinstance(node, (ast.Constant, ast.Num)):
			start = node.position
			if not isinstance(node, (ast.Call, ast.Tuple)):
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
			return i
		if hasattr(statement, 'end_position') and statement.end_position > pos:
			return i
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
