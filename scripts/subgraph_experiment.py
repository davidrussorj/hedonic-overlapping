"""
Subgraph Experiment
===================
Extrai sub-redes ao redor de comunidades ground truth do DBLP e
roda o algoritmo hedônico overlapping em cada uma.

Cada sub-rede é construída pegando os nós de uma comunidade GT
e expandindo L níveis de vizinhos.

Uso:
    python subgraph_experiment.py --data_dir data/dblp --levels 1 --n_communities 20
    python subgraph_experiment.py --data_dir data/dblp --levels 2 --community_idx 0
"""

import argparse
import json
import pickle
import time
from pathlib import Path
from collections import deque

import igraph as ig
import numpy as np


def log(msg, t0=None):
    elapsed = f"  [{time.time() - t0:.1f}s]" if t0 else ""
    print(f"{msg}{elapsed}", flush=True)


# ---------------------------------------------------------------------------
# Extração de sub-rede
# ---------------------------------------------------------------------------

def extract_subgraph(g, seed_nodes, levels):
    """Extrai sub-rede com `levels` níveis de vizinhos ao redor de seed_nodes.

    Retorna (subgrafo, node_map_old2new, node_map_new2old).
    """
    nodes = set(seed_nodes)
    frontier = set(seed_nodes)

    for _ in range(levels):
        new_frontier = set()
        for v in frontier:
            for u in g.neighbors(v):
                if u not in nodes:
                    new_frontier.add(u)
        nodes.update(new_frontier)
        frontier = new_frontier

    nodes_sorted = sorted(nodes)
    old2new = {old: new for new, old in enumerate(nodes_sorted)}
    subg = g.induced_subgraph(nodes_sorted)
    return subg, old2new, nodes_sorted


# ---------------------------------------------------------------------------
# Métricas (sem Omega — O(n²))
# ---------------------------------------------------------------------------

def evaluate(predicted, ground_truth):
    pred_sets = [set(c) for c in predicted if c]
    gt_sets   = [set(c) for c in ground_truth if c]

    def best_f1(A, B):
        total = 0.0
        for a in A:
            best = 0.0
            for b in B:
                inter = len(a & b)
                if not inter:
                    continue
                p = inter / len(a)
                r = inter / len(b)
                f = 2 * p * r / (p + r)
                if f > best:
                    best = f
            total += best
        return total / len(A) if A else 0.0

    def best_jaccard(A, B):
        total = 0.0
        for a in A:
            best = 0.0
            for b in B:
                inter = len(a & b)
                union = len(a | b)
                j = inter / union if union else 0.0
                if j > best:
                    best = j
            total += best
        return total / len(A) if A else 0.0

    return {
        "f1":      (best_f1(pred_sets, gt_sets)      + best_f1(gt_sets, pred_sets))      / 2,
        "jaccard": (best_jaccard(pred_sets, gt_sets)  + best_jaccard(gt_sets, pred_sets)) / 2,
        "n_pred":  len(pred_sets),
        "n_gt":    len(gt_sets),
    }


# ---------------------------------------------------------------------------
# Experimento numa única comunidade
# ---------------------------------------------------------------------------

