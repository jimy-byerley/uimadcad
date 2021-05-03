from madcad import *

dint, dext, h = 16, 35, 11

rint = dint/2
rext = dext/2
c = 0.05*h
w = 0.5*h
e = 0.15*(dext-dint)

axis = Axis(O,Z)
interior = Wire([
	vec3(rint+e, 0,	w), 
	vec3(rint, 0, w),
	vec3(rint,	0,	-w),
	vec3(rint+e, 0,	-w), 
	]) .segmented() .flip()
bevel(interior, [1, 2], ('radius',c), resolution=('div',1))

exterior = Wire([
	vec3(rext-e,	0, -w),
	vec3(rext, 0, -w),
	vec3(rext, 0, w),
	vec3(rext-e,	0, w),
	]) .segmented() .flip()
bevel(exterior, [1,2], ('radius',c), resolution=('div',1))

rb = (dint + dext)/4
rr = 0.75*(dext - dint)/4

hr = sqrt(rr**2 - (rb-rint-e)**2)
interior += wire(ArcCentered((rb*X,-Y), vec3(rint+e, 0, hr), vec3(rint+e, 0, -hr)))
exterior += wire(ArcCentered((rb*X,-Y), vec3(rext-e, 0, -hr), vec3(rext-e, 0, hr)))
interior.close()
exterior.close()

nb = int(0.7 * pi*rb/rr)
balls = repeat(icosphere(rb*X, rr), nb, angleAxis(radians(360)/nb, Z))
balls.option(color=vec3(0,0.1,0.2))

#interior = (
#	  Wire([
#		exterior[-1], 
#		exterior[-1]+c*Z, 
#		interior[0]+c*Z, 
#		interior[0]]) .segmented()
#	+ interior
#	+ Wire([
#		interior[-1], 
#		interior[-1]-c*Z, 
#		exterior[0]-c*Z, 
#		exterior[0]]) .segmented()
#	)

part = revolution(4, axis, web([exterior, interior]))
part.mergeclose()

envelope = difference(
	union(
		repeat(
			icosphere(rb*X, 2*c+rr), 
			nb, angleAxis(2*pi/nb,Z),
			), 
		brick(width=vec3(dext,dext, 3*c)),
		),
	( extrusion(2*h*Z, Circle((-h*Z,Z), rb-rr*0.4, resolution=('rad',0.1)))
	+ extrusion(2*h*Z, Circle((-h*Z,Z), rb+rr*0.4, resolution=('rad',0.1))) .flip()
		),
	)
sides = envelope.group({0,4,6})
#chamfer(sides, sides.frontiers(0,4,6), ('width',1.1))
#chamfer(envelope, envelope.frontiers(0,6), ('width',c))
cage = thicken(sides, c) .option(color=vec3(0.5,0.3,0))

