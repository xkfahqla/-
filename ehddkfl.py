from ursina import *
import random, math
from ursina.prefabs.first_person_controller import FirstPersonController
from 추구미2 import feature_vector_from_log
app=Ursina()
player=FirstPersonController()
player.position=(3,10,3)
player.cursor.visible=False
player.gravity=1
player.speed=10
player.collider='box'
d = random.choice([0,1,2])
cb=[]
limmove=15
def input(key):
    if key=='escape':
        application.quit()
    if key=='e':
        cuby=Entity(
            model='cube',
            scale=1,
            position=(player.position.x,player.position.y+10,player.position.z),
            color=color.white,
            collider='box'
        )
        cb.append(cuby)
    if key=='q':
        if player.intersects(cuby):
            destroy(cuby)
    if key=='r':
        cb.clear()
underworld=[]
Earth=[
    [d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d],
    [d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d],
    [d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d],
    [d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d],
    [d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d],
    [d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d],
    [d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d],
    [d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d],
    [d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d],
    [d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d],
    [d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d],
    [d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d],
    [d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d],
    [d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d],
    [d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d,d]
    ]
for i in range(len(Earth)):
    for j in range(len(Earth[i])):
        A=Earth[i][j]
        if A==0:
            model=None
        if A==1:
            Floor=Entity(
                model='cube',
                scale=1,
                position=(i,0,j),
                color=color.white,
                collider='box'
            )
        if A==2:
            Wall=Entity(
                model='cube',
                scale=(1,random.random(),1),
                position=(i,1,j),
                color=color.white,
                collider='box'
            )
        underworld.append(A)
def detect_persona_realtime(window_log):
    vec, f = feature_vector_from_log(window_log)
    if f['pos_ratio'] > 0.6: return 'Explorer'
    if f['unique_actions'] < 3: return 'Analyst'
    if f['completes']>0 and f['restarts']<3: return 'Verifier'
    return 'Neutral'
def update():
    for cuby in cb:
        cuby.gravity=5
app.run()