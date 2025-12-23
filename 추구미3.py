# fixed_stacking_demo.py
from ursina import *
import random, math
from ursina.prefabs.first_person_controller import FirstPersonController

app = Ursina()
player = FirstPersonController()
player.position = (3, 5, 3)   # 너무 높지 않게 시작
player.cursor.visible = False
player.gravity = 1
player.speed = 10

# spawned cubes (player-created)
cb = []

# simple per-cube physics parameters (tunable)
CUBE_GRAVITY = 20.0
CUBE_FLOOR_Y = 0.0

# world grid size
ROWS = 15
COLS = 15

# create ground/world using per-cell randomness (random for each cell)
for i in range(ROWS):
    for j in range(COLS):
        A = random.choice([0, 1, 2])   # choose per-cell
        if A == 0:
            # empty: do nothing
            pass
        elif A == 1:
            # floor tile
            Entity(
                model='cube',
                scale=1,
                position=(i, 0, j),
                color=color.rgb(200, 200, 200),
                collider='box'
            )
        elif A == 2:
            # wall block with visible height
            h = random.uniform(0.8, 2.0)
            Entity(
                model='cube',
                scale=(1, h, 1),
                position=(i, h/2, j),   # set y so it sits on ground
                color=color.rgb(150, 150, 180),
                collider='box'
            )

# simple UI hint
Text("E: spawn cube in front | Q: delete nearest cube in front | R: clear spawned cubes | ESC: quit",
     position=(-0.7, 0.45), origin=(0, 0), scale=1.0)

# helper: spawn a cube a bit in front of camera/player and give it a velocity so it falls
def spawn_cube_in_front():
    spawn_pos = camera.world_position + camera.forward * 2.5 + Vec3(0, 3, 0)
    cube = Entity(model='cube', color=color.white, scale=1, position=spawn_pos, collider='box')
    # add simple physics state
    cube.vel = Vec3(0, 0, 0)
    cb.append(cube)
    return cube

# helper: find nearest player-facing cube within reach
def nearest_cube_in_front(reach=3.5, fov_dot=0.6):
    cam_pos = camera.world_position
    cam_forward = camera.forward
    best = None
    best_d = 1e9
    for c in cb:
        d_vec = c.world_position - cam_pos
        d = d_vec.length()
        if d > reach: 
            continue
        # check roughly in front (dot product)
        if d_vec.normalized().dot(cam_forward) < fov_dot:
            continue
        if d < best_d:
            best_d = d
            best = c
    return best

# update loop: simple gravity for spawned cubes + ground collision
def update():
    dt = time.dt
    # basic physics for manual spawned cubes
    for c in list(cb):
        # integrate gravity
        c.vel.y -= CUBE_GRAVITY * dt
        # integrate position
        c.position += c.vel * dt
        # floor collision
        half_h = c.scale_y / 2.0
        if c.y - half_h <= CUBE_FLOOR_Y:
            c.y = CUBE_FLOOR_Y + half_h
            # stop vertical velocity and damp
            if abs(c.vel.y) > 0.5:
                c.vel.y = -c.vel.y * 0.1
            else:
                c.vel.y = 0
        # optional: simple horizontal damping to avoid perpetual sliding
        c.vel.x *= 0.995
        c.vel.z *= 0.995

# input handling
def input(key):
    if key == 'escape':
        application.quit()

    if key == 'e':
        # spawn white cube in front (will fall)
        spawn_cube_in_front()

    if key == 'q':
        # destroy nearest cube in front if found
        target = nearest_cube_in_front()
        if target:
            destroy(target)
            try:
                cb.remove(target)
            except ValueError:
                pass

    if key == 'r':
        # destroy all spawned cubes
        for c in list(cb):
            destroy(c)
        cb.clear()

app.run()
