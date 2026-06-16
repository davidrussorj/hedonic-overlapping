"""
DBLP Validation Experiment
===========================
Validates the overlapping vectorized hedonic game against DBLP ground truth.

Dataset: https://snap.stanford.edu/data/bigdata/communities/
  - com-dblp.ungraph.txt.gz   (edges)
  - com-dblp.cmty.txt.gz      (ground-truth communities, one per line)

Usage:
    python dblp_experiment.py --data_dir ./data/dblp --resolution 0.0001
    python dblp_experiment.py --data_dir ./data/dblp --resolution_sweep
"""

import argparse
import gzip
import json
import pickle
import sys
import time
from pathlib import Path

import igraph as ig
import numpy as np


# ---------------------------------------------------------------------------
# Logging helper — flush=True garante output imediato mesmo em background
# ---------------------------------------------------------------------------

def log(msg: str, t0: float = None):
    elapsed = f"  [{time.time() - t0:.1f}s]" if t0 else ""
    print(f"{msg}{elapsed}", flush=True)


# ---------------------------------------------------------------------------
# Data loading (com cache pickle para evitar recarregamento lento)
# ---------------------------------------------------------------------------

def load_dblp(data_dir: str):
    """Load DBLP graph and ground-truth communities.

    Na primeira execução lê os .gz e salva cache em dblp.pkl.
    Nas próximas carrega direto do cache (~3s vs ~8min).
    """
    data_dir   = Path(data_dir)
    cache_file = data_dir / "dblp.pkl"

    # --- cache hit ---
    if cache_file.exists():
        log(f"[load] Carregando cache {cache_file} …")
        t = time.time()
        g, gt, node_map = pickle.load(open(cache_file, "rb"))
        log(f"[load] Cache OK — {g.vcount():,} nós, {g.ecount():,} arestas, "
            f"{len(gt):,} comunidades ground truth", t)
        return g, gt, node_map

    # --- cache miss: ler .gz ---
    edge_file = data_dir / "com-dblp.ungraph.txt.gz"
    cmty_file = data_dir / "com-dblp.cmty.txt.gz"

    log("[load] Lendo arestas do .gz …")
    t_total = time.time()
    edges, node_set = [], set()
    with gzip.open(edge_file, "rt") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            u, v = map(int, line.split())
            edges.append((u, v))
            node_set.update([u, v])
    log(f"[load] {len(node_set):,} nós, {len(edges):,} arestas lidas", t_total)

    log("[load] Remapeando ids e construindo grafo igraph …")
    t = time.time()
    node_list = sorted(node_set)
    node_map  = {old: new for new, old in enumerate(node_list)}
    edges_r   = [(node_map[u], node_map[v]) for u, v in edges]
    g = ig.Graph(n=len(node_list), edges=edges_r, directed=False)
    log(f"[load] Grafo construído (sem simplify)", t)

    log("[load] Lendo comunidades ground truth …")
    t = time.time()
    gt = []
    with gzip.open(cmty_file, "rt") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            members = [node_map[int(x)] for x in line.split() if int(x) in node_map]
            if len(members) >= 2:
                gt.append(members)
    log(f"[load] {len(gt):,} comunidades ground truth carregadas", t)

    log("[load] Salvando cache …")
    t = time.time()
    pickle.dump((g, gt, node_map), open(cache_file, "wb"))
    log(f"[load] Cache salvo em {cache_file}", t)

    log(f"[load] Carregamento total completo", t_total)
    return g, gt, node_map


# ---------------------------------------------------------------------------
# Experimento principal
# ---------------------------------------------------------------------------

