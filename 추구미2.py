"""
persona_game_with_analysis_fixed.py

- Usage:
    python persona_game_with_analysis_fixed.py run
    python persona_game_with_analysis_fixed.py analyze

- This is a refined/fixed version of the previous script.
  Key fixes:
  - No 'import *' inside functions (imports at module level).
  - Safe log saving on ESC / Ctrl+C.
  - Tunable sampling rate and constants.
  - Optional clustering if scikit-learn available.
"""

import os
import sys
import json
import time as pytime
import math
import argparse
import glob
import signal
import traceback

# ------- Configurable constants -------
LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)
SAMPLE_INTERVAL = 0.1          # seconds (position sampling frequency)
MAX_EXPECTED_TIME = 3600.0     # for speedrunner normalization (tune to your level)
KMEANS_CLUSTERS = 4

# ------- Ursina imports (module-level) -------
# Avoid `import *` inside functions; import only what's needed at top-level.
try:
    from ursina import Ursina, Entity, Text, application, time as ursina_time, color
    from ursina.prefabs.first_person_controller import FirstPersonController
except Exception as e:
    # If Ursina not installed, we'll still allow 'analyze' mode to run.
    Ursina = None
    Entity = None
    Text = None
    application = None
    ursina_time = None
    FirstPersonController = None
    ursina_import_error = e
else:
    ursina_import_error = None

# --------------------------
# ---- RUN (game + logger)
# --------------------------
def run_game():
    if Ursina is None:
        print("Ursina is not importable in this environment. Error:", ursina_import_error)
        print("Install ursina (pip install ursina) and run again.")
        return

    # Create the Ursina app
    app = Ursina()

    # Simple world (same as your original small grid)
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

    # Player
    player = FirstPersonController()
    player.position = (3,0,3)
    player.cursor.visible = False
    player.gravity = 1
    player.speed = 10
    player.collider = 'box'

    # Logger state
    log = {
        'positions': [],
        'actions': [],
        'events': [],
        'items_collected': 0,
        'start_time': pytime.time(),
        'end_time': None,
        'meta': {'map': 'default_grid'}
    }

    sample_accum = 0.0

    # safe save function (idempotent)
    def save_log_to_disk(logdict):
        try:
            logdict['end_time'] = logdict.get('end_time') or pytime.time()
            total_time = logdict['end_time'] - logdict['start_time']
            logdict['meta']['total_time'] = total_time
            logdict['meta']['unique_positions'] = len(set(logdict['positions']))
            logdict['meta']['total_positions'] = len(logdict['positions'])
            logdict['meta']['unique_actions'] = len(set(logdict['actions']))
            fname = pytime.strftime("playerlog_%Y%m%d_%H%M%S.json")
            path = os.path.join(LOG_DIR, fname)
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(logdict, f, indent=2, ensure_ascii=False)
            print(f"[LOG SAVED] {path}")
        except Exception as e:
            print("[ERROR] Failed saving log:", e)
            traceback.print_exc()

    # event recorder helper
    def record_event(name, payload=None):
        t = pytime.time() - log['start_time']
        log['events'].append({'t': t, 'name': name, 'payload': payload or {}})

    # small demo interactions
    def do_interact():
        record_event('interact')
        log['actions'].append('interact')

    def risky_action():
        record_event('risky_action')
        log['actions'].append('risky')

    # update loop: sample position at SAMPLE_INTERVAL
    def update():
        nonlocal sample_accum
        dt = ursina_time.dt
        sample_accum += dt
        if sample_accum >= SAMPLE_INTERVAL:
            sample_accum = 0.0
            p = player.position
            # round to limit log size
            log['positions'].append( (round(p.x,4), round(p.y,4), round(p.z,4)) )
            # detect out of bounds
            if p.y < -5:
                record_event('out_of_bounds')

    # input handling: map keys to action tokens/events
    def input_handler(key):
        keystr = str(key)
        log['actions'].append(keystr)

        if key == 'escape':
            # Save and quit gracefully
            log['end_time'] = pytime.time()
            save_log_to_disk(log)
            application.quit()
        elif key == 'e':
            do_interact()
        elif key == 'q':
            risky_action()
        elif key == 'space':
            log['actions'].append('jump')
        elif key == 'r':
            record_event('restart')
            log['actions'].append('restart')
        elif key == 'c':
            record_event('complete', {'time': pytime.time() - log['start_time']})

    # minimal UI hint
    Text("Controls: WASD move, Space jump, E interact, Q risky, R restart, C complete, ESC exit+save",
         origin=(0,0), position=(-0.7, 0.45), scale=1.0)

    # attach handlers
    application.input = input_handler

    # handle Ctrl+C in console: save log before quitting
    def _signal_handler(sig, frame):
        print("\n[Signal] Interrupt received, saving log...")
        log['end_time'] = pytime.time()
        save_log_to_disk(log)
        try:
            application.quit()
        except Exception:
            pass
        sys.exit(0)

    signal.signal(signal.SIGINT, _signal_handler)

    # run ursina app (blocking)
    try:
        app.run()
    except SystemExit:
        # normal exit
        pass
    except Exception:
        # unexpected exception: save log and re-raise
        print("[ERROR] Exception in app.run(), saving log before exit.")
        log['end_time'] = pytime.time()
        save_log_to_disk(log)
        traceback.print_exc()
        raise

