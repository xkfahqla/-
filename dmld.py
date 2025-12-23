# persona_game_dynamic.py
# Requires: pip install ursina
# Run: python persona_game_dynamic.py

import os, sys, time, math, random, json, traceback, signal
from collections import deque

# try ursina import
try:
    from ursina import *
    from ursina.prefabs.first_person_controller import FirstPersonController
except Exception as e:
    print("Ursina import failed. Install ursina (pip install ursina). Error:", e)
    sys.exit(1)

# ---------------- Config (튜닝하기 쉬움) ----------------
GRID_SIZE = 28
SPARSE_TILE_PROB = 0.40
WALL_PROB = 0.14
SPAWN_HEIGHT = 3.0
CUBE_GRAVITY = 16.0
SAMPLE_INTERVAL = 0.12
WINDOW_SECONDS = 10.0        # 슬라이딩 윈도우 길이(초)
NEAR_RADIUS = 15             # 플레이어 주변 반경 체크 (칸)
MIN_TILES_NEAR = 60          # 근처 타일이 이보다 작으면 생성
MAX_SPAWNED = 80
LOG_DIR = "logs_dynamic"
os.makedirs(LOG_DIR, exist_ok=True)
# ----------------------------------------------------

# visual params
DEST_PULSE_SPEED = 3.0
DEST_PULSE_SCALE = 0.35
DEST_RING_COUNT = 8

# ---------------- App & Player ----------------
app = Ursina()
window.title = "Persona Puzzle Dynamic"
window.color = color.rgb(18, 20, 25)

