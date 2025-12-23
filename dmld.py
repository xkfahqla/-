from ursina import *
from ursina.prefabs.first_person_controller import FirstPersonController
import random, time
from collections import defaultdict, deque

app = Ursina()
window.color = color.rgb(18,20,26)

# ================= Player =================
player = FirstPersonController()
player.position = Vec3(5,4,5)
player.speed = 7
player.cursor.visible = False
player.prev_position = player.position

SPAWN_POINT = Vec3(5,4,5)

# ================= HUD =================
persona_text = Text(
    text='Persona: Neutral',
    position=(-0.85, 0.45),
    scale=1.2,
    background=True
)

# ================= Map System (A) =================
floor_tiles = {}

def spawn_tile(x,z):
    e = Entity(
        model='cube',
        scale=(1,0.1,1),
        position=(x,-0.05,z),
        color=color.light_gray,
        collider='box'
    )
    floor_tiles[(x,z)] = e

def ensure_map(radius=15):
    cx, cz = int(player.x), int(player.z)
    for x in range(cx-radius, cx+radius):
        for z in range(cz-radius, cz+radius):
            if (x,z) not in floor_tiles and random.random() < 0.8:
                spawn_tile(x,z)

# ================= Goal =================
goal = Entity(
    model='sphere',
    color=color.azure,
    scale=0.7,
    position=(10,1,10),
    collider='box'
)

def relocate_goal():
    goal.position = Vec3(
        random.randint(int(player.x)-12, int(player.x)+12),
        1,
        random.randint(int(player.z)-12, int(player.z)+12)
    )

# ================= Obstacles (B) =================
class ChaserCube(Entity):
    def __init__(self):
        super().__init__(
            model='cube',
            color=color.red,
            position=(0,1,0),
            collider='box'
        )

    def update(self):
        d = player.position - self.position
        self.position += d.normalized() * time.dt * 2.5
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
        self.position += d.normalized() * time.dt * 3
        if self.intersects(goal).hit:
            relocate_goal()

chaser = ChaserCube()
saboteur = SaboteurOrb()

# ================= Persona System =================
speed_log = deque(maxlen=120)
jump_count = 0
retry_count = 0

persona_ema = defaultdict(float)
CURRENT_PERSONA = 'Neutral'
LAST_CHANGE = 0

EMA_ALPHA = 0.1
CHANGE_COOLDOWN = 6

def detect_persona():
    global CURRENT_PERSONA, LAST_CHANGE

    avg_speed = sum(speed_log)/len(speed_log) if speed_log else 0

    scores = defaultdict(float)
    scores['검증가'] += 1 if avg_speed < 2 else 0
    scores['스피드러너'] += avg_speed
    scores['모험가'] += jump_count * 0.2
    scores['전략가'] += retry_count * 0.3

    for p in scores:
        persona_ema[p] = EMA_ALPHA*scores[p] + (1-EMA_ALPHA)*persona_ema[p]

    best = max(persona_ema, key=lambda k: persona_ema[k])
    now = time.time()

    if best != CURRENT_PERSONA and now-LAST_CHANGE > CHANGE_COOLDOWN:
        CURRENT_PERSONA = best
        LAST_CHANGE = now
        adapt_world(best)

def adapt_world(persona):
    if persona == '검증가':
        goal.color = color.green
    elif persona == '모험가':
        relocate_goal()
    elif persona == '스피드러너':
        player.speed = 9
    else:
        goal.color = color.azure
        player.speed = 7

# ================= Update =================
def update():
    ensure_map(15)

    # 속도 계산
    delta = player.position - player.prev_position
    speed = delta.length() / max(time.dt, 0.001)
    speed_log.append(speed)
    player.prev_position = player.position

    detect_persona()
    persona_text.text = f"Persona: {CURRENT_PERSONA}"

    if player.intersects(goal).hit:
        relocate_goal()

    if player.y < -10:
        player.position = SPAWN_POINT

def input(key):
    global jump_count, retry_count
    if key == 'space':
        jump_count += 1
    if key == 'r':
        retry_count += 1
        player.position = SPAWN_POINT

app.run()
