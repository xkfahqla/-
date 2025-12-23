# persona_puzzle_game_fixed.py
# Requires: pip install ursina
# Run: python persona_puzzle_game_fixed.py

import os
import sys
import time
import math
import random
import json
import traceback
import signal

# try importing ursina
try:
    from ursina import *
    from ursina.prefabs.first_person_controller import FirstPersonController
except Exception as e:
    print("Ursina import failed. Install ursina (pip install ursina) to run the game.")
    print("Error:", e)
    sys.exit(1)

# ---------------- Config ----------------
GRID_SIZE = 28
SPARSE_TILE_PROB = 0.40
WALL_PROB = 0.14
SPAWN_HEIGHT = 3.0
CUBE_GRAVITY = 16.0
SAMPLE_INTERVAL = 0.15
WINDOW_SECONDS = 8.0
EXPLORER_POS_RATIO = 0.55
ANALYST_UNIQ_ACTIONS = 2
MAX_SPAWNED = 60
LOG_DIR = "logs_fixed"
os.makedirs(LOG_DIR, exist_ok=True)

# visual tuning
DEST_PULSE_SPEED = 3.0
DEST_PULSE_SCALE = 0.35
DEST_RING_COUNT = 10

# ---------------- App & Player ----------------
app = Ursina()
window.title = "Persona Puzzle (Fixed)"
window.color = color.rgb(18, 20, 25)

