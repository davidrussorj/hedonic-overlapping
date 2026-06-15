"""
DBLP Validation Experiment
===========================
Validates the overlapping vectorized hedonic game against DBLP ground truth.

Dataset: https://snap.stanford.edu/data/com-DBLP.html
  - com-dblp.ungraph.txt.gz   (edges)
  - com-dblp.cmty.txt.gz      (ground-truth communities, one per line)

Usage:
    python dblp_experiment.py --data_dir ./data/dblp --resolution 0.0001
"""

import argparse
import gzip
import os
import time
import json
from pathlib import Path

import igraph as ig
import numpy as np


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_dblp(data_dir: str):
    """Load DBLP graph and ground-truth communities from SNAP files."""
    data_dir = Path(data_dir)
    edge_file = data_dir / "com-dblp.ungraph.txt.gz"
    cmty_file = data_dir / "com-dblp.cmty.txt.gz"

    print("Loading edges …")
    edges = []
    node_set = set()
    opener = gzip.open if str(edge_file).endswith(".gz") else open
    with opener(edge_file, "rt") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            u, v = map(int, line.split())
            edges.append((u, v))
            node_set.update([u, v])

    # Remap node ids to 0-based integers
    node_list = sorted(node_set)
    node_map  = {old: new for new, old in enumerate(node_list)}
    edges_remapped = [(node_map[u], node_map[v]) for u, v in edges]

    print(f"  {len(node_list):,} nodes, {len(edges):,} edges")
    g = ig.Graph(n=len(node_list), edges=edges_remapped, directed=False)
    g.simplify()  # remove multi-edges and self-loops

    print("Loading ground-truth communities …")
    gt = []
    opener = gzip.open if str(cmty_file).endswith(".gz") else open
    with opener(cmty_file, "rt") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            members = [node_map[int(x)] for x in line.split()
                       if int(x) in node_map]
            if len(members) >= 2:
                gt.append(members)
    print(f"  {len(gt):,} ground-truth communities")
    return g, gt, node_map


# ---------------------------------------------------------------------------
# Experiment
# ---------------------------------------------------------------------------

def run_experiment(g: ig.Graph, gt: list, resolution: float, n_iter: int):
    from hedonic.overlapping import OverlappingGame

    og = OverlappingGame(g)
    n = og.vcount()

    results = {}

    # ---- Baseline: standard non-overlapping Leiden ----
    print("\n[1/3] Running non-overlapping Leiden …")
    t0 = time.time()
    leiden_part = og.community_leiden(resolution=resolution, n_iterations=-1)
    t_leiden = time.time() - t0
    leiden_cover = [[v for v, c in enumerate(leiden_part.membership) if c == ci]
                    for ci in range(max(leiden_part.membership) + 1)]

    metrics_leiden = OverlappingGame.evaluate_cover(leiden_cover, gt, n)
    metrics_leiden["time_s"] = t_leiden
    metrics_leiden["n_communities"] = max(leiden_part.membership) + 1
    results["leiden_nonoverlapping"] = metrics_leiden
    print(f"  Done in {t_leiden:.1f}s. {metrics_leiden['n_predicted_comms']} communities. "
          f"F1={metrics_leiden['f1']:.4f}, Omega={metrics_leiden['omega']:.4f}")

    # ---- Vectorized hedonic game (overlapping Leiden) ----
    print("\n[2/3] Running overlapping hedonic Leiden …")
    t0 = time.time()
    hedonic_cover = og.community_leiden_overlapping(
        resolution=resolution,
        n_iterations=n_iter,
        initial_membership=leiden_part.membership,
    )
    t_hedonic = time.time() - t0

    cover_lists = hedonic_cover.membership_list  # list of lists
    metrics_hedonic = OverlappingGame.evaluate_cover(cover_lists, gt, n)
    metrics_hedonic["time_s"] = t_hedonic
    metrics_hedonic["n_communities"] = len(cover_lists)
    results["hedonic_overlapping"] = metrics_hedonic
    print(f"  Done in {t_hedonic:.1f}s. {metrics_hedonic['n_predicted_comms']} communities. "
          f"F1={metrics_hedonic['f1']:.4f}, Omega={metrics_hedonic['omega']:.4f}")

    # ---- Equilibrium check ----
    print("\n[3/3] Checking Nash equilibrium …")
    is_eq = og.in_equilibrium_overlapping(cover_lists, resolution)
    results["hedonic_overlapping"]["in_equilibrium"] = is_eq
    print(f"  Cover is {'in' if is_eq else 'NOT in'} Nash equilibrium.")

    # ---- Quality scores ----
    q_leiden = og.quality_overlapping(leiden_cover, resolution)
    q_hedonic = og.quality_overlapping(cover_lists, resolution)
    results["leiden_nonoverlapping"]["quality"] = q_leiden
    results["hedonic_overlapping"]["quality"] = q_hedonic
    print(f"\n  Quality — Leiden (non-overlapping): {q_leiden:.6f}")
    print(f"  Quality — Hedonic (overlapping):    {q_hedonic:.6f}")
    print(f"  ΔQ = {q_hedonic - q_leiden:+.6f}")

    return results


# ---------------------------------------------------------------------------
# Resolution sweep (to understand sensitivity)
# ---------------------------------------------------------------------------

def resolution_sweep(og, gt, resolutions, n_iter):
    from hedonic.overlapping import OverlappingGame

    n = og.vcount()
    sweep = []
    for res in resolutions:
        part = og.community_leiden(resolution=res, n_iterations=-1)
        cover_obj = og.community_leiden_overlapping(
            resolution=res,
            n_iterations=n_iter,
            initial_membership=part.membership,
        )
        cover = cover_obj.membership_list
        metrics = OverlappingGame.evaluate_cover(cover, gt, n)
        metrics["resolution"] = res
        metrics["quality"] = og.quality_overlapping(cover, res)
        sweep.append(metrics)
        print(f"  γ={res:.5f}  comms={len(cover):4d}  "
              f"F1={metrics['f1']:.4f}  Omega={metrics['omega']:.4f}  "
              f"Q={metrics['quality']:.6f}")
    return sweep


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="DBLP overlapping community experiment")
    parser.add_argument("--data_dir", default="./data/dblp",
                        help="Directory with com-dblp.ungraph.txt.gz and com-dblp.cmty.txt.gz")
    parser.add_argument("--resolution", type=float, default=1e-4,
                        help="CPM resolution γ (default: 1e-4)")
    parser.add_argument("--n_iterations", type=int, default=-1,
                        help="Overlapping iterations (-1 = until convergence)")
    parser.add_argument("--resolution_sweep", action="store_true",
                        help="Run a sweep of resolution values")
    parser.add_argument("--output", default="results.json",
                        help="Output JSON file for results")
    args = parser.parse_args()

    g, gt, _ = load_dblp(args.data_dir)

    if args.resolution_sweep:
        from hedonic.overlapping import OverlappingGame
        og = OverlappingGame(g)
        resolutions = np.logspace(-5, -2, 10)
        print("\nResolution sweep:")
        sweep = resolution_sweep(og, gt, resolutions, args.n_iterations)
        with open(args.output, "w") as f:
            json.dump({"resolution_sweep": sweep}, f, indent=2)
        print(f"\nResults saved to {args.output}")
    else:
        results = run_experiment(g, gt, args.resolution, args.n_iterations)
        with open(args.output, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\nResults saved to {args.output}")


if __name__ == "__main__":
    main()
