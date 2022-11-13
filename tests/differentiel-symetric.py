from madcad import *
from madcad.gear import *

def sbevelgear(step, z, pitch_cone_angle, **kwargs):
	part = bevelgear(step, z, pitch_cone_angle, **kwargs)
	top = project(part.group(4).barycenter(), Z)
	bot = project(part.group(1).barycenter(), Z)
	return Solid(
		part = part .option(color=gear_color),
		summit = O,
		axis = Axis(top, -Z, interval=(0, length(top))),
		bot = Axis(bot, Z, interval=(0, length(top-bot))),
		)

def bolt(a, b, dscrew, washera=False, washerb=False):
	dir = normalize(b-a)
	rwasher = washer(dscrew)
	thickness = rwasher['part'].box().width.z
	rscrew = screw(dscrew, distance(a,b) + 1.5*dscrew)
	rnut = nut(dscrew)
	return Solid(
			screw = rscrew.place((Pivot, rscrew['axis'], Axis(a-thickness*dir, -dir))), 
			nut = rnut.place((Pivot, rnut['top'], Axis(b+thickness*dir, -dir))),
			w1 = rwasher.place((Pivot, rwasher['top'], Axis(b, -dir))),
			w2 = rwasher.place((Pivot, rwasher['top'], Axis(a, dir))),
			)

transmiter_angle = pi/6
transmiter_z = 8
gear_step = 6
output_radius = 5
gear_color = vec3(0.2, 0.3, 0.4)

axis_z = round(transmiter_z/tan(transmiter_angle))
transmiter_rint = stceil((transmiter_z * gear_step / (2*pi) - 0.6*gear_step) * (0.5 + 0.2*sin(transmiter_angle)))

bearing_height = stceil(output_radius)
bearing_radius = stceil(output_radius*2.5)
out_gear = sbevelgear(gear_step, axis_z, pi/2-transmiter_angle, 
				bore_radius=output_radius, 
				bore_height=1.2*bearing_height,
				)
output = Solid(
	gear = out_gear,
	bearing = bearing(stceil(output_radius*1.5*2), bearing_radius*2, bearing_height)
				.transform(out_gear['axis'].origin - 0.5*bearing_height*Z),
	)
output1 = output
output2 = deepcopy(output).transform(rotate(pi,Y))

transmiter_axis_thickness = stceil(transmiter_rint*0.2)
transmiter_washer_thickness = stceil(transmiter_rint*0.2)
transmiter_gear = sbevelgear(gear_step, transmiter_z, transmiter_angle, 
				bore_height=0, 
				bore_radius=transmiter_rint,
				)
transmiter = Solid(
		gear = transmiter_gear,
		bearing = slidebearing(
				(transmiter_rint-transmiter_axis_thickness)*2, 
				stceil(distance(transmiter_gear['axis'].origin, transmiter_gear['bot'].origin)), 
				transmiter_axis_thickness,
				) .transform(transmiter_gear['axis'].origin),
		washer = washer(
				stceil(transmiter_rint*2), 
				stceil(transmiter_rint*1.8*2), 
				transmiter_washer_thickness,
				) .transform(transmiter_gear['axis'].origin),
		).transform(rotate(pi/2,Y))

transmiter_amount = ceil(axis_z / (1.5*transmiter_z/pi))
transmiters = [deepcopy(transmiter).transform(rotate(i*2*pi/transmiter_amount,Z))  for i in range(transmiter_amount)]

space_radius = transmiter_z*gear_step/(2*pi) / sin(transmiter_angle) * 1.05

interior_top = revolution(2*pi, Axis(O,Z), Wire([
	out_gear['axis'].origin + bearing_radius*X - bearing_radius*0.15*X,
	out_gear['axis'].origin + bearing_radius*X,
	out_gear['axis'].origin + bearing_radius*X - bearing_height*Z,
	out_gear['axis'].origin + bearing_radius*X - bearing_height*1.2*Z + bearing_height*0.2*X,
	out_gear['axis'].origin + space_radius*X  - bearing_height*1.2*Z,
	]).flip().segmented())
interior_out = (
			interior_top 
			+ interior_top.transform(scaledir(Z,-1)).flip()
			).finish()

r = length(transmiter['gear']['axis'].origin)
l = distance(transmiter['gear']['axis'].origin, transmiter['gear']['bot'].origin)
h = transmiter_rint - transmiter_axis_thickness
interior_transmision = revolution(2*pi, Axis(O,X), Wire([
	(r-l)*X,
	(r-l)*X + h*Z,
	r*X + h*Z,
	r*X + h*Z + transmiter_washer_thickness*(X+Z),
	(r + transmiter_washer_thickness)*X + 2.5*h*Z,
	(r + transmiter_washer_thickness)*X + 2.5*h*Z + h*(X+Z),
	]).flip().segmented())
interior_transmisions = repeat(interior_transmision, transmiter_amount, rotate(2*pi/transmiter_amount, Z))

interior_space = union(
				icosphere(O, space_radius),
				cylinder(out_gear['axis'].origin, out_gear['axis'].origin*vec3(1,1,-1), bearing_radius*1.1, fill=False),
				).flip()

interior_shell = union(interior_space, interior_out)
interior = union(interior_shell, interior_transmisions)

# symetrical exterior
shell_thickness = 1
exterior_shell = inflate(interior_shell.flip(), shell_thickness)

dscrew = 3
neighscrew = 1.4*dscrew
rscrew = max(bearing_radius + 1.2*neighscrew,  space_radius + dscrew*0.5 + shell_thickness*0.5)
a = out_gear['axis'].origin + rscrew*X - (bearing_height-shell_thickness)*Z
b = bolt(a, a*vec3(1,1,-1), dscrew, False, False)
bolts = [b.transform(rotate(i*2*pi/6, Z))  for i in range(6)]

screw_support = web([
	project(a, Z) + dscrew*X,
	a + neighscrew*X,
	a + neighscrew*X - shell_thickness*Z,
	a + neighscrew*X - shell_thickness*Z - rscrew*(X+Z),
	]).segmented()
screw_supports = revolution(2*pi, Axis(O,Z), union(
				screw_support, 
				screw_support.transform(scaledir(Z,-1)).flip()),
				)

exterior_shape = union(exterior_shell, screw_supports)

hole = cylinder(a+1*Z, a*vec3(1,1,-1)-1*Z, dscrew*0.55).flip()
holes = mesh.mesh([hole.transform(b.pose)  for b in bolts])
exterior = intersection(exterior_shape, holes)