def run_experiment(g: ig.Graph, gt: list, resolution: float, n_iter: int):
    from hedonic.overlapping import OverlappingGame

    log(f"\n[exp] Criando OverlappingGame (n={g.vcount():,}, m={g.ecount():,}) …")
    t_total = time.time()
    og = OverlappingGame(g)
    n  = og.vcount()
    results = {}

    # ---- 1) Leiden não-overlapping (baseline) ----
    log(f"\n[1/3] Leiden não-overlapping  γ={resolution:.2e} …")
    t0 = time.time()
    leiden_part  = og.community_leiden(resolution=resolution, n_iterations=-1)
    t_leiden     = time.time() - t0
    leiden_cover = [[v for v, c in enumerate(leiden_part.membership) if c == ci]
                    for ci in range(max(leiden_part.membership) + 1)]
    log(f"[1/3] {len(leiden_cover):,} comunidades em {t_leiden:.1f}s")

    log("[1/3] Calculando métricas vs ground truth …")
    t = time.time()
    metrics_leiden = OverlappingGame.evaluate_cover(leiden_cover, gt, n)
    metrics_leiden["time_s"]       = t_leiden
    metrics_leiden["n_communities"] = len(leiden_cover)
    results["leiden_nonoverlapping"] = metrics_leiden
    log(f"[1/3] F1={metrics_leiden['f1']:.4f}  "
        f"Jaccard={metrics_leiden['jaccard']:.4f}  "
        f"Omega={metrics_leiden['omega']:.4f}", t)

    # ---- 2) Hedonic overlapping ----
    log(f"\n[2/3] Hedonic overlapping  γ={resolution:.2e}  n_iter={n_iter} …")
    t0 = time.time()
    hedonic_cover_obj = og.community_leiden_overlapping(
        resolution=resolution,
        n_iterations=n_iter,
        initial_membership=leiden_part.membership,
    )
    t_hedonic  = time.time() - t0
    cover_lists = list(hedonic_cover_obj)
    log(f"[2/3] {len(cover_lists):,} comunidades em {t_hedonic:.1f}s")

    log("[2/3] Calculando métricas vs ground truth …")
    t = time.time()
    metrics_hedonic = OverlappingGame.evaluate_cover(cover_lists, gt, n)
    metrics_hedonic["time_s"]       = t_hedonic
    metrics_hedonic["n_communities"] = len(cover_lists)
    results["hedonic_overlapping"] = metrics_hedonic
    log(f"[2/3] F1={metrics_hedonic['f1']:.4f}  "
        f"Jaccard={metrics_hedonic['jaccard']:.4f}  "
        f"Omega={metrics_hedonic['omega']:.4f}", t)

    # ---- 3) Nash equilibrium ----
    log("\n[3/3] Verificando equilíbrio de Nash …")
    t = time.time()
    is_eq = og.in_equilibrium_overlapping(cover_lists, resolution)
    results["hedonic_overlapping"]["in_equilibrium"] = is_eq
    log(f"[3/3] {'✓ Em equilíbrio de Nash' if is_eq else '✗ Fora do equilíbrio'}", t)

    # ---- Qualidade CPM ----
    log("\n[exp] Calculando qualidade CPM …")
    t = time.time()
    q_leiden  = og.quality_overlapping(leiden_cover, resolution)
    q_hedonic = og.quality_overlapping(cover_lists, resolution)
    results["leiden_nonoverlapping"]["quality"] = q_leiden
    results["hedonic_overlapping"]["quality"]   = q_hedonic
    log(f"[exp] Q não-overlapping : {q_leiden:.6f}", t)
    log(f"[exp] Q overlapping     : {q_hedonic:.6f}")
    log(f"[exp] ΔQ = {q_hedonic - q_leiden:+.6f}  "
        f"{'✓ melhorou' if q_hedonic >= q_leiden else '✗ piorou'}")
    log(f"\n[exp] Experimento completo", t_total)
    return results


# ---------------------------------------------------------------------------
# Varredura de resolução
# ---------------------------------------------------------------------------

def resolution_sweep(og, gt, resolutions, n_iter):
    from hedonic.overlapping import OverlappingGame

    n = og.vcount()
    sweep = []
    log(f"\n[sweep] {len(resolutions)} resoluções: "
        f"{resolutions[0]:.1e} → {resolutions[-1]:.1e}", flush=True)

    for i, res in enumerate(resolutions):
        log(f"\n[sweep {i+1}/{len(resolutions)}] γ={res:.5e} …")
        t0 = time.time()

        log(f"  Leiden não-overlapping …")
        t = time.time()
        part = og.community_leiden(resolution=res, n_iterations=-1)
        log(f"  {max(part.membership)+1:,} comunidades em {time.time()-t:.1f}s")

        log(f"  Hedonic overlapping …")
        t = time.time()
        cover_obj = og.community_leiden_overlapping(
            resolution=res,
            n_iterations=n_iter,
            initial_membership=part.membership,
        )
        cover = list(cover_obj)
        log(f"  {len(cover):,} comunidades em {time.time()-t:.1f}s")

        log(f"  Calculando métricas …")
        t = time.time()
        metrics = OverlappingGame.evaluate_cover(cover, gt, n)
        metrics["resolution"] = res
        metrics["quality"]    = og.quality_overlapping(cover, res)
        sweep.append(metrics)
        log(f"  F1={metrics['f1']:.4f}  Omega={metrics['omega']:.4f}  "
            f"Q={metrics['quality']:.6f}  total={time.time()-t0:.1f}s", t)

    return sweep


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="DBLP overlapping community experiment")
    parser.add_argument("--data_dir",        default="./data/dblp")
    parser.add_argument("--resolution",      type=float, default=1e-4)
    parser.add_argument("--n_iterations",    type=int,   default=-1)
    parser.add_argument("--resolution_sweep", action="store_true")
    parser.add_argument("--output",          default="results.json")
    args = parser.parse_args()

    log("=" * 55)
    log("  DBLP Overlapping Hedonic Game Experiment")
    log("=" * 55)
    log(f"  data_dir   : {args.data_dir}")
    log(f"  output     : {args.output}")
    log(f"  sweep      : {args.resolution_sweep}")
    log(f"  resolution : {args.resolution:.2e}")
    log("=" * 55)

    t_start = time.time()
    g, gt, _ = load_dblp(args.data_dir)

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)

    if args.resolution_sweep:
        from hedonic.overlapping import OverlappingGame
        og = OverlappingGame(g)
        resolutions = np.logspace(-5, -2, 10)
        sweep = resolution_sweep(og, gt, resolutions, args.n_iterations)
        with open(args.output, "w") as f:
            json.dump({"resolution_sweep": sweep}, f, indent=2)
    else:
        results = run_experiment(g, gt, args.resolution, args.n_iterations)
        with open(args.output, "w") as f:
            json.dump(results, f, indent=2)

    log(f"\n[done] Resultados salvos em {args.output}")
    log(f"[done] Tempo total", t_start)


if __name__ == "__main__":
    main()
