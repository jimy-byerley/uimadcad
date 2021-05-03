from madcad import *

dint, dext, h = 16, 35, 8
detail = True

rint = dint/2
rext = dext/2
c = 0.1*h
w = 0.5*h
e = 0.12*(dext-dint)

axis = Axis(O,Z)
top = Wire([
	vec3(rext, 0, w-e), 
	vec3(rext, 0, w),
	vec3(rint, 0, w),
	vec3(rint, 0, w-e), 
	]) .segmented() .flip()
bevel(top, [1, 2], ('radius',c), resolution=('div',1))

bot = Wire([
	vec3(rint, 0, -w+e),
	vec3(rint, 0, -w),
	vec3(rext, 0, -w),
	vec3(rext, 0, -w+e),
	]) .segmented() .flip()
bevel(bot, [1,2], ('radius',c), resolution=('div',1))

rb = (dint + dext)/4	# balls guide radius
rr = 0.75*h/2		# ball radius

hr = sqrt(rr**2 - (w-e)**2)
top += wire(ArcCentered((rb*X,-Y), vec3(rb+hr, 0, w-e), vec3(rb-hr, 0, w-e)))
bot += wire(ArcCentered((rb*X,-Y), vec3(rb-hr, 0, -w+e), vec3(rb+hr, 0, -w+e)))
top.close()
bot.close()

nb = int(0.8 * pi*rb/rr)
balls = repeat(icosphere(rb*X, rr), nb, angleAxis(radians(360)/nb, Z))
balls.option(color=vec3(0,0.1,0.2))

cage_profile = Wire([ 
	vec3(rext-c, 0, -w+e+0.5*c),
	vec3(rext-c, 0, w-e-c),
	vec3(rint+c, 0, w-e-c),
	vec3(rint+c, 0, -w+e+0.5*c),
	])
bevel(cage_profile, [1,2], ('radius',c), resolution=('div',1))

cage_surf = revolution(2*pi, axis, cage_profile)
cage_surf.mergeclose()
boolean.booleanwith(cage_surf, inflate(balls, 0.2*c), False)
cage = thicken(cage_surf, 0.5*c) .option(color=vec3(0.3,0.2,0))

#top = (
#	  Wire([
#		bot[-1], 
#		bot[-1]+c*X, 
#		top[0]+c*X, 
#		top[0]]) .segmented()
#	+ top
#	+ Wire([
#		top[-1], 
#		top[-1]-c*X, 
#		bot[0]-c*X, 
#		bot[0]]) .segmented()
#	)

part = revolution(4, axis, web([top, bot]))
part.mergeclose()
