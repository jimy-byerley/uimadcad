from madcad import *
from madcad.boolean import booleanwith

dint = 16
dext = 35
h = 11
contact = radians(10)
hint = h*cos(contact)
hext = h*cos(contact) * 0.8 if contact else h


# convenient variables
rint = dint/2
rext = dext/2
c = 0.05*h
w = 0.5*h
e = 0.08*(dext-dint)
axis = Axis(O,Z)

# cones definition points
if contact:
	cr = vec3(mix(rint, rext, 0.5), 0, 0)
	ct = -cr.x / tan(contact) *Z
	angled = Axis(ct, vec3(sin(contact), 0, cos(contact)))

	p1 = vec3(rext-e, 0, -w+hext)
	p2 = vec3(rint+e, 0, w-hint+e)
	a1 = Axis(p1, normalize(p1-ct))
	a2 = Axis(p2, normalize(p2-ct))

	p3 = angled[0] - project(reflect(p2-angled[0], angled[1]), a1[1])

	p4 = angled[0] - reflect(p3-angled[0], angled[1])
	p5 = angled[0] - reflect(p1-angled[0], angled[1])
else:
	p1 = vec3(rext-e, 0, -w+hext-e)
	p3 = vec3(rext-e, 0, -w+e)
	p4 = vec3(rint+e, 0, w-hint+e)
	p5 = vec3(rint+e, 0, -w+hext-e)
	angled = Axis(0.5*(rint+rext) * X, Z)

# exterior profiles
interior = Wire([
	p5+e*X,
	vec3(p5[0]+e, 0, w),
	vec3(rint, 0, w),
	vec3(rint,	0,	w-hint),
	vec3(p4[0]+e, 0, w-hint),
	p4+e*X,
	]) .segmented()
exterior = Wire([
	p3,
	vec3(p3[0], 0, -w),
	vec3(rext, 0, -w),
	vec3(rext, 0, -w+hext),
	vec3(rext-e,	0, -w+hext),
	]) .segmented()
bevel(interior, [2,3], ('radius',c), resolution=('div',1))
bevel(exterior, [2,3], ('radius',c), resolution=('div',1))

# create interior details
interior += Wire([
	p4,
	p5,
	p5+e*X,
	]) .segmented()
exterior += Wire([p3])

roller = revolution(2*pi, angled, Segment(mix(p1,p3,0.05), mix(p3,p1,0.05)))
roller.mergeclose()
for hole in roller.outlines().islands():
	roller += flatsurface(wire(hole))

nb = int(pi*(rint+rext) / (2.5*distance_pa(p1,angled)))
rollers = repeat(roller, nb, rotatearound(2*pi/nb, axis)) 
rollers.option(color=vec3(0,0.1,0.2))

p6 = mix(p4,p3,0.6) - e*angled[1]
cage_profile = wire([
	p6 - 1.5*e*X,
	p6,
	p6 + (distance(p1,p3)+1.8*e) * angled[1],
	])
bevel(cage_profile, [1], ('radius',c))
cage = revolution(2*pi, axis, cage_profile)
cage.mergeclose()
booleanwith(cage, inflate(rollers, 0.5*c), False)
cage = thicken(cage, c) .option(color=vec3(0.3,0.2,0))

part = revolution(4, axis, web([
			exterior, 
			interior,
			]).flip() )
part.mergeclose()

return part + cage + rollers

#part = revolution(2*pi, axis, 
#			(exterior + interior) .close() .flip()
#			)
#part.mergeclose()
#return part