# --------------------------
# ---- ANALYZE (offline) ----
# --------------------------
def feature_vector_from_log(log):
    positions = log.get('positions', [])
    actions = log.get('actions', [])
    events = log.get('events', [])
    total_time = log.get('meta', {}).get('total_time') or (log.get('end_time', pytime.time()) - log.get('start_time', pytime.time()))
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
    items_collected = log.get('items_collected', 0)

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
        max(0.0, 1.0 - (f['total_time'] / MAX_EXPECTED_TIME))
    ]
    return vec, f

def heuristic_persona_scores(fdict):
    scores = {}
    pos_ratio = fdict['pos_ratio']
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

    scores['verifier'] = 1.0 if fdict['completes'] > 0 and restarts < 3 else (0.6 if fdict['completes']>0 else 0.0)
    scores['explorer'] = min(1.0, pos_ratio * 1.5)
    scores['analyst'] = 1.0 / (1.0 + math.log(1 + unique_actions)) if unique_actions>0 else 1.0
    scores['achiever'] = min(1.0, items / 5.0)
    scores['gambler'] = min(1.0, (risky + out_of_bounds) / (1 + total_actions) * 5.0)
    scores['speedrunner'] = max(0.0, 1.0 - (total_time / MAX_EXPECTED_TIME))
    scores['glitcher'] = min(1.0, out_of_bounds / 2.0 + (restarts>5)*0.5)
    scores['immerser'] = min(1.0, (interacts / (1 + total_actions)) * 2.0 + min(1.0, total_time / 600.0))
    scores['self_competitor'] = min(1.0, (restarts / 5.0) + (fdict['completes']>1)*0.3)
    scores['artist'] = min(1.0, (jumps / (1 + total_actions)) * 3.0 + (interacts>10)*0.2)
    scores['creator'] = min(1.0, editor / 2.0)
    scores['strategist'] = min(1.0, (restarts / 5.0) + (editor>0)*0.3)

    return scores

def analyze_logs():
    files = sorted(glob.glob(os.path.join(LOG_DIR, "playerlog_*.json")))
    if not files:
        print("No log files found in", LOG_DIR)
        return

    all_vecs = []
    meta_list = []
    score_list = []
    for fp in files:
        with open(fp,'r', encoding='utf-8') as f:
            log = json.load(f)
        vec, fdict = feature_vector_from_log(log)
        scores = heuristic_persona_scores(fdict)
        all_vecs.append(vec)
        meta_list.append({'file':fp, 'f':fdict})
        score_list.append(scores)

    # clustering if sklearn available
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
            print(f" Cluster {i}: {len(idxs)} logs")
            for j in idxs:
                print("   ", meta_list[j]['file'])
            print("  centroid:", centroids[i])
    except Exception as e:
        print("Clustering skipped (scikit-learn not available or failed):", e)
        labels = [None]*len(all_vecs)

    # print heuristic persona summary per file
    for i, meta in enumerate(meta_list):
        print("\n---", meta['file'])
        for k,v in score_list[i].items():
            print(f"  {k:12s}: {v:.3f}")
        print("  derived features:", meta['f'])

    # rare persona detection
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

    print("\nDone analysis.")

# --------------------------
# ---- CLI ----
# --------------------------
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
