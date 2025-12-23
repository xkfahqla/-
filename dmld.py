from ursina import *
from ursina.prefabs.first_person_controller import FirstPersonController
import random, math, time

# ===============================
# 기본 앱 설정
# ===============================
app = Ursina()
window.color = color.rgb(20, 20, 25)

# ===============================
# 플레이어
# ===============================
player = FirstPersonController()
player.position = (5, 3, 5)
player.gravity = 1
player.speed = 7
player.cursor.visible = False

# ===============================
# 맵 설정
# ===============================
GRID_SIZE = 30
floor_tiles = []
walls = []

def generate_map():
    for i in range(GRID_SIZE):
        for j in range(GRID_SIZE):
            # 바닥
            f = Entity(
                model='cube',
                scale=(1, 0.1, 1),
                position=(i, 0, j),
                color=color.rgb(200, 200, 200),
                collider='box'
            )
            floor_tiles.append(f)

            # 랜덤 벽
            if random.random() < 0.15:
                h = random.randint(1, 3)
                w = Entity(
                    model='cube',
                    scale=(1, h, 1),
                    position=(i, h/2, j),
                    color=color.rgb(120, 120, 140),
                    collider='box'
                )
                walls.append(w)

generate_map()

# ===============================
# 플레이 로그 (아주 단순)
# ===============================
log = {
    "positions": [],
    "actions": [],
    "start": time.time()
}

def record_position():
    p = player.position
    log["positions"].append((round(p.x,1), round(p.z,1)))

# ===============================
# 페르소나 판별 (단순 휴리스틱)
# ===============================
current_persona = "Neutral"

def detect_persona():
    global current_persona
    unique_pos = len(set(log["positions"]))
    total_pos = max(1, len(log["positions"]))
    pos_ratio = unique_pos / total_pos

    if pos_ratio > 0.6:
        return "Explorer"
    if len(log["actions"]) < 5:
        return "Analyst"
    if log["actions"].count("restart") > 2:
        return "Verifier"
    return "Neutral"

# ===============================
# 목적지(Beacon) 시스템
# ===============================
destination = None
ring_particles = []
label = None

def clear_destination():
    global destination, ring_particles, label
    if destination:
        destroy(destination)
    for r in ring_particles:
        destroy(r)
    ring_particles.clear()
    if label:
        destroy(label)
    destination = None
    label = None

def set_destination(persona):
    clear_destination()

    # 위치 선택
    if persona == "Explorer":
        tile = max(
            floor_tiles,
            key=lambda f: distance(f.position, player.position)
        )
        c = color.yellow
        text = "Hidden Goal"

    elif persona == "Analyst":
        tile = floor_tiles[len(floor_tiles)//2]
        c = color.cyan
        text = "Optimal Node"

    elif persona == "Verifier":
        tile = min(
            floor_tiles,
            key=lambda f: distance(f.position, player.position)
        )
        c = color.green
        text = "Safe Zone"

    else:
        return

    pos = tile.position + Vec3(0,1.2,0)

    # 메인 비콘
    global destination
    destination = Entity(
        model='sphere',
        scale=0.8,
        position=pos,
        color=c
    )

    # 회전 링
    for i in range(10):
        angle = i * (2*math.pi/10)
        r = Entity(
            model='sphere',
            scale=0.1,
            color=c,
            position=pos + Vec3(math.cos(angle), 0, math.sin(angle))
        )
        ring_particles.append(r)

    # 라벨
    global label
    label = Text(
        text,
        world=True,
        position=pos + Vec3(0,1.2,0),
        scale=1.5,
        origin=(0,0)
    )

# ===============================
# 퍼즐 적응 로직
# ===============================
def apply_persona_changes(persona):
    if persona == "Explorer":
        for w in walls:
            w.enabled = random.random() < 0.7

    elif persona == "Analyst":
        for w in walls:
            w.enabled = True

    elif persona == "Verifier":
        for w in walls:
            w.enabled = False

    set_destination(persona)

# ===============================
# 업데이트 루프
# ===============================
timer = 0

def update():
    global timer, current_persona
    timer += time.dt

    record_position()

    # 비콘 애니메이션
    if destination:
        destination.rotation_y += 90 * time.dt
        s = 0.8 + 0.2 * math.sin(time.time()*3)
        destination.scale = s

        for i, r in enumerate(ring_particles):
            a = time.time()*2 + i
            r.position = destination.position + Vec3(math.cos(a), 0, math.sin(a))

    # 페르소나 판별 (2초마다)
    if timer > 2:
        timer = 0
        new_persona = detect_persona()
        if new_persona != current_persona:
            current_persona = new_persona
            apply_persona_changes(current_persona)

# ===============================
# 입력
# ===============================
def input(key):
    if key == 'escape':
        application.quit()
    if key == 'r':
        log["actions"].append("restart")
        player.position = (5,3,5)

# ===============================
# UI
# ===============================
persona_text = Text(
    "Persona: Neutral",
    position=(-0.75, 0.45),
    scale=1.5
)

def late_update():
    persona_text.text = f"Persona: {current_persona}"

app.run()
