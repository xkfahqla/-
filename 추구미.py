"""
persona_game_with_analysis.py

Usage:
  # 1) 게임 실행 (Ursina 필요)
  python persona_game_with_analysis.py run

  # 2) 오프라인 분석 (logs/*.json 필요)
  python persona_game_with_analysis.py analyze

설명:
- run: 간단한 Ursina 기반 씬(FPS 컨트롤러)을 띄워 플레이 로그(positions, actions, events)를 수집.
- 종료(escape)하면 로그를 저장(./logs/YYYYMMDD_HHMMSS_playerlog.json).
- analyze: 저장된 로그들을 불러와 피처화 후 k-means (있으면) / 또는 휴리스틱으로 군집 및 희소 페르소나 탐색.
"""

import os, sys, json, time, math, argparse, glob
from collections import defaultdict, deque

########################
# ---------- CONFIG ----
########################
LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

# feature normalizers / constants (튜닝 가능)
MAX_EXPECTED_STEPS = 2000.0
MAX_EXPECTED_TIME = 3600.0  # 1 hour cap for normalization
KMEANS_CLUSTERS = 4

########################
# ---------- RUN MODE (Ursina game + logger) ----
########################
def run_game():
    try:
        from ursina import *
        from ursina.prefabs.first_person_controller import FirstPersonController
    except Exception as e:
        print("Ursina import failed. Install ursina to run the game. Error:", e)
        return

    app = Ursina()

    # --- basic world from your earlier example (small grid)
    Earth = [
        [1,1,1,1,1],
        [1,1,1,1,1],
        [1,1,1,1,1],
        [1,1,1,1,1]
    ]
    for i in range(len(Earth)):
        for j in range(len(Earth[i])):
            if Earth[i][j] == 1:
                Entity(model='cube', scale=1, position=(i,0,j), color=color.white, collider='box')

    # --- player
    player = FirstPersonController()
    player.position = (3,0,3)
    player.cursor.visible = False
    player.gravity = 1
    player.speed = 10
    player.collider = 'box'

    # --- logger state
    log = {
        'positions': [],            # sampled every frame (x,y,z)
        'actions': [],              # inputs like 'w','a','space', 'risky', 'jump'
        'events': [],               # semantic events: death, completion, out_of_bounds, restart, editor_use
        'items_collected': 0,
        'start_time': time.time(),
        'end_time': None,
        'meta': { 'map': 'default_grid' }
    }

    last_pos = player.position
    sample_accum = 0.0

    # helper: record an event
    def record_event(name, payload=None):
        t = time.time() - log['start_time']
        log['events'].append({'t':t, 'name':name, 'payload': payload or {}})

    # simple example: collect item on 'e' (no real item system here)
    def do_interact():
        # mark an interaction (could be used to detect immerser)
        record_event('interact')
        log['actions'].append('interact')

    # call risky_action when player presses 'q' (demo)
    def risky_action():
        record_event('risky_action')
        log['actions'].append('risky')

    # sample positions at fixed dt to avoid massive logs
    def update():
        nonlocal last_pos, sample_accum
        dt = time.dt
        sample_accum += dt
        # sample roughly 10Hz
        if sample_accum >= 0.1:
            sample_accum = 0.0
            p = player.position
            log['positions'].append( (round(p.x,3), round(p.y,3), round(p.z,3)) )
            # detect out_of_bounds (demo): if y < -5
            if p.y < -5:
                record_event('out_of_bounds')
        last_pos = player.position

    # input handling
    def input(key):
        # store raw keys to actions
        log['actions'].append(str(key))
        if key == 'escape':
            # finish
            log['end_time'] = time.time()
            # compute summary and save
            save_log_and_exit(log)
        if key == 'e':
            do_interact()
        if key == 'q':
            risky_action()
        if key == 'space':
            log['actions'].append('jump')
        if key == 'r':
            record_event('restart')
            log['actions'].append('restart')

    # placeholder "complete level" event bound to 'c' key
    def on_complete():
        record_event('complete', {'time': time.time() - log['start_time']})

    # bind 'c' to simulate completion
    from ursina import camera
    # little UI hint
    from ursina import Text
    Text("Controls: WASD move, Space jump, E interact, Q risky, R restart, C complete, ESC exit+save", origin=(0,0), position=(-0.7, 0.45), scale=1.2)

    def input_wrapper(key):
        input(key)
        if key == 'c':
            on_complete()

    # override ursina input
    from ursina import application
    application.input = input_wrapper

    def save_log_and_exit(logdict):
        logdict['end_time'] = logdict.get('end_time') or time.time()
        # compute some derived fields
        total_time = logdict['end_time'] - logdict['start_time']
        logdict['meta']['total_time'] = total_time
        # simple counts
        logdict['meta']['unique_positions'] = len(set(logdict['positions']))
        logdict['meta']['total_positions'] = len(logdict['positions'])
        logdict['meta']['unique_actions'] = len(set(logdict['actions']))
        fname = time.strftime("playerlog_%Y%m%d_%H%M%S.json")
        path = os.path.join(LOG_DIR, fname)
        with open(path, 'w') as f:
            json.dump(logdict, f, indent=2)
        print("Saved log to", path)
        sys.exit(0)

    app.run()

