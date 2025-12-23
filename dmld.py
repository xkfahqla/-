from ursina import *
from ursina.prefabs.first_person_controller import FirstPersonController
import random, time, math
from collections import defaultdict, deque

app = Ursina()
window.color = color.rgb(18,20,26)

# ---------------- Player ----------------
player = FirstPersonController()
player.position = (5, 4, 5)
player.speed = 7
player.cursor.visible = False

last_player_pos = player.position

SPAWN_POINT = Vec3(5,4,5)

# ---------------- Map ----------------
floor_tiles = {}

def has_tile(x,z):
    return (x,z) in floor_tiles

def spawn_tile(x,z):
    t = Entity(
        model='cube',
        scale=(1,0.1,1),
        position=(x,-0.05,z),
        color=color.light_gray,
        collider='box'
    )
    floor_tiles[(x,z)] = t

def ensure_map(radius=15):
    cx, cz = int(player.x), int(player.z)
    for x in range(cx-radius, cx+radius):
        for z in range(cz-radius, cz+radius):
            if not has_tile(x,z) and random.random() < 0.7:
                spawn_tile(x,z)

# 초기 맵
ensure_map(20)

# ---------------- Goal ----------------
goal = Entity(
    model='sphere',
    color=color.azure,
    scale=0.7,
    position=(10,1,10),
    collider='box'
)

def relocate_goal():
    goal.position = Vec3(
        random.randint(int(player.x)-10, int(player.x)+10),
        1,
        random.randint(int(player.z)-10, int(player.z)+10)
    )

# ---------------- Persona System ----------------
PERSONAS = [
    "검증가","모험가","분석가","성취가","도박사",
    "스피드러너","글리치탐색가","몰입가",
    "자기경쟁가","예술가","창조자","전략가"
]

persona_scores = defaultdict(float)
persona_ema = defaultdict(float)
CURRENT_PERSONA = "중립"
LAST_CHANGE = 0

EMA_ALPHA = 0.12
CHANGE_COOLDOWN = 8.0

# 행동 기록
speed_log = deque(maxlen=120)
jump_count = 0
spawn_count = 0
retry_count = 0

def detect_persona():
    global CURRENT_PERSONA, LAST_CHANGE

    avg_speed = sum(speed_log)/len(speed_log) if speed_log else 0

    scores = defaultdict(float)
    scores["스피드러너"] += avg_speed
    scores["검증가"] += 1/(1+avg_speed)
    scores["모험가"] += random.random()*0.3
    scores["도박사"] += jump_count*0.2
    scores["창조자"] += spawn_count*0.3
    scores["전략가"] += retry_count*0.4

    # EMA 안정화
    for p in scores:
        persona_ema[p] = EMA_ALPHA*scores[p] + (1-EMA_ALPHA)*persona_ema[p]

    best = max(persona_ema, key=lambda k: persona_ema[k])
    now = time.time()

    if best != CURRENT_PERSONA and now-LAST_CHANGE > CHANGE_COOLDOWN:
        CURRENT_PERSONA = best
        LAST_CHANGE = now
        adapt_world(best)

# ---------------- Persona Adaptation ----------------
def adapt_world(persona):
    if persona == "검증가":
        goal.color = color.green
    elif persona == "모험가":
        relocate_goal()
    elif persona == "스피드러너":
        player.speed = 9
    else:
        goal.color = color.azure

# ---------------- Obstacles ----------------
class ChaserCube(Entity):
    def __init__(self):
        super().__init__(
            model='cube',
            color=color.red,
            scale=1,
            position=(0,1,0),
            collider='box'
        )

    def update(self):
        d = player.position - self.position
        self.position += d.normalized() * time.dt * 3
        if self.intersects(player).hit:
            player.position = SPAWN_POINT

class SaboteurOrb(Entity):
    def __init__(self):
        super().__init__(
            model='sphere',
            color=color.orange,
            scale=0.5,
            position=(15,1,15),
            collider='box'
        )

    def update(self):
        d = goal.position - self.position
        self.position += d.normalized() * time.dt * 4
        if self.intersects(goal).hit:
            relocate_goal()

chaser = ChaserCube()
saboteur = SaboteurOrb()

# ---------------- HUD ----------------
persona_text = Text("", position=(-0.8,0.45))

# ---------------- Update ----------------
def update():
    ensure_map(15)
    detect_persona()

    persona_text.text = f"Persona: {CURRENT_PERSONA}"

    if player.intersects(goal).hit:
        relocate_goal()

    if player.y < -10:
        player.position = SPAWN_POINT

def input(key):
    global jump_count, spawn_count, retry_count
    if key == 'space':
        jump_count += 1
    if key == 'r':
        retry_count += 1
        player.position = SPAWN_POINT
delta = player.position - last_player_pos
speed = delta.length() / max(time.dt, 0.001)
speed_log.append(speed)
app.run()