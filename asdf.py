# persona_adaptive_stacking.py
# Requires: pip install ursina
from ursina import *
from ursina.prefabs.first_person_controller import FirstPersonController
import random, time

# ---------- CONFIG ----------
GRID_ROWS = 12
GRID_COLS = 12
FLOOR_Y = 0.0
SPAWN_HEIGHT = 3.0
CUBE_GRAVITY = 18.0
SAMPLE_INTERVAL = 0.12     # 위치 샘플 주기 (초)
WINDOW_SECONDS = 8.0       # 페르소나 판정에 쓰는 시간 창
EXPLORER_POS_RATIO = 0.55  # 임계값(튜닝 가능)
ANALYST_UNIQ_ACTIONS = 2   # 임계값

# ---------- APP & PLAYER ----------
app = Ursina()
player = FirstPersonController()
player.position = (GRID_ROWS/2, 4, GRID_COLS/2)
player.speed = 7
player.cursor.visible = False

# ---------- world creation + keep references ----------
floor_entities = []
spawned = []   # player-spawned cubes
tokens = []    # hidden tokens for explorer reward
markers = []   # path markers for analyst hint
safe_tiles = []  # for verifier adaptation

for x in range(GRID_ROWS):
    for z in range(GRID_COLS):
        kind = random.choice([0,1,2])  # 0 empty, 1 floor, 2 wall
        wx = x
        wz = z
        if kind == 1:
            ent = Entity(model='cube', scale=(1,0.1,1), position=(wx, FLOOR_Y - 0.05, wz),
                         color=color.light_gray, collider='box')
            floor_entities.append(ent)
        elif kind == 2:
            h = random.uniform(0.9, 2.0)
            Entity(model='cube', scale=(1,h,1), position=(wx, h/2 + FLOOR_Y, wz),
                   color=color.rgb(150,150,180), collider='box')

# UI
hint = Text("E: spawn | Q: delete nearest spawned | R: clear | ESC: quit", position=(-0.7,0.45))
persona_label = Text("", position=(0.6, 0.42), origin=(0,0))

# ---------- logging for persona detection ----------
pos_samples = []   # list of (x,z, timestamp)
action_log = []    # list of (action_str, timestamp)
last_sample = time.time()

def record_pos():
    # sample player's horizontal position
    now = time.time()
    pos_samples.append((round(player.x,2), round(player.z,2), now))
    # prune old samples to keep memory small
    cutoff = now - (WINDOW_SECONDS * 2)
    while pos_samples and pos_samples[0][2] < cutoff:
        pos_samples.pop(0)

def record_action(a):
    action_log.append((a, time.time()))
    cutoff = time.time() - (WINDOW_SECONDS * 2)
    while action_log and action_log[0][1] < cutoff:
        action_log.pop(0)

# ---------- simple physics for spawned cubes ----------
def spawn_cube():
    pos = camera.world_position + camera.forward * 2.5 + Vec3(0, SPAWN_HEIGHT, 0)
    c = Entity(model='cube', color=color.white, position=pos, collider='box')
    c.vel = Vec3(0,0,0)
    spawned.append(c)
    record_action('spawn')
    return c

def nearest_spawned_in_front(max_dist=3.5, forward_dot=0.5):
    cam_pos = camera.world_position
    cam_forward = camera.forward
    best = None; best_d = 1e9
    for c in spawned:
        dvec = c.world_position - cam_pos
        d = dvec.length()
        if d > max_dist: continue
        if dvec.normalized().dot(cam_forward) < forward_dot: continue
        if d < best_d:
            best_d = d; best = c
    return best

# ---------- persona detection (sliding window) ----------
def get_window_logs(window=WINDOW_SECONDS):
    now = time.time()
    pos_window = [p for p in pos_samples if p[2] >= now - window]
    actions_window = [a for a in action_log if a[1] >= now - window]
    return pos_window, actions_window