########################
# ---------- ANALYZE MODE (offline) ----
########################
def feature_vector_from_log(log):
    # create numeric feature vector for clustering / heuristics
    positions = log.get('positions', [])
    actions = log.get('actions', [])
    events = log.get('events', [])
    total_time = log.get('meta', {}).get('total_time', None) or (log.get('end_time', time.time()) - log.get('start_time', time.time()))
    unique_positions = len(set(positions))
    total_positions = max(1, len(positions))
    unique_actions = len(set(actions))
    total_actions = max(1, len(actions))
    risky_actions = actions.count('risky') + sum(1 for e in events if e['name']=='risky_action')
    jumps = actions.count('jump')
    restarts = sum(1 for e in events if e['name']=='restart') + actions.count('restart')
    out_of_bounds = sum(1 for e in events if e['name']=='out_of_bounds')
    completes = sum(1 for e in events if e['name']=='complete')
    interacts = actions.count('interact') + sum(1 for e in events if e['name']=='interact')
    editor_use = sum(1 for e in events if e['name']=='editor_use')
    # items collected field if exists
    items_collected = log.get('items_collected', 0)

    # normalized features (keep raw too)
    f = {
        'unique_positions': unique_positions,
        'total_positions': total_positions,
        'pos_ratio': unique_positions / total_positions,
        'unique_actions': unique_actions,
        'total_actions': total_actions,
        'risky_actions': risky_actions,
        'jumps': jumps,
        'restarts': restarts,
        'out_of_bounds': out_of_bounds,
        'completes': completes,
        'interacts': interacts,
        'editor_use': editor_use,
        'items_collected': items_collected,
        'total_time': total_time
    }

    # compact vector for clustering
    vec = [
        f['pos_ratio'],
        f['unique_actions'] / (1 + f['total_actions']),
        f['risky_actions'] / (1 + f['total_actions']),
        f['jumps'] / (1 + f['total_actions']),
        f['restarts'],
        f['out_of_bounds'],
        f['interacts'] / (1 + f['total_actions']),
        f['editor_use'],
        f['items_collected'],
        max(0.0, 1.0 - (f['total_time'] / MAX_EXPECTED_TIME))  # inverse time for speedrunner-like metric (normalized)
    ]
    return vec, f