player = FirstPersonController()
player.position = (GRID_SIZE // 2, 4, GRID_SIZE // 2)
player.speed = 7
player.cursor.visible = False
player.gravity = 1

# ---------------- World containers ----------------
floor_tiles = []
walls = []

# create initial sparse world (but we will also dynamically add)
def generate_initial_world():
    random.seed(int(time.time()))
    half = GRID_SIZE // 2
    for x in range(GRID_SIZE):
        for z in range(GRID_SIZE):
            if random.random() < SPARSE_TILE_PROB:
                f = Entity(model='cube', scale=(1,0.08,1), position=(x, 0.0-0.04, z),
                           color=color.light_gray, collider='box')
                floor_tiles.append(f)
                if random.random() < WALL_PROB:
                    h = random.uniform(1.0, 2.2)
                    w = Entity(model='cube', scale=(1,h,1), position=(x, h/2, z),
                               color=color.rgb(120,120,140), collider='box')
                    walls.append(w)
generate_initial_world()

# ---------------- HUD ----------------
persona_text = Text("Persona: Neutral", position=(-0.75, 0.45), scale=1.1)
status_text = Text("", position=(0.6, 0.45))
info_text = Text("E spawn · Q delete · U undo · H hint · R clear · ESC save+quit", position=(-0.72, 0.41), scale=0.9, color=color.azure)

# ---------------- Logging & sliding buffers ----------------
log = {'positions': [], 'actions': [], 'events': [], 'start_time': time.time()}
# sliding position samples: store (x,z,t)
pos_buffer = deque()
# action buffer: (action,t)
action_buffer = deque()
# movement speed buffer (last N samples): store instantaneous speed (units/sec)
speed_buffer = deque()
# counts for windowed features
jump_buffer = deque()
interact_buffer = deque()
risky_buffer = deque()

def sample_position():
    now = time.time()
    xz = (round(player.x,3), round(player.z,3), now)
    pos_buffer.append(xz)
    log['positions'].append((round(player.x,4), round(player.y,4), round(player.z,4)))
    # maintain window length
    cutoff = now - (WINDOW_SECONDS)
    while pos_buffer and pos_buffer[0][2] < cutoff:
        pos_buffer.popleft()

def record_action(action_name):
    now = time.time()
    action_buffer.append((action_name, now))
    log['actions'].append(action_name)
    cutoff = now - (WINDOW_SECONDS)
    while action_buffer and action_buffer[0][1] < cutoff:
        action_buffer.popleft()

# compute instantaneous speed each time we sample (from last sample)
last_pos_for_speed = None
def sample_speed():
    global last_pos_for_speed
    now = time.time()
    p = (player.x, player.z)
    if last_pos_for_speed is not None:
        dt = now - last_pos_for_speed[2] if last_pos_for_speed[2] else 1e-6
        dist = math.hypot(p[0]-last_pos_for_speed[0], p[1]-last_pos_for_speed[1])
        speed = dist / max(dt, 1e-6)
        speed_buffer.append((speed, now))
        # maintain window
        cutoff = now - WINDOW_SECONDS
        while speed_buffer and speed_buffer[0][1] < cutoff:
            speed_buffer.popleft()
    last_pos_for_speed = (p[0], p[1], now)

# ---------------- Spawned boxes & undo ----------------
spawned = []
spawn_history = []

def spawn_box():
    if len(spawned) >= MAX_SPAWNED:
        status_text.text = "[경고] 생성 한도"
        return None
    pos = camera.world_position + camera.forward * 2.2 + Vec3(0, SPAWN_HEIGHT, 0)
    b = Entity(model='cube', scale=1, color=color.white, position=pos, collider='box')
    b.vel = Vec3(0,0,0)
    spawned.append(b)
    spawn_history.append(b)
    record_action('spawn')
    return b

def undo_spawn():
    if not spawn_history:
        status_text.text = "취소할 작업 없음"
        return
    b = spawn_history.pop()
    try:
        destroy(b); spawned.remove(b)
    except: pass
    record_action('undo'); status_text.text = "생성 취소됨"

# ---------------- Safety ----------------
checkpoint = None
def set_checkpoint(pos):
    global checkpoint
    try:
        if checkpoint: destroy(checkpoint)
    except: pass
    checkpoint = Entity(model='cube', position=(pos.x,pos.y+0.2,pos.z), scale=(0.8,0.2,0.8), color=color.rgb(120,200,255))
    log['events'].append({'t': time.time()-log['start_time'], 'name':'checkpoint_set', 'pos':(round(pos.x,2), round(pos.z,2))})

def soft_respawn():
    if checkpoint:
        dest = checkpoint.position + Vec3(0,1,0)
        player.position = (dest.x, dest.y+1, dest.z)
    else:
        player.position = (GRID_SIZE//2, 4, GRID_SIZE//2)
    record_action('soft_respawn'); status_text.text = "안전 리스폰"

# ---------------- Destination (Beacon) ----------------
destination = {'beacon': None, 'ring': [], 'label': None, 'type': None}
def clear_destination():
    try:
        if destination['beacon']: destroy(destination['beacon'])
    except: pass
    for r in list(destination['ring']): 
        try: destroy(r)
        except: pass
    destination['ring'].clear()
    try:
        if destination['label']: destroy(destination['label'])
    except: pass
    destination['beacon']=None; destination['label']=None; destination['type']=None

def spawn_beacon_at(pos, col=color.azure, txt="DEST"):
    b = Entity(model='sphere', position=(pos.x,pos.y+1.2,pos.z), scale=0.8, color=col)
    arrow = Entity(model='cone', position=(pos.x,pos.y+2.2,pos.z), scale=(0.25,0.6,0.25), color=col)
    ring=[]
    for i in range(DEST_RING_COUNT):
        a = i*(2*math.pi/DEST_RING_COUNT)
        dot = Entity(model='sphere', position=(pos.x+math.cos(a), pos.y+0.9, pos.z+math.sin(a)), scale=0.08, color=col)
        ring.append(dot)
    lbl = Text(txt, world=True, position=(pos.x,pos.y+2.6,pos.z), origin=(0,0))
    b.arrow = arrow
    destination['beacon']=b; destination['ring']=ring; destination['label']=lbl
    return b

def pick_tile(pref='random'):
    if not floor_tiles: return None
    if pref=='far':
        best=None; bd=-1
        for f in floor_tiles:
            d = (Vec3(f.x,0,f.z)-camera.world_position).length()
            if d>bd: bd=d; best=f
        return best
    if pref=='center':
        c=Vec3(GRID_SIZE/2,0,GRID_SIZE/2)
        return min(floor_tiles, key=lambda f: (Vec3(f.x,0,f.z)-c).length())
    near = [f for f in floor_tiles if (Vec3(f.x,0,f.z)-camera.world_position).length() < NEAR_RADIUS]
    return random.choice(near) if near else random.choice(floor_tiles)

def set_destination_for_persona(persona):
    clear_destination()
    if persona=='Explorer':
        tgt = pick_tile('far'); 
        if not tgt: return
        spawn_beacon_at(Vec3(tgt.x,tgt.y,tgt.z), col=color.yellow, txt="Hidden Cache")
        set_checkpoint(Vec3(tgt.x,tgt.y+0.5,tgt.z))
        destination['type']='Explorer'
    elif persona=='Analyst':
        tgt = pick_tile('center')
        if not tgt: return
        spawn_beacon_at(Vec3(tgt.x,tgt.y,tgt.z), col=color.cyan, txt="Optimal Node")
        destination['type']='Analyst'
    elif persona=='Verifier':
        tgt = pick_tile('near')
        if not tgt: return
        spawn_beacon_at(Vec3(tgt.x,tgt.y,tgt.z), col=color.green, txt="Safe Hub")
        set_checkpoint(Vec3(tgt.x,tgt.y+0.5,tgt.z))
        destination['type']='Verifier'
    else:
        destination['type']='Neutral'

# ---------------- Mini-puzzle ----------------
active_mini={'plate':None,'boxes':[],'required':2,'active':False}
def spawn_mini(center):
    clear_mini()
    cx,cz = int(center.x), int(center.z)
    plate = Entity(model='cube', position=(cx+1,0.02,cz), scale=(1.0,0.04,1.0), color=color.orange)
    boxes=[]
    offs=[(-1,0),(0,1),(1,1)]
    for dx,dz in offs:
        b = Entity(model='cube', position=(cx+dx, SPAWN_HEIGHT, cz+dz), color=color.rgb(230,230,230), scale=0.9, collider='box')
        b.vel=Vec3(0,0,0); boxes.append(b)
    active_mini['plate']=plate; active_mini['boxes']=boxes; active_mini['active']=True
    log['events'].append({'t':time.time()-log['start_time'],'name':'mini_spawned','pos':(cx,cz)})

def clear_mini():
    if active_mini['plate']:
        try: destroy(active_mini['plate'])
        except: pass
    for b in list(active_mini['boxes']):
        try: destroy(b)
        except: pass
    active_mini['plate']=None; active_mini['boxes'].clear(); active_mini['active']=False

def check_mini_solved():
    if not active_mini['active']: return False
    plate_pos=active_mini['plate'].position
    cnt=0
    for b in active_mini['boxes']:
        if abs(b.x-plate_pos.x)<0.6 and abs(b.z-plate_pos.z)<0.6 and b.y<1.0: cnt+=1
    if cnt>=active_mini['required']:
        t=Entity(model='sphere', position=(plate_pos.x,plate_pos.y+0.4,plate_pos.z), color=color.yellow, scale=0.4)
        invoke(lambda e=t: destroy(e), delay=6)
        log['events'].append({'t':time.time()-log['start_time'],'name':'mini_solved','count':cnt})
        clear_mini()
        set_destination_for_persona(detect_persona()[0])
        return True
    return False

# ---------------- Persona detection (고도화) ----------------
def compute_window_features():
    now=time.time()
    # positions
    pos_w = [p for p in pos_buffer]
    total = len(pos_w) or 1
    uniq = len(set((p[0],p[1]) for p in pos_w))
    pos_ratio = uniq / total
    # speed
    speeds = [s for s,_t in speed_buffer]
    avg_speed = sum(speeds)/len(speeds) if speeds else 0.0
    # actions counts in window
    actions = [a for a,_t in action_buffer]
    unique_actions = len(set(actions))
    jump_count = sum(1 for a,_t in action_buffer if a=='jump')
    interact_count = sum(1 for a,_t in action_buffer if a=='interact')
    risky_count = sum(1 for a,_t in action_buffer if a in ('risky','risky_action'))
    # idle ratio: fraction of speed samples < small threshold
    idle_frac = 0.0
    if speeds:
        idle_frac = sum(1 for v in speeds if v < 0.05) / len(speeds)
    # return dictionary
    return {
        'pos_ratio': pos_ratio,
        'avg_speed': avg_speed,
        'unique_actions': unique_actions,
        'jump_count': jump_count,
        'interact_count': interact_count,
        'risky_count': risky_count,
        'idle_frac': idle_frac
    }

def detect_persona():
    f = compute_window_features()
    # heuristics -> score each persona 0..1
    scores={}
    # Explorer: high pos_ratio and moderate-high avg_speed
    scores['Explorer'] = min(1.0, f['pos_ratio']*1.6 + (f['avg_speed']*0.2))
    # Analyst: low unique_actions, low avg_speed, low risky
    scores['Analyst'] = min(1.0, (1.0/(1.0+math.log(1+f['unique_actions']))) * (1.0 - f['risky_count']*0.1))
    # Verifier: low risky, moderate idle (careful), many restarts (we use 'restart' action count)
    restart_count = sum(1 for a,_t in action_buffer if a=='restart')
    scores['Verifier'] = min(1.0, (1.0 - min(1.0, f['risky_count']*0.2)) * (0.3 + min(1.0, restart_count/3.0)))
    # Achiever: many interacts
    scores['Achiever'] = min(1.0, f['interact_count'] / 5.0)
    # Gambler: risky actions and jumps
    scores['Gambler'] = min(1.0, (f['risky_count']*0.6 + f['jump_count']*0.1))
    # Immerser: long play (approx by having many samples + low idle)
    scores['Immerser'] = min(1.0, (len(pos_buffer)/ (WINDOW_SECONDS*10)) + (1.0 - f['idle_frac'])*0.5)
    # Speedrunner: high avg_speed and low unique_positions? (approx)
    scores['Speedrunner'] = min(1.0, (f['avg_speed']*0.3) + (1.0 - f['pos_ratio'])*0.2)
    # Creator: many undo/spawn events (count spawn & undo)
    spawn_count = sum(1 for a in log['actions'] if a=='spawn')
    undo_count = sum(1 for a in log['actions'] if a=='undo')
    scores['Creator'] = min(1.0, (spawn_count/10.0) + (undo_count/5.0))
    # pick top score
    best = max(scores.items(), key=lambda kv: kv[1])
    persona_label = best[0] if best[1] > 0.25 else 'Neutral'
    # return persona and full scores + features (for logging/debug)
    return persona_label, scores, f

# ---------------- Beacon animation ----------------
def animate_beacon(dt):
    b = destination.get('beacon')
    if not b: return
    t = time.time()
    pulse = 1.0 + DEST_PULSE_SCALE*(0.5+0.5*math.sin(t*DEST_PULSE_SPEED))
    try:
        b.scale = Vec3(pulse,pulse,pulse)
    except: pass
    try:
        if hasattr(b,'arrow'):
            b.arrow.rotation_y += 120 * dt
    except: pass
    for i,dot in enumerate(destination['ring']):
        try:
            angle = (t*1.2 + i*(2*math.pi/DEST_RING_COUNT))
            dot.x = b.x + math.cos(angle) * 1.0
            dot.z = b.z + math.sin(angle) * 1.0
        except: pass

# ---------------- Dynamic map generation near player ----------------
def count_floor_near(radius=NEAR_RADIUS):
    c = Vec3(player.x,0,player.z)
    cnt = 0
    for f in floor_tiles:
        if (Vec3(f.x,0,f.z) - c).length() <= radius:
            cnt += 1
    return cnt

def generate_area_around_player(radius=NEAR_RADIUS):
    # generate a square area centered on player (integer grid)
    cx = int(round(player.x))
    cz = int(round(player.z))
    half = radius
    created = 0
    for x in range(cx-half, cx+half+1):
        for z in range(cz-half, cz+half+1):
            # skip if tile already exists at that integer pos
            exists = any((int(f.x)==x and int(f.z)==z) for f in floor_tiles)
            if exists: continue
            # avoid generating hugely out-of-bounds negative coords
            if x < -10 or z < -10 or x > 300 or z > 300: 
                continue
            # probabilistic floor
            if random.random() < 0.65:
                try:
                    f = Entity(model='cube', scale=(1,0.08,1), position=(x, 0.0-0.04, z), color=color.light_gray, collider='box')
                    floor_tiles.append(f); created += 1
                except Exception:
                    continue
                # small chance to put a wall
                if random.random() < 0.12:
                    try:
                        h = random.uniform(1.0,2.0)
                        w = Entity(model='cube', scale=(1,h,1), position=(x,h/2,z), color=color.rgb(120,120,140), collider='box')
                        walls.append(w)
                    except: pass
    if created>0:
        status_text.text = f"맵 확장: 주변에 {created}개 타일 생성됨"
    return created

# ---------------- Save log ----------------
def save_log():
    try:
        log['end_time']=time.time()
        log['meta']={'total_time':log['end_time']-log['start_time']}
        fname=time.strftime("playerlog_dyn_%Y%m%d_%H%M%S.json")
        path=os.path.join(LOG_DIR,fname)
        with open(path,'w',encoding='utf-8') as f:
            json.dump(log,f,indent=2,ensure_ascii=False)
        print("[LOG SAVED]",path)
    except Exception as e:
        print("[ERROR] save failed:",e); traceback.print_exc()

# ---------------- Update & Input ----------------
last_sample_time=time.time()
adapt_time=0.0
current_persona='Neutral'

def update():
    global last_sample_time, adapt_time, current_persona
    dt = time.dt
    now = time.time()

    # sampling (position & speed)
    if now - last_sample_time >= SAMPLE_INTERVAL:
        # compute speed from last sample if available
        if pos_buffer:
            last = pos_buffer[-1]
            dt_pos = now - last[2] if now - last[2] > 1e-6 else 1e-6
            dist = math.hypot(player.x - last[0], player.z - last[1])
            speed = dist / dt_pos
            speed_buffer.append((speed, now))
            # maintain speed buffer window
            while speed_buffer and speed_buffer[0][1] < now - WINDOW_SECONDS:
                speed_buffer.popleft()
        # sample pos
        sample_position()
        sample_speed()
        last_sample_time = now

    # simple physics for spawned boxes
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
        except: continue

    # animate beacon
    animate_beacon(dt)

    # dynamic map generation if too few tiles near player
    cnt_near = count_floor_near(NEAR_RADIUS)
    if cnt_near < MIN_TILES_NEAR:
        generate_area_around_player(NEAR_RADIUS)

    # persona detect + adapt throttle
    if now - adapt_time > 2.0:
        persona_label, scores, feats = detect_persona()
        if persona_label != current_persona:
            current_persona = persona_label
            # apply light adaptations
            if current_persona=='Explorer':
                for w in walls: w.enabled = (random.random() < 0.7)
            elif current_persona=='Analyst':
                for w in walls: w.enabled = True
            elif current_persona=='Verifier':
                for w in walls: w.enabled = False
            set_destination_for_persona(current_persona)
            log['events'].append({'t':time.time()-log['start_time'],'name':'persona_changed','persona':current_persona,'scores':scores,'feats':feats})
            status_text.text = f"[적응] {current_persona}"
        adapt_time = now

    persona_text.text = f"Persona: {current_persona}"

    # mini puzzle check
    if active_mini['active']:
        check_mini_solved()

    # soft fall safety
    if player.y < -10:
        soft_respawn()

def input(key):
    if key == 'escape':
        record_action('escape'); save_log(); application.quit()
    elif key == 'e':
        b = spawn_box()
        if b: status_text.text = "상자 생성"
    elif key == 'q':
        # delete nearest spawned in front
        cam_pos = camera.world_position; cam_forward = camera.forward
        best=None; bd=1e9
        for s in spawned:
            dvec = s.world_position - cam_pos
            d = dvec.length()
            if d < bd and d < 3.5 and dvec.normalized().dot(cam_forward) > 0.4:
                best=s; bd=d
        if best:
            try: destroy(best); spawned.remove(best)
            except: pass
            record_action('delete'); status_text.text="삭제됨"
    elif key == 'u':
        undo_spawn()
    elif key == 'r':
        for s in list(spawned):
            try: destroy(s)
            except: pass
        spawned.clear(); spawn_history.clear(); record_action('clear'); status_text.text="모두 제거됨"
    elif key == 'h':
        b = destination.get('beacon')
        if b:
            start = camera.world_position; end = b.position
            steps = 6
            for i in range(1,steps+1):
                p = start.lerp(end, i/(steps+1))
                m = Entity(model='cube', position=(p.x,0.12,p.z), scale=0.18, color=color.azure)
                invoke(destroy, m, delay=3.0)
            record_action('hint'); status_text.text="힌트(3s)"

# late_update: trigger mini when reach beacon
def late_update():
    b = destination.get('beacon')
    if b:
        if (Vec3(b.x,b.y,b.z)-camera.world_position).length() < 2.0:
            if not active_mini['active']:
                spawn_mini(Vec3(b.x,b.y,b.z))
                status_text.text = "새 퍼즐 생성됨 — 자유롭게 시도!"
                log['events'].append({'t':time.time()-log['start_time'],'name':'beacon_reached','persona':destination['type']})
                set_checkpoint(Vec3(b.x,b.y,b.z))
                clear_destination()

# SIGINT save
def _sigint(sig, frame):
    print("SIGINT -> saving log and exit")
    save_log(); application.quit(); sys.exit(0)
signal.signal(signal.SIGINT, _sigint)

# initialize neutral
set_destination_for_persona('Neutral')

# run
if __name__ == '__main__':
    app.run()
