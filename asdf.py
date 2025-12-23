# simple_stacking_highschool.py
# 실행: python simple_stacking_highschool.py
# 필요: pip install ursina

from ursina import *
import random

# ----------------- 설정(수정하기 쉬움) -----------------
GRID_ROWS = 15
GRID_COLS = 15
CELL_SIZE = 1
SPAWN_HEIGHT = 3.0      # E로 생성하면 이 높이에서 떨어짐
CUBE_GRAVITY = 18.0     # 상자에 적용할 중력
FLOOR_Y = 0.0
REACH = 3.5             # Q로 지울 때 최대 거리
# -----------------------------------------------------

app = Ursina()

# 플레이어(1인칭 컨트롤러)
from ursina.prefabs.first_person_controller import FirstPersonController
player = FirstPersonController()
player.position = (GRID_ROWS/2, 5, GRID_COLS/2)
player.speed = 8
player.cursor.visible = False

# 화면 설명 텍스트
Text("E: spawn cube | Q: delete nearest spawned cube | R: clear spawned cubes | ESC: quit",
     position=(-0.7, 0.45), scale=1.0)

# 저장해 둘 리스트 (플레이어가 생성한 상자들)
spawned = []

# 땅과 랜덤 벽 생성
for x in range(GRID_ROWS):
    for z in range(GRID_COLS):
        kind = random.choice([0,1,2])   # 0 empty, 1 floor, 2 wall
        world_x = x * CELL_SIZE
        world_z = z * CELL_SIZE
        if kind == 1:
            # 바닥 타일
            Entity(model='cube', scale=(1,0.1,1), position=(world_x, FLOOR_Y - 0.05, world_z),
                   color=color.light_gray, collider='box')
        elif kind == 2:
            # 벽: 높이를 랜덤으로 해서 안 묻히게 y를 height/2로 설정
            h = random.uniform(0.8, 2.0)
            Entity(model='cube', scale=(1,h,1), position=(world_x, h/2 + FLOOR_Y, world_z),
                   color=color.rgb(150,150,180), collider='box')
        # kind == 0 이면 아무것도 놓지 않음(빈 칸)

# helper: spawn a physics-like cube (간단 모사)
def spawn_cube():
    # 생성 위치: 카메라 앞 + 약간 위
    pos = camera.world_position + camera.forward * 2.5 + Vec3(0, SPAWN_HEIGHT, 0)
    c = Entity(model='cube', scale=1, color=color.white, position=pos, collider='box')
    # 물리 상태를 직접 붙임 (vel로 속도 관리)
    c.vel = Vec3(0,0,0)
    spawned.append(c)
    print("Spawned cube. Total spawned:", len(spawned))
    return c

# helper: 가장 가까운 spawned cube 찾기 (플레이어 앞, 시야 내)
def nearest_spawned_in_front(max_dist=REACH, min_dot=0.5):
    cam_pos = camera.world_position
    cam_forward = camera.forward
    best = None
    best_d = 1e9
    for c in spawned:
        dvec = c.world_position - cam_pos
        d = dvec.length()
        if d > max_dist: 
            continue
        # 앞쪽인지 확인 (dot이 크면 앞)
        if dvec.normalized().dot(cam_forward) < min_dot:
            continue
        if d < best_d:
            best_d = d
            best = c
    return best

# update: 간단한 중력 시뮬 (spawned에 대해서만)
def update():
    dt = time.dt
    # 물리 통합 (간단)
    for c in list(spawned):
        # 중력 가속
        c.vel.y -= CUBE_GRAVITY * dt
        # 위치 업데이트
        c.position += c.vel * dt
        # 바닥 충돌 검사 (y 방향만)
        half = c.scale_y / 2.0
        if c.y - half <= FLOOR_Y:
            c.y = FLOOR_Y + half
            # 충돌 후 속도 감쇠
            if abs(c.vel.y) > 0.5:
                c.vel.y = -c.vel.y * 0.1
            else:
                c.vel.y = 0
            # 수평 감쇠
            c.vel.x *= 0.98
            c.vel.z *= 0.98

# 입력 처리 (간단)
def input(key):
    if key == 'escape':
        app.quit()

    if key == 'e':
        spawn_cube()

    if key == 'q':
        t = nearest_spawned_in_front()
        if t:
            destroy(t)
            try:
                spawned.remove(t)
            except ValueError:
                pass
            print("Deleted one cube. Remaining:", len(spawned))

    if key == 'r':
        # 모두 지우기
        for c in list(spawned):
            destroy(c)
        spawned.clear()
        print("Cleared all spawned cubes.")

app.run()
# ----------------- 이전 버전 코드 (참고용) -----------------