def detect_persona_realtime(window=WINDOW_SECONDS):
    pos_w, act_w = get_window_logs(window)
    # safety: if not enough data, return Neutral
    if len(pos_w) < 4 and len(act_w) < 2:
        return 'Neutral', 'not enough data'
    # compute pos_ratio = unique_positions / total_positions
    total = len(pos_w)
    uniq = len(set((p[0], p[1]) for p in pos_w))
    pos_ratio = uniq / max(1, total)
    unique_actions = len(set(a[0] for a in act_w))
    # simple heuristics
    if pos_ratio >= EXPLORER_POS_RATIO and len(pos_w) >= 6:
        return 'Explorer', f'pos_ratio={pos_ratio:.2f}'
    if unique_actions <= ANALYST_UNIQ_ACTIONS and len(act_w) >= 3:
        return 'Analyst', f'unique_actions={unique_actions}'
    # verifier: if mostly idle or few risky actions (we treat default as verifier)
    return 'Verifier', f'pos_ratio={pos_ratio:.2f}, actions={unique_actions}'

# ---------- adaptations ----------
# Clear previous adaptations helpers
def clear_markers():
    for m in markers:
        destroy(m)
    markers.clear()

def clear_tokens():
    for t in tokens:
        destroy(t)
    tokens.clear()

def clear_safe_tiles():
    for s in safe_tiles:
        # restore color
        s.color = color.light_gray
    safe_tiles.clear()

def apply_adaptation(persona):
    # take actions depending on persona
    # idempotent-ish: calling repeatedly won't stack infinite objects
    if persona == 'Explorer':
        # spawn a hidden token somewhere random on a floor tile (if none present)
        if not tokens and floor_entities:
            target = random.choice(floor_entities)
            t = Entity(model='sphere', color=color.yellow, position=(target.x, target.y+0.25, target.z), scale=0.4)
            tokens.append(t)
    elif persona == 'Analyst':
        # show a simple straight-line hint from player to grid center using small markers
        clear_markers()
        center = Vec3(GRID_ROWS/2, 0.1, GRID_COLS/2)
        steps = 6
        start = camera.world_position
        for i in range(1, steps+1):
            p = start.lerp(center, i/(steps+1))
            m = Entity(model='cube', color=color.green, position=(p.x, 0.15, p.z), scale=0.2)
            markers.append(m)
    elif persona == 'Verifier':
        # highlight 3 floor tiles as visibly safe (change color) if not already
        if not safe_tiles and floor_entities:
            sample = random.sample(floor_entities, min(3, len(floor_entities)))
            for s in sample:
                s.color = color.rgb(120,220,120)  # greenish safe tile
                safe_tiles.append(s)
    else:
        # neutral or unknown: clear adaptive content
        clear_tokens(); clear_markers(); clear_safe_tiles()

# ---------- update loop ----------
last_persona = 'Neutral'
last_reason = ''
last_adapt_time = 0

def update():
    global last_persona, last_reason, last_adapt_time, last_sample
    dt = time.dt
    # sample position periodically
    now = time.time()
    if now - last_sample >= SAMPLE_INTERVAL:
        record_pos()
        last_sample = now

    # physics for spawned cubes (simple)
    for c in list(spawned):
        c.vel.y -= CUBE_GRAVITY * dt
        c.position += c.vel * dt
        half = c.scale_y/2.0
        if c.y - half <= FLOOR_Y:
            c.y = FLOOR_Y + half
            if abs(c.vel.y) > 0.5:
                c.vel.y = -c.vel.y * 0.1
            else:
                c.vel.y = 0
            c.vel.x *= 0.98; c.vel.z *= 0.98

    # detect persona every few seconds (avoid too frequent adaptation)
    if now - last_adapt_time > 2.0:
        persona, reason = detect_persona_realtime()
        if persona != last_persona:
            # changed -> apply adaptation
            apply_adaptation(persona)
            last_persona = persona
            last_reason = reason
            last_adapt_time = now
        else:
            # occasionally refresh adaptation even if same persona
            if now - last_adapt_time > 8.0:
                apply_adaptation(persona)
                last_adapt_time = now

    # UI update
    persona_label.text = f'Persona: {last_persona} ({last_reason})'

# ---------- input handling ----------
def input(key):
    if key == 'escape':
        application.quit()
    if key == 'e':
        spawn_cube()
    if key == 'q':
        t = nearest_spawned_in_front()
        if t:
            destroy(t)
            try: spawned.remove(t)
            except: pass
        record_action('delete')
    if key == 'r':
        for c in list(spawned):
            destroy(c)
        spawned.clear()
        record_action('clear')

# ---------- run ----------
# init sampling
last_sample = time.time()
record_pos()
app.run()