def heuristic_persona_scores(fdict):
    """
    Compute heuristic scores (0..1) for each persona in the solo-adapted list.
    Returns dict of persona -> score (higher = stronger).
    Personas:
    - verifier (Baseline)
    - explorer
    - analyst (minimalist)
    - achiever
    - gambler (risk taker)
    - speedrunner
    - glitcher
    - immerser
    - self_competitor
    - artist
    - creator
    - strategist
    """
    scores = {}
    # helper safe norms
    pos_ratio = fdict['pos_ratio']    # exploration tendency
    unique_actions = fdict['unique_actions']
    total_actions = fdict['total_actions']
    risky = fdict['risky_actions']
    jumps = fdict['jumps']
    restarts = fdict['restarts']
    out_of_bounds = fdict['out_of_bounds']
    interacts = fdict['interacts']
    editor = fdict['editor_use']
    items = fdict['items_collected']
    total_time = fdict['total_time']

    # Verifier / Baseline: if they have completed at least once and not too many restarts -> high
    scores['verifier'] = 1.0 if fdict['completes'] > 0 and restarts < 3 else (0.6 if fdict['completes']>0 else 0.0)

    # Explorer: high pos_ratio and many unique positions
    scores['explorer'] = min(1.0, pos_ratio * 1.5)

    # Analyst / Minimalist: low unique_actions and low path length (prefer low total_actions)
    scores['analyst'] = 1.0 / (1.0 + math.log(1 + unique_actions)) if unique_actions>0 else 1.0

    # Achiever: items collected relative to a not-known total (we use absolute)
    scores['achiever'] = min(1.0, items / 5.0)  # assumes 5 optional items -> tune as needed

    # Gambler / RiskTaker: risky actions fraction and deaths/out_of_bounds
    scores['gambler'] = min(1.0, (risky + out_of_bounds) / (1 + total_actions) * 5.0)

    # Speedrunner: low total_time -> normalized inverse
    scores['speedrunner'] = max(0.0, 1.0 - (total_time / MAX_EXPECTED_TIME))

    # Glitcher / Exploiter: out_of_bounds and unusual event counts
    scores['glitcher'] = min(1.0, out_of_bounds / 2.0 + (restarts>5)*0.5)

    # Immerser: lots of interaction time (we only have counts) and long play time
    scores['immerser'] = min(1.0, (interacts / (1 + total_actions)) * 2.0 + min(1.0, total_time / 600.0))

    # Self-competitor: many restarts attempting to improve (restarts high) and completes multiple times
    scores['self_competitor'] = min(1.0, (restarts / 5.0) + (fdict['completes']>1)*0.3)

    # Artist / Performer: flashy actions like jumps + interactions per time
    scores['artist'] = min(1.0, (jumps / (1 + total_actions)) * 3.0 + (interacts>10)*0.2)

    # Creator: editor usage or many custom events
    scores['creator'] = min(1.0, editor / 2.0)

    # Strategist: many runs exporting logs or changing params (we approximate via restarts + editor)
    scores['strategist'] = min(1.0, (restarts / 5.0) + (editor>0)*0.3)

    return scores

def analyze_logs():
    # gather logs
    files = sorted(glob.glob(os.path.join(LOG_DIR, "playerlog_*.json")))
    if not files:
        print("No log files found in", LOG_DIR)
        return

    all_vecs = []
    meta_list = []
    score_list = []
    for fp in files:
        with open(fp,'r') as f:
            log = json.load(f)
        vec, fdict = feature_vector_from_log(log)
        scores = heuristic_persona_scores(fdict)
        all_vecs.append(vec)
        meta_list.append({'file':fp, 'f':fdict})
        score_list.append(scores)

    # try to cluster with sklearn if present
    try:
        import numpy as np
        from sklearn.cluster import KMeans
        X = np.array(all_vecs)
        k = min(KMEANS_CLUSTERS, max(2, len(X)//2))
        kmeans = KMeans(n_clusters=k, random_state=0).fit(X)
        labels = kmeans.labels_
        centroids = kmeans.cluster_centers_
        print("KMeans clusters (k={}):".format(k))
        for i in range(k):
            idxs = [j for j,lbl in enumerate(labels) if lbl==i]
            print(f" Cluster {i}: {len(idxs)} logs, files:")
            for j in idxs:
                print("   ", meta_list[j]['file'])
            print("  centroid:", centroids[i])
    except Exception as e:
        print("sklearn clustering not available or failed:", e)
        labels = [None]*len(all_vecs)

    # print heuristic persona summary per file
    for i, meta in enumerate(meta_list):
        print("\n---", meta['file'])
        for k,v in score_list[i].items():
            print(f"  {k:12s}: {v:.3f}")
        print("  derived features:", meta['f'])

    # detect 'rare/interesting' personas by heuristic thresholds
    print("\n=== Rare Persona Detections (heuristic thresholds) ===")
    for i, scores in enumerate(score_list):
        rare = []
        if scores['speedrunner'] > 0.8:
            rare.append('Speedrunner')
        if scores['glitcher'] > 0.5:
            rare.append('Glitcher')
        if scores['creator'] > 0.6:
            rare.append('Creator')
        if scores['strategist'] > 0.6:
            rare.append('Strategist')
        if scores['artist'] > 0.6:
            rare.append('Artist')
        if rare:
            print(meta_list[i]['file'], "->", rare)

    print("\nDone analysis. If you want CSV or plots, I can add simple matplotlib outputs.")

########################
# ---------- CLI ----
########################
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['run','analyze'], help='run game or analyze logs')
    args = parser.parse_args()
    if args.mode == 'run':
        run_game()
    elif args.mode == 'analyze':
        analyze_logs()

if __name__ == "__main__":
    main()
