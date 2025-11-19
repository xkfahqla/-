from ursina import *
import random, math
from ursina.prefabs.first_person_controller import FirstPersonController
app=Ursina()
player=FirstPersonController()
player.position=(3,0,3)
player.cursor.visible=False
player.gravity=1
player.speed=10
player.collider = 'box'
def input(key):
    if key=='escape':
        application.quit()
    if key=="q":
        drop_box=Entity(
            model='cube',
            scale=1,
            position=(player.x,player.y-1,player.z),
            color=color.red,
            collider='box',
        )
        drop_box.gravity=10
        try:
            if drop_box.intersects(Floor).hit:
                destroy(drop_box)
        except Exception:
            pass
    if key=="e":
        player.y-=1
    if key=="q":
        player.y+=1
    if key=="r":
        drop_box=Entity(
            model='cube',
            scale=1,
            position=(player.x,player.y-1,player.z),
            color=color.red,
            collider='box'
        )
        drop_box.gravity=10
        try:
            if drop_box.intersects(Floor).hit:
                destroy(drop_box)
        except Exception:
            pass
Earth=[
    [1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1],
    [1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1],
    [1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1],
    [1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1],
    [1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1],
    [1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1],
    [1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1],
    [1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1],
    [1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1],
    [1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1],
    [1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1],
    [1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1],
    [1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1],
    [1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1],
    [1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1]
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
        """
        if A==2:
            drop_box=Entity(
                model='cube',
                scale=1,
                position=(i,100,j),
                color=color.red,
                collider='box',
            )
            drop_box.gravity=10
            try:
                if drop_box.intersects(Floor).hit:
                    destroy(drop_box)
            except Exception:
                pass
        """
        if A==3:
            Wall=Entity(
                model='wireframe_cube',
                scale=1,
                position=(i,1,j),
                color=color.white,
                collider='box'
            )
app.run()