player = FirstPersonController()
player.position = (GRID_SIZE // 2, 4, GRID_SIZE // 2)
player.speed = 7
player.cursor.visible = False
player.gravity = 1

# ---------------- World ----------------
floor_tiles = []
walls = []

def generate_world():
    random.seed(int(time.time()))
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

generate_world()

# ---------------- HUD ----------------
persona_text = Text("Persona: Neutral", position=(-0.75, 0.45), scale=1.1)
status_text = Text("", position=(0.6, 0.45))
hint_text = Text("", position=(-0.75, 0.40), color=color.azure)

welcome = Text("여기는 안전한 실험 공간입니다. 자유롭게 시도하세요!", origin=(0,0), scale=1.1, y=0.33, color=color.rgb(200,220,255))
welcome_timer = 0.0
WELCOME_DURATION = 6.0

# ---------------- Logging ----------------
log = {'positions': [], 'actions': [], 'events': [], 'start_time': time.time()}
pos_samples = []
action_log = []

def record_pos():
    now = time.time()
    pos = (round(player.x,2), round(player.z,2), now)
    pos_samples.append(pos)
    log['positions'].append((round(player.x,4), round(player.y,4), round(player.z,4)))
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

# ---------------- Spawned boxes & undo ----------------
spawned = []
spawn_history = []

def spawn_box_in_front():
    if len(spawned) >= MAX_SPAWNED:
        status_text.text = "[경고] 생성 수 제한"
        return None
    pos = camera.world_position + camera.forward * 2.2 + Vec3(0, SPAWN_HEIGHT, 0)
    b = Entity(model='cube', scale=1, color=color.white, position=pos, collider='box')
    b.vel = Vec3(0,0,0)
    spawned.append(b)
    spawn_history.append(b)
    record_action('spawn')
    return b

def undo_last_spawn():
    if not spawn_history:
        status_text.text = "취소할 작업이 없습니다"
        return
    b = spawn_history.pop()
    try:
        destroy(b)
        spawned.remove(b)
    except Exception:
        pass
    record_action('undo')
    status_text.text = "마지막 생성 취소됨"

# ---------------- Safety: checkpoint & soft respawn ----------------
checkpoint = None

def set_checkpoint_at(pos):
    global checkpoint
    try:
        if checkpoint:
            destroy(checkpoint)
    except:
        pass
    checkpoint = Entity(model='cube', position=(pos.x, pos.y+0.2, pos.z), scale=(0.8,0.2,0.8), color=color.rgb(120,200,255))
    log['events'].append({'t': time.time()-log['start_time'], 'name':'checkpoint_set', 'pos':(round(pos.x,2), round(pos.z,2))})

def soft_respawn():
    if checkpoint:
        dest = checkpoint.position + Vec3(0,1,0)
        player.position = (dest.x, dest.y+1, dest.z)
    else:
        player.position = (GRID_SIZE//2, 4, GRID_SIZE//2)
    status_text.text = "안전하게 리스폰되었습니다"
    record_action('soft_respawn')

# ---------------- Destination (Beacon) ----------------
destination = {'beacon': None, 'ring': [], 'label': None, 'type': None}

def clear_destination():
    # safely destroy existing destination entities
    try:
        if destination['beacon']:
            destroy(destination['beacon'])
    except:
        pass
    for r in list(destination['ring']):
        try: destroy(r)
        except: pass
    destination['ring'].clear()
    try:
        if destination['label']:
            destroy(destination['label'])
    except:
        pass
    destination['beacon'] = None
    destination['label'] = None
    destination['type'] = None

def spawn_beacon_at(pos, col=color.azure, txt="DEST"):
    # create beacon + small ring + label
    b = Entity(model='sphere', position=(pos.x, pos.y+1.2, pos.z), scale=0.8, color=col)
    # arrow/orb above (simple small cone)
    arrow = Entity(model='cone', position=(pos.x, pos.y+2.2, pos.z), scale=(0.3,0.7,0.3), color=col)
    # ring particles
    ring = []
    for i in range(DEST_RING_COUNT):
        angle = i * (2*math.pi/DEST_RING_COUNT)
        rpos = Vec3(pos.x + math.cos(angle)*1.0, pos.y+0.9, pos.z + math.sin(angle)*1.0)
        dot = Entity(model='sphere', position=rpos, scale=0.08, color=col)
        ring.append(dot)
    lbl = Text(txt, world=True, position=(pos.x, pos.y+2.6, pos.z), origin=(0,0))
    b.arrow = arrow
    destination['beacon'] = b
    destination['ring'] = ring
    destination['label'] = lbl
    return b

def pick_destination(preference='random'):
    if not floor_tiles: return None
    if preference == 'far':
        best = None; best_d = -1
        for f in floor_tiles:
            d = (Vec3(f.x,0,f.z) - camera.world_position).length()
            if d > best_d:
                best_d = d; best = f
        return best
    if preference == 'center':
        center = Vec3(GRID_SIZE/2,0,GRID_SIZE/2)
        return min(floor_tiles, key=lambda f: (Vec3(f.x,0,f.z)-center).length())
    # near
    near = [f for f in floor_tiles if (Vec3(f.x,0,f.z)-camera.world_position).length() < 6]
    return random.choice(near) if near else random.choice(floor_tiles)

def set_destination_for_persona(persona):
    clear_destination()
    if persona == 'Explorer':
        target = pick_destination('far')
        if not target: return
        spawn_beacon_at(Vec3(target.x, target.y, target.z), col=color.yellow, txt="Hidden Cache")
        set_checkpoint_at(Vec3(target.x, target.y+0.5, target.z))
        destination['type'] = 'Explorer'
    elif persona == 'Analyst':
        target = pick_destination('center')
        if not target: return
        spawn_beacon_at(Vec3(target.x, target.y, target.z), col=color.cyan, txt="Optimal Node")
        destination['type'] = 'Analyst'
    elif persona == 'Verifier':
        target = pick_destination('near')
        if not target: return
        spawn_beacon_at(Vec3(target.x, target.y, target.z), col=color.green, txt="Safe Hub")
        set_checkpoint_at(Vec3(target.x, target.y+0.5, target.z))
        destination['type'] = 'Verifier'
    else:
        destination['type'] = 'Neutral'

# ---------------- Mini puzzle ----------------
active_mini = {'plate': None, 'boxes': [], 'required': 2, 'active': False}

def spawn_mini_puzzle_at(center_pos):
    clear_mini_puzzle()
    cx, cz = int(center_pos.x), int(center_pos.z)
    plate = Entity(model='cube', position=(cx+1, 0.02, cz), scale=(1.0, 0.04, 1.0), color=color.orange)
    boxes = []
    offsets = [(-1,0),(0,1),(1,1)]
    for dx, dz in offsets:
        b = Entity(model='cube', position=(cx+dx, SPAWN_HEIGHT, cz+dz), color=color.rgb(230,230,230), scale=0.9, collider='box')
        b.vel = Vec3(0,0,0)
        boxes.append(b)
    active_mini['plate'] = plate
    active_mini['boxes'] = boxes
    active_mini['required'] = 2
    active_mini['active'] = True
    log['events'].append({'t': time.time()-log['start_time'], 'name':'mini_spawned', 'pos':(cx,cz)})

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

def check_mini_solved():
    if not active_mini['active']: return False
    plate_pos = active_mini['plate'].position
    count = 0
    for b in active_mini['boxes']:
        dx = abs(b.x - plate_pos.x)
        dz = abs(b.z - plate_pos.z)
        if dx < 0.6 and dz < 0.6 and b.y < 1.0:
            count += 1
    if count >= active_mini['required']:
        t = Entity(model='sphere', position=(plate_pos.x, plate_pos.y+0.4, plate_pos.z), color=color.yellow, scale=0.4)
        invoke(lambda e=t: destroy(e), delay=6)
        log['events'].append({'t': time.time()-log['start_time'], 'name':'mini_solved', 'count':count})
        clear_mini_puzzle()
        # next beacon spawn for same persona
        cur_persona = detect_persona()[0]
        set_destination_for_persona(cur_persona)
        return True
    return False

# ---------------- Persona detection ----------------
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

# ---------------- Beacon animation ----------------
def animate_beacon(dt):
    b = destination.get('beacon')
    if not b: return
    t = time.time()
    pulse = 1.0 + DEST_PULSE_SCALE * (0.5 + 0.5 * math.sin(t * DEST_PULSE_SPEED))
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

# ---------------- Save log ----------------
def save_log_to_disk():
    try:
        log['end_time'] = time.time()
        log['meta'] = {}
        log['meta']['total_time'] = log['end_time'] - log['start_time']
        log['meta']['unique_positions'] = len(set([ (x,y) for x,y,t in log['positions'] ])) if log['positions'] else 0
        fname = time.strftime("playerlog_fixed_%Y%m%d_%H%M%S.json")
        path = os.path.join(LOG_DIR, fname)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(log, f, indent=2, ensure_ascii=False)
        print("[LOG SAVED]", path)
    except Exception as e:
        print("[ERROR] saving log:", e)
        traceback.print_exc()

# ---------------- Update & Input (Ursina hooks) ----------------
last_sample = time.time()
persona = 'Neutral'
persona_reason = ''
adapt_time = 0.0

def update():
    global last_sample, persona, persona_reason, adapt_time, welcome_timer
    dt = time.dt
    now = time.time()

    # welcome fade
    if 'welcome_timer' in globals():
        welcome_timer_local = globals().get('welcome_timer', 0.0)
        # increment and fade
        if welcome_timer_local < WELCOME_DURATION:
            welcome_timer_local += dt
            alpha = max(0.0, 1.0 - welcome_timer_local / WELCOME_DURATION)
            try:
                welcome.color = color.rgba(200,220,255, int(255*alpha))
            except:
                pass
            globals()['welcome_timer'] = welcome_timer_local
            if welcome_timer_local >= WELCOME_DURATION:
                try: destroy(welcome)
                except: pass

    # periodic position sample
    if now - last_sample >= SAMPLE_INTERVAL:
        record_pos(); last_sample = now

    # physics for spawned boxes (soft)
    for b in list(spawned):
        try:
            b.vel.y -= CUBE_GRAVITY * dt
            b.position += b.vel * dt
            half = b.scale_y / 2.0
            if b.y - half <= 0.0:
                b.y = 0.0 + half
                if abs(b.vel.y) > 0.5:
                    b.vel.y = -b.vel.y * 0.08
                else:
                    b.vel.y = 0
                b.vel.x *= 0.98
                b.vel.z *= 0.98
        except Exception:
            continue

    # animate beacon
    animate_beacon(dt)

    # persona detection throttle
    if now - adapt_time > 2.0:
        new_persona, reason = detect_persona()
        if new_persona != persona:
            persona = new_persona; persona_reason = reason; adapt_time = now
            status_text.text = f"[Adapt] {persona} ({reason})"
            # apply simple persona-driven changes (soft)
            if persona == 'Explorer':
                # make some walls disappear (softly) to encourage exploration
                for w in walls:
                    w.enabled = (random.random() < 0.7)
            elif persona == 'Analyst':
                for w in walls:
                    w.enabled = True
            elif persona == 'Verifier':
                for w in walls:
                    w.enabled = False
            # set beacon and checkpoint
            set_destination_for_persona(persona)
        else:
            if now - adapt_time > 8.0:
                set_destination_for_persona(persona); adapt_time = now

    persona_text.text = f"Persona: {persona}"

    # mini puzzle solved check
    if active_mini['active']:
        check_mini_solved()

    # soft fall safety
    if player.y < -10:
        soft_respawn()

def input(key):
    if key == 'escape':
        record_action('escape'); save_log_to_disk(); application.quit()
    elif key == 'e':
        b = spawn_box_in_front()
        if b:
            status_text.text = "상자 생성됨"
    elif key == 'q':
        # nearest spawned in front delete
        cam_pos = camera.world_position; cam_f = camera.forward
        best = None; bd = 1e9
        for s in spawned:
            dvec = s.world_position - cam_pos
            d = dvec.length()
            if d < bd and d < 3.5 and dvec.normalized().dot(cam_f) > 0.4:
                best = s; bd = d
        if best:
            try: destroy(best); spawned.remove(best)
            except: pass
            record_action('delete'); status_text.text = "삭제됨"
    elif key == 'r':
        for s in list(spawned):
            try: destroy(s)
            except: pass
        spawned.clear(); spawn_history.clear()
        record_action('clear'); status_text.text = "모두 제거됨"
    elif key == 'u':
        undo_last_spawn()
    elif key == 'h':
        # hint line to beacon
        b = destination.get('beacon')
        if b:
            start = camera.world_position; end = b.position
            steps = 6
            for i in range(1, steps+1):
                p = start.lerp(end, i/(steps+1))
                m = Entity(model='cube', position=(p.x, 0.12, p.z), scale=0.18, color=color.azure)
                invoke(destroy, m, delay=3.0)
            record_action('hint'); status_text.text = "힌트 표시(3s)"
    elif key == 'c':
        # test-complete mini puzzle instantly
        if active_mini['active']:
            plate = active_mini['plate']
            boxes = active_mini['boxes'][:active_mini['required']]
            for b in boxes:
                b.position = plate.position + Vec3(0,0.5,0); b.vel = Vec3(0,-1,0)
            record_action('cheat_complete')

# ---------------- late_update hook (Ursina supports it) ----------------
def late_update():
    b = destination.get('beacon')
    if b:
        # distance from player's camera to beacon
        if (Vec3(b.x,b.y,b.z) - camera.world_position).length() < 2.0:
            if not active_mini['active']:
                spawn_mini_puzzle_at(Vec3(b.x,b.y,b.z))
                status_text.text = "새 퍼즐 생성됨 — 자유롭게 시도하세요!"
                log['events'].append({'t': time.time()-log['start_time'], 'name':'beacon_reached', 'persona': destination['type']})
                # create checkpoint at beacon
                set_checkpoint_at(Vec3(b.x,b.y,b.z))
                # remove beacon to encourage focus on mini puzzle
                clear_destination()

# ---------------- SIGINT handler ----------------
def on_sigint(sig, frame):
    print("SIGINT: save log and exit")
    save_log_to_disk(); application.quit(); sys.exit(0)

signal.signal(signal.SIGINT, on_sigint)

# ---------------- initialize neutral destination and run ----------------
set_destination_for_persona('Neutral')

if __name__ == '__main__':
    app.run()