def run_one(g_full, gt_community, all_gt, levels, resolution, n_iterations, comm_idx):
    from hedonic.overlapping import OverlappingGame

    # Extrair sub-rede
    t0 = time.time()
    subg, old2new, new2old = extract_subgraph(g_full, gt_community, levels)
    n_sub = subg.vcount()
    m_sub = subg.ecount()
    log(f"  sub-rede: {n_sub:,} nós, {m_sub:,} arestas  [{time.time()-t0:.1f}s]")

    if n_sub < 3 or m_sub == 0:
        log("  sub-rede muito pequena, pulando.")
        return None

    # Remapear GT da comunidade alvo para ids da sub-rede
    gt_sub = [[old2new[v] for v in gt_community if v in old2new]]

    # Remapear todas as GT que caem dentro da sub-rede (para métricas completas)
    node_set = set(new2old)
    all_gt_sub = []
    for comm in all_gt:
        members = [old2new[v] for v in comm if v in old2new]
        if len(members) >= 2:
            all_gt_sub.append(members)

    og = OverlappingGame(subg)

    # Leiden não-overlapping (baseline)
    t = time.time()
    part = og.community_leiden(resolution=resolution, n_iterations=-1)
    n_leiden = max(part.membership) + 1
    leiden_cover = [[v for v, c in enumerate(part.membership) if c == ci]
                    for ci in range(n_leiden)]
    t_leiden = time.time() - t
    metrics_leiden = evaluate(leiden_cover, gt_sub)
    log(f"  Leiden:   {n_leiden:,} comunidades  F1={metrics_leiden['f1']:.4f}  "
        f"Jaccard={metrics_leiden['jaccard']:.4f}  [{t_leiden:.1f}s]")

    # Hedonic overlapping
    t = time.time()
    cover_obj = og.community_leiden_overlapping(
        resolution=resolution,
        n_iterations=n_iterations,
        initial_membership=part.membership,
    )
    cover = list(cover_obj)
    t_hedonic = time.time() - t
    metrics_hedonic = evaluate(cover, gt_sub)
    log(f"  Hedonic:  {len(cover):,} comunidades  F1={metrics_hedonic['f1']:.4f}  "
        f"Jaccard={metrics_hedonic['jaccard']:.4f}  [{t_hedonic:.1f}s]")

    delta_f1 = metrics_hedonic["f1"] - metrics_leiden["f1"]
    log(f"  ΔF1 = {delta_f1:+.4f}  {'✓ melhorou' if delta_f1 >= 0 else '✗ piorou'}")

    return {
        "community_idx":  comm_idx,
        "gt_size":        len(gt_community),
        "subgraph_nodes": n_sub,
        "subgraph_edges": m_sub,
        "levels":         levels,
        "resolution":     resolution,
        "leiden":         {**metrics_leiden, "n_communities": n_leiden, "time_s": t_leiden},
        "hedonic":        {**metrics_hedonic, "n_communities": len(cover), "time_s": t_hedonic},
        "delta_f1":       delta_f1,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data_dir",       default="./data/dblp")
    parser.add_argument("--levels",         type=int,   default=1)
    parser.add_argument("--resolution",     type=float, default=0.1)
    parser.add_argument("--n_iterations",   type=int,   default=5)
    parser.add_argument("--n_communities",  type=int,   default=20,
                        help="Número de comunidades GT a testar (amostradas aleatoriamente)")
    parser.add_argument("--community_idx",  type=int,   default=None,
                        help="Índice específico de comunidade GT (substitui --n_communities)")
    parser.add_argument("--output",         default="results/subgraph_experiment.json")
    args = parser.parse_args()

    log("=" * 55)
    log("  DBLP Subgraph Experiment")
    log("=" * 55)
    log(f"  levels        : {args.levels}")
    log(f"  resolution    : {args.resolution:.2e}")
    log(f"  n_iterations  : {args.n_iterations}")
    log("=" * 55)

    # Carregar dados
    cache = Path(args.data_dir) / "dblp.pkl"
    log(f"[load] {cache} …")
    t0 = time.time()
    g, gt, node_map = pickle.load(open(cache, "rb"))
    log(f"[load] {g.vcount():,} nós, {g.ecount():,} arestas, {len(gt):,} GT", t0)

    # Selecionar comunidades a testar
    if args.community_idx is not None:
        indices = [args.community_idx]
    else:
        # Filtrar comunidades com tamanho razoável (5–200 nós)
        candidates = [i for i, c in enumerate(gt) if 5 <= len(c) <= 200]
        rng = np.random.default_rng(42)
        indices = rng.choice(candidates, size=min(args.n_communities, len(candidates)),
                             replace=False).tolist()

    log(f"\n[exp] {len(indices)} comunidades  levels={args.levels}  γ={args.resolution:.2e}\n")

    results = []
    for rank, idx in enumerate(indices):
        gt_comm = gt[idx]
        log(f"[{rank+1}/{len(indices)}] comunidade {idx}  ({len(gt_comm)} nós GT)")
        t_comm = time.time()
        result = run_one(g, gt_comm, gt, args.levels, args.resolution,
                         args.n_iterations, idx)
        if result:
            results.append(result)
        log(f"  total: {time.time()-t_comm:.1f}s\n")

    # Resumo
    if results:
        avg_f1_leiden  = np.mean([r["leiden"]["f1"]  for r in results])
        avg_f1_hedonic = np.mean([r["hedonic"]["f1"] for r in results])
        avg_delta      = np.mean([r["delta_f1"]      for r in results])
        n_improved     = sum(1 for r in results if r["delta_f1"] >= 0)
        log("=" * 55)
        log(f"  Leiden  F1 médio : {avg_f1_leiden:.4f}")
        log(f"  Hedonic F1 médio : {avg_f1_hedonic:.4f}")
        log(f"  ΔF1 médio        : {avg_delta:+.4f}")
        log(f"  Melhorou em      : {n_improved}/{len(results)} comunidades")
        log("=" * 55)

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(results, f, indent=2)
    log(f"\n[done] Resultados em {args.output}")


if __name__ == "__main__":
    main()
