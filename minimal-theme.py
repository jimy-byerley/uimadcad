import sys, os, shutil

def replicate(project, prefix, filter):
	if not os.path.exists(prefix):
		os.mkdir(prefix)
	for name in os.listdir(project):
		src = os.path.join(project,name)
		dst = os.path.join(prefix,name)
		if os.path.isdir(src):
			replicate(src, dst, filter)
		elif filter(name):
			print('  install', dst)
			shutil.copy(src, dst)
			
def checkname(name, allowed):
	radix, ext = os.path.splitext(name)
	if not (ext.startswith('.svg') or ext.startswith('.png')):
		return True
	if radix.endswith('-symbolic'):
		radix = radix[:-len('-symbolic')]
	if radix in allowed:
		return True
	return False
	

if __name__ == '__main__':
	command, names, project, prefix = sys.argv
	icons = set(open(names).read().split('\n'))
	
	replicate(project, prefix, lambda name: checkname(name, icons))
