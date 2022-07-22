from madcad import *

rint = 1
rext = 3
margin = 0.1*rint

def cardan_sphereprofile(maxangle=0.5):
	s = icosphere(O, 1)
	d = vec3(cos(maxangle), 0, sin(maxangle))
	a = normalize(d+Y)
	return wire([
		ArcCentered(Axis(O, d*vec3(-1,1,1)), a*vec3(-1,-1,1), a*vec3(-1,1,1)),
		ArcCentered(Axis(O, -Y), a*vec3(-1,1,1), a),
		ArcCentered(Axis(O, d), a, a*vec3(1,-1,1)),
		ArcCentered(Axis(O, Y), a*vec3(1,-1,1), a*vec3(-1,-1,1)),
		])

thickness = 0.58
profile = cardan_sphereprofile(0.5) .transform(rext*thickness*0.95)

#body = icosphere(O, rext) .transform(rint*0.3*Z)
body = union(
		icosphere(O, rext),
		revolution(2*pi, Axis(O,Z), Softened([
				vec3(2.706, 0, 1.147),
				vec3(1.959, -1.56e-08, 2.209),
				vec3(1.221, -1.454e-07, 3.298),
				vec3(1.175, -4.856e-07, 6.152)])) .flip(),
		) #.transform(rint*0.3*Z)

shape = intersection(
	inflate(extrusion(mat3(5), profile.flip()), -margin),
#	union(
#		inflate(extrusion(mat3(5), profile.flip()), -margin),
#		icosphere(O, rext+margin) .flip(),
#		),
	body + icosphere(O, thickness*rext).flip(),
	)

from madcad.recent import convexhull, convexoutline
s = flatsurface(convexoutline(web(
	Circle(Axis(rext*Y,Y), 1.5*rint),
	Circle(Axis(rext*Y+rext*Z, Y), 0.7*rint),
	)))
s.check()
r = extrusion(scaledir(Y,-1), s.flip())
r.check()
shape = shape.replace(union(shape.group((4,5)), r))

hole = revolution(2*pi, Axis(O,Y), wire([
	vec3(rint+0.1*rext, rext, 0),
	vec3(rint, rext*0.9, 0),
	vec3(rint, 0, 0),
	]).segmented().flip())
result = intersection(
		shape, 
		hole + hole.transform(scaledir(Y,-1)).flip(),
		).finish()

upper = Solid(content=result)
lower = upper.transform(rotate(pi/2,Z) * rotate(pi,Y))


tubes = repeat(
		cylinder((rext - 0.3*rint)*X, sqrt((thickness*rext)**2 - rint**2)*X, 0.95*rint) .group((0,1)),
		4, 
		rotatearound(pi/2, Axis(O,Z)),
		) 
moyeu = tubes + junction(
	tubes.flip(),
	tangents='tangent', weight=-1,
	)
moyeu.option(color=vec3(0.7))

cardan = [upper, lower, moyeu]

notes = [
	note_leading(
		result.group(5),
		text='surface can be extended\nto join the target part'),
	note_leading(result.group(7), text='gliding surface ?'),
	]





adaptation = revolution(2*pi, Axis(O,X), wire([
	vec3(rext, rint+0.1*rext, 0),
	vec3(rext*0.9, rint, 0),
	vec3(rint*1.2+margin, rint, 0),
	vec3(rint*1.2+margin, rint*1.2, 0),
	vec3(rext, rext, 0),
	]).segmented().flip())
limit_ext = icosphere(O, rext)
ponpon = intersection(adaptation, limit_ext)

n = repeat(ponpon, 4, rotatearound(pi/2, Axis(O,Z)))


# limited holder
limitx = ArcThrough(
	vec3(-2.273, -2.14e-07, 1.795),
	vec3(-0.1443, -3.538e-07, 2.968),
	vec3(2.258, 0.01989, 1.815))
limity = wire(Softened([
		vec3(7.089e-07, 0.341, 2.973),
		vec3(7.191e-07, 1.108, 3.016),
		vec3(5.26e-07, 3.282, 2.206),
		vec3(5.31e-07, 4.753, 2.227)]))
limitint = tube(limitx, limity)
limintest = limitint.transform(rotate(pi/2, Z) * rotate(pi/2, X))
ArcThrough(
	vec3(-2.118, -1.809, 0.8377),
	vec3(0.4138, -0.7041, 3.037),
	vec3(2.149, -1.901, 0.7572))


# ring holder
ring = Solid(content=[
	Axis(O,Z),
	ArcThrough(
		vec3(-2.25, 0.006792, -2.172),
		vec3(-0.327, 0.006791, 6.053),
		vec3(2.237, 0.006792, -2.172)),
	ArcThrough(
		vec3(-2.143, 0.006792, 2.137),
		vec3(-0.2557, 0.006791, 4.95),
		vec3(2.201, 0.006792, 2.172)),
	ArcThrough(
		vec3(-2.157, -2.041, 0.04165),
		vec3(-0.1463, -0.6017, 5.451),
		vec3(2.148, -2.042, 0.1403)),
	ArcThrough(
		vec3(-2.157, 2.041, 0.04165),
		vec3(-0.1463, 0.6017, 5.451),
		vec3(2.148, 2.042, 0.1403)),
	])
ring2 = ring.transform(rotate(pi/2,X) * rotate(pi/8,X))
ring3 = ring.transform(rotate(pi/2,Z) * rotate(pi/8,X))


# shared sphere area
limit_side = revolution(pi, Axis(O,X), Segment(
	vec3(rint*1.2, rint*1.2+margin, 0),
	vec3(rext, rext+margin, 0),
	)) .transform(rotate(-pi/8,Y))
limit = intersection(
			limit_side + limit_side.transform(scaledir(X, -1)).flip(),
			limit_ext,
			)
