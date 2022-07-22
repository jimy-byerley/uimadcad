from madcad import *

pla = vec3(0.6)
copper = vec3(0.6, 0.4, 0.2)

@cachefunc
def part_emptyaxis(r, l):
	profile = web(wire([
		vec3(r, 0, 0),
		vec3(r, 0, l),
		vec3(0.6*r, 0, l),
		vec3(0.6*r, 0, 0),
		]) .flip().close().segmented())
	chamfer(profile, [0,1], ('radius', 0.2*r))
	return revolution(2*pi, Axis(O,Z), profile) .option(color=copper)

def emptyaxis(a, b, r):
	return Solid(part=part_emptyaxis(r, distance(a,b))) .transform(quat(Z, b-a)) .transform(a)
def washer(axis, *args, **kwargs):
	return Solid(part=standard.washer(*args, **kwargs)) .transform(quat(Z, axis[1])) .transform(axis[0])

d = 8
axis_play = 0.02
nail_radius = 50

def moyeu(d):
	return difference(
		union(
			cylinder(-1.5*d*X, 1.5*d*X, d),
			cylinder(-1.1*d*Y, O, 0.9*d),
			),
		( cylinder(-3*d*Y, 3*d*Y, (0.5+axis_play)*d)
		+ cylinder(-2*d*X, -0.8*d*X, (0.5+axis_play)*d)
		+ cylinder(2*d*X, 0.8*d*X, (0.5+axis_play)*d) ),
		) .option(color=pla)

def side_mount(d):
	c = wire(Circle((0.5*d*X,X), 0.75*d))
	w = web(wire([
		4*d*Z,
		1.2*d*Y,
		-4*d*Z,
		-1.2*d*Y,
		]) .close() .segmented())
	bevel(w, [1,3], ('radius',d))
	bevel(w, [0,2], ('radius',d/3))
	w.finish()
	side = difference(
		( 	extrusion(-0.5*d*X, w)
			+ blendpair(w, blending.synchronize(wire(w),c), tangents='straight')
			+ flatsurface(c)
			+ flatsurface(w.transform(-0.5*d*X))
		).finish(),
		cylinder(2*d*X, -2*d*X, d/2),
		) .option(color=pla)
	return Solid(
				part=side, 
				washer=washer((-0.7*d*X, X), d, h=0.15*d), 
				axis=emptyaxis(-1.5*d*X, 0.5*d*X, d/2),
				)

def nail(d):
	return Solid(
		moyeu = moyeu(d),
		side1 = side_mount(d) .transform(translate(2.4*d*X)),
		side2 = side_mount(d) .transform(translate(-2.4*d*X) * rotate(pi,Z)),
		axis = emptyaxis(d*Y, -3*d*Y, d/2),
		washer = washer((-1.3*d*Y, Y), d, h=0.15*d),
		stop = washer((d*Y, Y), 0.7*d),
		stop_screw = Solid(part=screw(0.7*d, d, head='BH')) .transform(translate(1.2*d*Y) * rotate(-pi/2,X)),
		)

f1 = nail(d) .transform(rotate(0,Z) * translate(nail_radius*Y))
f2 = nail(d) .transform(rotate(pi*2/3,Z) * translate(nail_radius*Y))
f3 = nail(d) .transform(rotate(-pi*2/3,Z) * translate(nail_radius*Y))

@cachefunc
def universaljoint(d):
	p = union(
		icosphere(O, 1.6*d),
		icosphere(-d*Z, 1.6*d),
		)
	profile = web([
		vec3(0, 1.1*d, 2*d),
		vec3(0, 1.1*d, -3*d),
#		vec3(0, 1.1*d, -1.2*d),
#		vec3(0, 1.1*d+d, -1.2*d-d),
		]) .segmented()
	moyeu = intersection(
		intersection(
			p,
			extrusion(4*d*X, profile.flip() + profile.transform(scaledir(Y, -1)), alignment=0.5),
			),
		(extrusion(4*d*X, profile.flip() + profile.transform(scaledir(Y, -1)), alignment=0.5)) .flip().transform(mat4(scaledir(Z, -1))*rotate(pi/2,Z)*translate(d*Z)),
		)
	moyeu = difference(moyeu, cylinder(-2*d*Y, 2*d*Y, (0.5+axis_play)*d))
	moyeu = difference(moyeu, cylinder(-2*d*X, 2*d*X, (0.5+axis_play)*d) .transform(-d*Z))
	moyeu.strippoints()
	moyeu.finish().option(color=pla)
	nprint(globals())
	return Solid(
		moyeu=moyeu,
		washers=[
			washer((1.2*d*Y, Y), d, h=0.15*d),
			washer((-1.2*d*Y, -Y), d, h=0.15*d),
			washer((1.2*d*X-d*Z, X), d, h=0.15*d),
			washer((-1.2*d*X-d*Z, -X), d, h=0.15*d),
			emptyaxis(-20*Y, 20*Y, d/2),
			emptyaxis(-20*X-d*Z, 20*X-d*Z, d/2),
			],
		)

center = universaljoint(d) .transform(-0.2*nail_radius*Z - 0.5*nail_radius*Y)

wire([
	ArcCentered((O,-Y), 1.4*d*Y-1.2*d*X, 1.4*d*Y+1.2*d*X),
	ArcCentered((4*d*Z,-Y), 1.4*d*Y+0.6*d*X+4*d*Z, 1.4*d*Y-0.6*d*X+4*d*Z),
	]).close()

