# persona_puzzle_game_safe.py
# Requires: pip install ursina
# Run: python persona_puzzle_game_safe.py

from ursina import *
from ursina.prefabs.first_person_controller import FirstPersonController
import random, math, time, json, os, traceback

# ----------------- CONFIG (튜닝하기 쉬운 곳) -----------------
GRID_SIZE = 28               # 맵 한 변 크기 (너무 크면 성능 저하)
SPARSE_TILE_PROB = 0.40      # 바닥 생성 비율 (나머지는 빈칸 또는 벽)
WALL_PROB = 0.14             # non-empty일 때 벽 비율
SPAWN_HEIGHT = 3.0
CUBE_GRAVITY = 16.0
SAMPLE_INTERVAL = 0.15
WINDOW_SECONDS = 8.0
EXPLORER_POS_RATIO = 0.55
ANALYST_UNIQ_ACTIONS = 2
MAX_SPAWNED = 60
LOG_DIR = "logs_safe"
os.makedirs(LOG_DIR, exist_ok=True)
# ------------------------------------------------------------

app = Ursina()
window.color = color.rgb(18,20,25)

# ----------------- Player (FPS) -----------------
player = FirstPersonController()
player.position = (GRID_SIZE//2, 4, GRID_SIZE//2)
player.speed = 7
player.cursor.visible = False
player.gravity = 1

# ----------------- World (sparse floor + some walls) -----------------
floor_tiles = []
walls = []
def generate_world():
    random.seed(int(time.time()))
    for x in range(GRID_SIZE):
        for z in range(GRID_SIZE):
            if random.random() < SPARSE_TILE_PROB:
                # floor
                f = Entity(model='cube', scale=(1,0.08,1), position=(x, 0.0-0.04, z),
                           color=color.light_gray, collider='box')
                floor_tiles.append(f)
                # sometimes wall on same tile
                if random.random() < WALL_PROB:
                    h = random.uniform(1.0, 2.2)
                    w = Entity(model='cube', scale=(1,h,1), position=(x,h/2,z),
                               color=color.rgb(120,120,140), collider='box')
                    walls.append(w)
generate_world()

# ----------------- HUD & comforting message -----------------
persona_text = Text("Persona: Neutral", position=(-0.75, 0.45), scale=1.2)
status_text = Text("", position=(0.6, 0.45))
hint_text = Text("", position=( -0.75, 0.40), scale=1.0, color=color.azure)

# show a friendly, short "safe space" message that fades out
welcome = Text("여기는 안전한 실험 공간이에요. 마음껏 시도해보세요!", origin=(0,0), scale=1.2, y=0.35, color=color.rgb(200,220,255))
welcome_timer = 0.0

# ----------------- Logging -----------------
log = {'positions':[], 'actions':[], 'events':[], 'start_time':time.time()}
pos_samples = []
action_log = []

def record_pos():
    now = time.time()
    pos = (round(player.x,2), round(player.z,2), now)
    pos_samples.append(pos)
    # keep persistent log of positions (for offline)
    log['positions'].append((round(player.x,4), round(player.y,4), round(player.z,4)))
    # trim
    cutoff = now - (WINDOW_SECONDS * 2)
    while pos_samples and pos_samples[0][2] < cutoff:
        pos_samples.pop(0)

def record_action(a):
    now = time.time()
    action_log.append((a, now))
    log['actions'].append(a)
    cutoff = now - (WINDOW_SECONDS * 2)
    while action_log and action_log[0][1] < cutoff:
        action_log.pop(0)

# ----------------- Spawned objects & Undo / Soft physics -----------------
spawned = []      # player-spawned boxes (Entity objects)
spawn_history = []  # for undo (store last entity refs)

def spawn_box_in_front():
    if len(spawned) >= MAX_SPAWNED:
        status_text.text = "[Warning] 엔티티 수 제한"
        return None
    pos = camera.world_position + camera.forward * 2.2 + Vec3(0, SPAWN_HEIGHT, 0)
    b = Entity(model='cube', scale=1, color=color.white, collider='box', position=pos)
    b.vel = Vec3(0,0,0)
    spawned.append(b)
    spawn_history.append(b)
    record_action('spawn')
    return b

def undo_last_spawn():
    if not spawn_history:
        status_text.text = "취소할 작업 없음"
        return
    b = spawn_history.pop()
    try:
        destroy(b)
        spawned.remove(b)
    except Exception:
        pass
    record_action('undo')
    status_text.text = "마지막 생성 취소됨"

# ----------------- Safety mechanics -----------------
checkpoint = None

def set_checkpoint(pos):
    global checkpoint
    if checkpoint:
        try: destroy(checkpoint)
        except: pass
    checkpoint = Entity(model='cube', position=(pos.x, pos.y+0.2, pos.z), scale=(0.8,0.2,0.8),
                        color=color.rgb(120,200,255), collider=None)
    log['events'].append({'t':time.time()-log['start_time'], 'name':'checkpoint_set', 'pos':(round(pos.x,2), round(pos.z,2))})

def soft_respawn():
    # teleport player to last checkpoint or map center
    if checkpoint:
        p = checkpoint.position + Vec3(0,1,0)
        player.position = (p.x, p.y+1, p.z)
    else:
        player.position = (GRID_SIZE//2, 4, GRID_SIZE//2)
    status_text.text = "안전하게 리스폰됨 — 벌칙 없음"
    record_action('soft_respawn')

# ----------------- Beacon (Destination) system -----------------
destination = {'beacon':None, 'ring':[], 'label':None, 'type':None}
DEST_PULSE_SPEED = 3.0
DEST_PULSE_SCALE = 0.35
DEST_RING_COUNT = 10

def clear_destination():
    if destination['beacon']:
        try: destroy(destination['beacon'])
        except: pass
    for r in list(destination['ring']):
        try: destroy(r)
        except: pass
    destination['ring'].clear()
    if destination['label']:
        try: destroy(destination['label'])
        except: pass
    destination['beacon'] = None
    destination['label'] = None
    destination['type'] = None

def _spawn_beacon_at(pos, color_val=color.azure, label_text="DEST"):
    b = Entity(model='sphere', position=(pos.x, pos.y+1.2, pos.z), scale=0.8, color=color_val, collider=None)
    arrow = Entity(model='cone', position=(pos.x, pos.y+2.2, pos.z), scale=(0.3,0.7,0.3), color=color_val, collider=None)
    lbl = Text(label_text, world=True, position=(pos.x, pos.y+2.6, pos.z), origin=(0,0))
    ring = []
    for i in range(DEST_RING_COUNT):
        angle = i*(2*math.pi/DEST_RING_COUNT)
        rpos = Vec3(pos.x + math.cos(angle)*1.0, pos.y+0.9, pos.z + math.sin(angle)*1.0)
        dot = Entity(model='sphere', position=rpos, scale=0.08, color=color_val, collider=None)
        ring.append(dot)
    b.arrow = arrow
    destination['beacon'] = b
    destination['ring'] = ring
    destination['label'] = lbl
    return b

def pick_destination_tile(preference='random'):
    # preference: 'far','center','near'
    if not floor_tiles: return None
    if preference == 'far':
        best = None; best_d = -1
        for f in floor_tiles:
            d = (Vec3(f.x,0,f.z) - camera.world_position).length()
            if d > best_d:
                best_d = d; best = f
        return best
    elif preference == 'center':
        center = Vec3(GRID_SIZE/2,0,GRID_SIZE/2)
        return min(floor_tiles, key=lambda f: (Vec3(f.x,0,f.z)-center).length())
    else:
        near = [f for f in floor_tiles if (Vec3(f.x,0,f.z)-camera.world_position).length() < 6]
        return random.choice(near) if near else random.choice(floor_tiles)

def set_destination(persona):
    clear_destination()
    if persona == 'Explorer':
        target = pick_destination_tile('far')
        if not target: return
        _spawn_beacon_at(Vec3(target.x, target.y, target.z), color_val=color.yellow, label_text="Hidden Cache")
        destination['type'] = 'Explorer'
        # gentle hint: set a checkpoint near beacon so player can experiment safely
        set_checkpoint(Vec3(target.x, target.y+0.5, target.z))
    elif persona == 'Analyst':
        target = pick_destination_tile('center')
        if not target: return
        _spawn_beacon_at(Vec3(target.x, target.y, target.z), color_val=color.cyan, label_text="Optimal Node")
        destination['type'] = 'Analyst'
    elif persona == 'Verifier':
        target = pick_destination_tile('near')
        if not target: return
        _spawn_beacon_at(Vec3(target.x, target.y, target.z), color_val=color.green, label_text="Safe Hub")
        destination['type'] = 'Verifier'
        set_checkpoint(Vec3(target.x, target.y+0.5, target.z))
    else:
        destination['type'] = 'Neutral'

# ----------------- Mini-puzzle generation on reach -----------------
active_mini = { 'plate': None, 'boxes': [], 'required': 2, 'active': False }

def spawn_mini_puzzle(center_pos):
    # create a small area with a plate and some boxes to push onto it
    clear_mini_puzzle()
    cx, cz = int(center_pos.x), int(center_pos.z)
    plate = Entity(model='cube', position=(cx+1, 0.02, cz), scale=(1.0,0.04,1.0), color=color.orange, collider=None)
    boxes = []
    # spawn 3 boxes near the center
    offsets = [(-1,0), (0,1), (1,1)]
    for dx, dz in offsets:
        b = Entity(model='cube', position=(cx+dx, SPAWN_HEIGHT, cz+dz), color=color.rgb(230,230,230), scale=0.9, collider='box')
        b.vel = Vec3(0,0,0)
        boxes.append(b)
    active_mini['plate'] = plate
    active_mini['boxes'] = boxes
    active_mini['required'] = 2
    active_mini['active'] = True
    log['events'].append({'t':time.time()-log['start_time'], 'name':'mini_spawned', 'pos':(cx,cz)})

def clear_mini_puzzle():
    if active_mini['plate']:
        try: destroy(active_mini['plate'])
        except: pass
    for b in list(active_mini['boxes']):
        try: destroy(b)
        except: pass
    active_mini['plate'] = None
    active_mini['boxes'].clear()
    active_mini['active'] = False

def check_mini_puzzle_solved():
    if not active_mini['active']: return False
    plate_pos = active_mini['plate'].position
    count = 0
    for b in active_mini['boxes']:
        # check horizontal proximity to plate center
        dx = abs(b.x - plate_pos.x)
        dz = abs(b.z - plate_pos.z)
        if dx < 0.6 and dz < 0.6 and b.y < 1.0:
            count += 1
    if count >= active_mini['required']:
        # solved: give reward token and clear mini
        t = Entity(model='sphere', position=(plate_pos.x, plate_pos.y+0.4, plate_pos.z), color=color.yellow, scale=0.4)
        # small animation: expand then disappear
        invoke(lambda e=t: destroy(e), delay=6)
        log['events'].append({'t':time.time()-log['start_time'], 'name':'mini_solved', 'count':count})
        clear_mini_puzzle()
        # move beacon to new spot (generate next)
        set_destination(detect_persona()[0])
        return True
    return False

# ----------------- Persona detection (sliding window) -----------------
def detect_persona(window=WINDOW_SECONDS):
    now = time.time()
    pos_w = [p for p in pos_samples if p[2] >= now - window]
    act_w = [a for a in action_log if a[1] >= now - window]
    if len(pos_w) < 4 and len(act_w) < 2:
        return ('Neutral', 'not enough data')
    total = len(pos_w)
    uniq = len(set((p[0], p[1]) for p in pos_w))
    pos_ratio = uniq / max(1, total)
    unique_actions = len(set(a[0] for a in act_w))
    if pos_ratio >= EXPLORER_POS_RATIO and len(pos_w) >= 6:
        return ('Explorer', f'pos_ratio={pos_ratio:.2f}')
    if unique_actions <= ANALYST_UNIQ_ACTIONS and len(act_w) >= 3:
        return ('Analyst', f'unique_actions={unique_actions}')
    return ('Verifier', f'pos_ratio={pos_ratio:.2f}, actions={unique_actions}')

# ----------------- Animation for destination -----------------
def animate_destination(dt):
    b = destination.get('beacon')
    if not b: return
    t = time.time()
    pulse = 1.0 + DEST_PULSE_SCALE * (0.5 + 0.5*math.sin(t * DEST_PULSE_SPEED))
    try:
        b.scale = Vec3(pulse, pulse, pulse)
    except: pass
    try:
        if hasattr(b, 'arrow'):
            b.arrow.rotation_y += 120 * dt
    except: pass
    for i, dot in enumerate(destination['ring']):
        try:
            angle = (t * 1.5 + i * (2*math.pi/DEST_RING_COUNT))
            dot.x = b.x + math.cos(angle) * 1.0
            dot.z = b.z + math.sin(angle) * 1.0
        except: continue

# ----------------- Save log -----------------
def save_log():
    try:
        log['end_time'] = time.time()
        log['meta'] = {}
        log['meta']['total_time'] = log['end_time'] - log['start_time']
        log['meta']['unique_positions'] = len(set([ (x,y) for x,y,t in log['positions'] ])) if log['positions'] else 0
        fname = time.strftime("playerlog_safe_%Y%m%d_%H%M%S.json")
        path = os.path.join(LOG_DIR, fname)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(log, f, indent=2, ensure_ascii=False)
        print("[LOG SAVED]", path)
    except Exception as e:
        print("[ERROR] failed saving log:", e)
        traceback.print_exc()

# ----------------- Update loop -----------------
last_sample_time = time.time()
persona = 'Neutral'
persona_reason = ''
adapt_time = 0.0
welcome_duration = 6.0

def update():
    global last_sample_time, persona, persona_reason, adapt_time, welcome_timer
    dt = time.dt
    now = time.time()

    # fade-out welcome
    global welcome_timer
    if welcome_timer < welcome_duration:
        welcome_timer += dt
        alpha = max(0, 1 - welcome_timer / welcome_duration)
        welcome.color = color.rgba(200,220,255, int(255*alpha))
        if welcome_timer >= welcome_duration:
            destroy(welcome)

    # sample position periodically
    if now - last_sample_time >= SAMPLE_INTERVAL:
        record_pos(); last_sample_time = now

    # simple physics for spawned boxes (soft)
    for b in list(spawned):
        try:
            b.vel.y -= CUBE_GRAVITY * dt
            b.position += b.vel * dt
            half = b.scale_y/2.0
            if b.y - half <= 0.0:
                b.y = 0.0 + half
                if abs(b.vel.y) > 0.5:
                    b.vel.y = -b.vel.y * 0.08
                else:
                    b.vel.y = 0
                b.vel.x *= 0.98; b.vel.z *= 0.98
        except Exception:
            continue

    # animate destination visuals
    animate_destination(dt)

    # detect persona every 2 seconds (throttle)
    if now - adapt_time > 2.0:
        new_persona, reason = detect_persona()
        if new_persona != persona:
            persona = new_persona; persona_reason = reason; adapt_time = now
            # apply friendly changes and set destination
            apply_persona_changes(persona)
            set_destination(persona)
            status_text.text = f"[Adapt] {persona} ({reason})"
            # ensure a checkpoint when persona is Explorer/Verifier
            if destination['type'] in ('Explorer','Verifier'):
                # checkpoint already set in set_destination, but double ensure
                pass
        else:
            # refresh occasionally
            if now - adapt_time > 8.0:
                set_destination(persona); adapt_time = now

    persona_text.text = f"Persona: {persona}"

    # mini puzzle check
    if active_mini['active']:
        check_mini_puzzle_solved()

    # soft-fall check (no death)
    if player.y < -10:
        soft_respawn()

# ----------------- Input handling -----------------
def input(key):
    if key == 'escape':
        record_action('escape'); save_log(); application.quit()
    elif key == 'e':
        b = spawn_box_in_front()
        if b:
            status_text.text = "상자 생성"
    elif key == 'q':
        # delete nearest spawned in front
        # find nearest spawned in front
        cam_pos = camera.world_position; cam_forward = camera.forward
        best = None; bd = 1e9
        for s in spawned:
            dvec = s.world_position - cam_pos
            d = dvec.length()
            if d < bd and d < 3.5 and dvec.normalized().dot(cam_forward) > 0.4:
                best = s; bd = d
        if best:
            try: destroy(best); spawned.remove(best)
            except: pass
            record_action('delete'); status_text.text = "삭제됨"
    elif key == 'r':
        # clear all spawned boxes
        for s in list(spawned):
            try: destroy(s)
            except: pass
        spawned.clear(); spawn_history.clear()
        record_action('clear'); status_text.text = "모두 제거됨"
    elif key == 'u':
        undo_last_spawn()
    elif key == 'h':
        # temporary hint: small line pointing to beacon (if exists)
        if destination['beacon']:
            # create 6 markers towards beacon (auto removed)
            start = camera.world_position
            end = destination['beacon'].position
            steps = 6
            for i in range(1, steps+1):
                p = start.lerp(end, i/(steps+1))
                m = Entity(model='cube', position=(p.x, 0.12, p.z), scale=0.18, color=color.azure)
                invoke(destroy, m, delay=3.0)
            record_action('hint'); status_text.text = "힌트 표시(3s)"
    elif key == 'c':
        # cheat: complete mini puzzle instantly for testing (friendly)
        if active_mini['active']:
            # drop required number of boxes onto plate by teleporting boxes
            plate = active_mini['plate']
            boxes = active_mini['boxes'][:active_mini['required']]
            for i,b in enumerate(boxes):
                b.position = plate.position + Vec3(0, 0.5, 0)
                b.vel = Vec3(0, -1, 0)
            record_action('cheat_complete')

# ----------------- Beacon reach & mini-puzzle trigger check -----------------
def late_update():
    # if beacon exists and player near, trigger mini-puzzle spawn (and reward)
    b = destination.get('beacon')
    if b:
        if (Vec3(b.x,b.y,b.z) - camera.world_position).length() < 2.0:
            # reached destination
            if destination['type'] == 'Explorer' or destination['type'] == 'Analyst' or destination['type'] == 'Verifier':
                # spawn mini puzzle at b (if none active)
                if not active_mini['active']:
                    spawn_mini_puzzle(Vec3(b.x,b.y,b.z))
                    status_text.text = "새 퍼즐 생성됨 — 자유롭게 시도해보세요!"
                    log['events'].append({'t':time.time()-log['start_time'], 'name':'beacon_reached', 'persona':destination['type']})
                    # create checkpoint at beacon for player safety
                    set_checkpoint(Vec3(b.x,b.y,b.z))
                    # small reward: mark event
                    # remove old beacon so player explores the mini puzzle
                    clear_destination()

# ----------------- Clean exit (SIGINT) -----------------
import signal, sys
def _sigint(sig, frame):
    print("SIGINT: saving log and exiting")
    save_log(); application.quit(); sys.exit(0)
signal.signal(signal.SIGINT, _sigint)

# ----------------- Start by setting neutral destination -----------------
set_destination('Neutral')

# ----------------- Run the app -----------------
app.run()
# dmld.py