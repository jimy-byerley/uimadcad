from madcad import *

def cylinder(a, b, radius):
	return extrusion(b-a, flatsurface(wire(Circle((a, normalize(a-b)), radius))))

color_pla = vec3(0.7,0.7,0.8)

nail_position = -X
ankle_position = O
spring_attach = -0.7*X+2.5*Z

rotoid_ankle = icosphere(ankle_position, 0.3)
rotoid_nail = difference(
	icosphere(nail_position, 0.2),
	cylinder(nail_position-0.1*X, nail_position+0.3*X, 0.1),
	)

rotoid_axis = difference(
		cylinder(nail_position-0.1*X, -0.4*X, 0.1), 
		cylinder(nail_position-0.11*X, -0.39*X, 0.07),
		)
chamfer(rotoid_axis, rotoid_axis.frontiers(0,1,2), ('radius', 0.02))

W = normalize(spring_attach - nail_position)

rotoid_shaft = difference(
				icosphere(spring_attach, 0.15),
				cylinder(spring_attach-0.2*W, spring_attach+0.2*W, 0.06),
				)
nail_shaft = cylinder(nail_position + 0.3*W, nail_position + 3.5*W, 0.05)
chamfer(nail_shaft, nail_shaft.frontiers(), ('radius', 0.01))

nail_spring = (Solid(content=coilspring_compression(1.5, 0.25, 0.02)) 
					.transform(quat(Z,W)) 
					.transform(nail_position + 1.6*W)
				)

Segment(nail_position, nail_position+vec3(0.5,0,1))

support = difference(
	revolution(2*pi, Axis(nail_position,W), 
		Interpolated([
			nail_position + 0.8*W - 0.11*X, 
			nail_position - 0.3*X, 
			nail_position - 0.2*X - 0.3*W, 
			nail_position - 0.5*W - 0.5*X, 
			], resolution=('div', 5))),
	union(
		revolution(2*pi, (nail_position,X), [
			Segment(
				vec3(-0.9266, 0.004563, 0.186),
#				vec3(-0.6422, 0.004563, 0.3265))) .flip(),
				vec3(-0.8481, -0.02064, 0.2325)),
			ArcThrough(
				vec3(-0.8481, -0.02064, 0.2325),
				vec3(-0.85, -0.01962, 0.318),
				vec3(-0.6916, -0.0128, 0.4177)),
			]) .flip(),
		icosphere(nail_position, 0.21)),
	) .option(color=color_pla)

P0 = vec3(-0.8899, 0, -1.32)
dumper = revolution(2*pi, Axis(nail_position,W), [
	Segment(vec3(-0.4454, 0, -0.6506), P0),
	ArcThrough(
		P0,
		vec3(-1.046, 0, -1.38),
		vec3(-1.17, 0, -1.388)),
	]) .option(color=vec3(0.1))

nail = Solid(content=[rotoid_nail, rotoid_axis, nail_spring, nail_shaft, rotoid_shaft, support, dumper])
nail2 = nail.transform(rotatearound(2*pi/3, Axis(ankle_position, Z)))
nail3 = nail.transform(rotatearound(-2*pi/3, Axis(ankle_position, Z)))
nail1 = nail

leg = cylinder(ankle_position, ankle_position+3*Z, 0.12)
branch = revolution(2*pi, Axis(ankle_position,X), Softened([
		vec3(-0.75, 0.01462, 0.1),
		vec3(-0.75, 0.01462, 0.2),
		vec3(-0.5, 0.01462, 0.2),
		vec3(-0.32, 0.01462, 0.2928)])) .flip()

base = union(
	difference(
		icosphere(ankle_position, 1) .transform(mat3(0.5, 0.5, 0.4)) 
			+ icosphere(ankle_position, 0.31).flip(),
		revolution(2*pi, (ankle_position,Z), Segment(
			vec3(-0.341, 0.01462, 0.3639),
			vec3(-0.1793, 0.01462, 0.1056),
			))
		),
	repeat(branch, 3, rotatearound(2*pi/3, (ankle_position,Z))),
	) .option(color=color_pla)


base = intersection(base, square((ankle_position+0.25*Z, Z), 3))
base = union(base, repeat(
		cylinder(ankle_position+0.45*X-0.21*Z, ankle_position+0.45*X+0.2501*Z, 0.1),
		3, rotatearound(2*pi/3, (ankle_position,Z))))
base = difference(base, repeat(
		union(
			cylinder(ankle_position+0.45*X-0.51*Z, ankle_position+0.45*X-0.2*Z, 0.11),
			cylinder(ankle_position+0.45*X-0.5*Z, ankle_position+0.45*X+0.5*Z, 0.04),
			),
		3, rotatearound(2*pi/3, (ankle_position,Z)))) .finish()
#chamfer(base, base.frontiers(5,0), ('width', 0.01))

base_separation = revolution(2*pi, (ankle_position,Z), wire([
	ankle_position - 0.6*X+0.25*Z,
	ankle_position - 0.32*X + 1e-4*Z,
	ankle_position + 1e-4*Z,
	]).segmented()) .finish() #.transform(1e-2*X+1.33e-2*Y)
base.check()
base_separation.check()
a, b = boolean.cut_mesh(base, base_separation)

lower = Solid(content=difference(base, base_separation).option(color=color_pla))
upper = Solid(content=difference(base, base_separation.flip()).option(color=color_pla)) #.transform(0.5*Z)
#bug1 = note_leading(upper['content'].group(15), text="bug encore inconnu")

base_screw = Solid(content=screw(0.08, 0.5)) .transform(ankle_position+0.45*X+0.25*Z)


side = extrusion(1*Z,
	Softened([
		vec3(-1, -0.35, 2.574),
		vec3(-0.4857, -0.1203, 2.574),
		vec3(-0.2, -0.1235, 2.574),
		2.574*Z + rotate(-0.22*X, pi/3, Z)]),
	alignment=0.5)

some = difference(
	intersection(
		intersection(
			revolution(2*pi, Axis(O,Z), web([
				Softened([
					vec3(-1, 0, 2.4),
					vec3(-0.5, 0, 2.4),
					vec3(-0.2, 0, 2.2),
					vec3(-0.2, 0, 2.1),
					vec3(0, 0, 2.1)]),
				Segment(
					vec3(0, 0, 2.6),
					vec3(-1, 0, 2.6)),
				])) .finish(),
			repeat(side + side.transform(scaledir(rotate(X, -pi/6, Z), -1)).flip(), 
				3, rotatearound(2*pi/3, Axis(O,Z))) .finish(),
			),
		repeat(
			extrusion(0.5*W, 
				ArcCentered(Axis(spring_attach,W), 
					vec3(-0.6, 0.2, 2.468), 
					vec3(-0.6, -0.2, 2.468)), 
				alignment=0.5),
			3, rotatearound(2*pi/3, Axis(O,Z))),
		),
	leg + repeat(icosphere(spring_attach, 0.16), 3, rotatearound(2*pi/3, Axis(O,Z))),
	) .option(color=color_pla)

leg = union(leg, rotoid_ankle)

#exploded = kinematic.explode([o  for o in vars().values() if isinstance(o,Solid)])
