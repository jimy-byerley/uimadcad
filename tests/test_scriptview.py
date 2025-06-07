from uimadcad.scriptview import SubstitutionIndex
from pnprint import nprint

def test_substitution_index():
	def assert_eq(name, a, b):
		assert a == b, (name,':', a, 'should be', b)
	
	def check():
		for dst, src in enumerate(reference):
			if src is None:
				continue
			assert_eq(src, index.upgrade(src), dst)
			assert_eq(dst, index.downgrade(dst), src)
	
	def test(position, remove=0, add=0):
		print()
		index.substitute(position, remove, add)
		reference[position-remove:position] = [None]*add
		nprint('src', index._src)
		nprint('dst', index._dst)
		check()
		
	index = SubstitutionIndex()
	reference = list(range(30))
	
	# test our check
	check()
	
	# test reliability of the resulting index
	test(10, remove=2)
	test(16, remove=2)
	test(10, remove=2)
	test(9, remove=2)
	
	test(10, add=2)
	test(9, add=2)
	test(8, add=2)
	test(20, remove=2, add=2)

	index = SubstitutionIndex()
	reference = list(range(30))
	
	# test fusion of edited zones
	test(10, add=1)
	test(11, add=1)
	test(12, add=2)
	test(14, add=2)
	assert index.steps() == 1
	test(17, add=1)
	assert index.steps() == 2
