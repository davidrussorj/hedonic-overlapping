"""
DBLP Full Graph Experiment (sem ground truth)
==============================================
Roda Leiden + Hedônico no grafo DBLP completo e compara:
  - número de comunidades
  - qualidade CPM (Q)
  - quantos nós ficam em múltiplas comunidades
  - equilíbrio de Nash

Não usa ground truth — avalia qualidade interna.

Uso:
    python3.12 scripts/dblp_full_experiment.py --resolution 0.1 --n_iterations 3
"""

import argparse
import json
import pickle
import time
from pathlib import Path

import igraph as ig
import numpy as np


def log(msg, t0=None):
    elapsed = f"  [{time.time() - t0:.1f}s]" if t0 else ""
    print(f"{msg}{elapsed}", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data_dir",      default="data/dblp")
    parser.add_argument("--resolution",    type=float, default=0.1)
    parser.add_argument("--n_iterations",  type=int,   default=3)
    parser.add_argument("--output",        default="results/dblp_full_experiment.json")
    args = parser.parse_args()

    log("=" * 55)
    log("  DBLP Full Graph Experiment")
    log("=" * 55)
    log(f"  resolução    : {args.resolution}")
    log(f"  n_iterations : {args.n_iterations}")
    log("=" * 55)

    # Carregar grafo
    t0 = time.time()
    log(f"[load] Carregando {args.data_dir}/dblp.pkl ...")
    g, _, _ = pickle.load(open(f"{args.data_dir}/dblp.pkl", "rb"))
    log(f"[load] {g.vcount():,} nós, {g.ecount():,} arestas", t0)

    from hedonic.overlapping import OverlappingGame
    og = OverlappingGame(g)
    results = {
        "graph": {"n": g.vcount(), "m": g.ecount()},
        "resolution": args.resolution,
        "n_iterations": args.n_iterations,
    }

    # ---- Leiden baseline ----
    log(f"\n[1/3] Leiden  γ={args.resolution} ...")
    t = time.time()
    part = og.community_leiden(resolution=args.resolution, n_iterations=-1)
    t_leiden = time.time() - t
    n_leiden = max(part.membership) + 1
    leiden_cover = [[v for v, c in enumerate(part.membership) if c == ci]
                    for ci in range(n_leiden)]
    log(f"[1/3] {n_leiden:,} comunidades em {t_leiden:.1f}s")

    log("[1/3] Calculando Q Leiden ...")
    t = time.time()
    q_leiden = og.quality_overlapping(leiden_cover, args.resolution)
    log(f"[1/3] Q={q_leiden:.6f}", t)

    results["leiden"] = {
        "n_communities": n_leiden,
        "quality": q_leiden,
        "time_s": t_leiden,
        "n_overlapping_nodes": 0,  # não-overlapping por definição
    }

    # ---- Hedônico overlapping ----
    log(f"\n[2/3] Hedônico overlapping  γ={args.resolution}  iter={args.n_iterations} ...")
    t = time.time()
    cover_obj = og.community_leiden_overlapping(
        resolution=args.resolution,
        n_iterations=args.n_iterations,
        initial_membership=[[c] for c in part.membership],
    )
    cover = list(cover_obj)
    t_hedonic = time.time() - t
    log(f"[2/3] {len(cover):,} comunidades em {t_hedonic:.1f}s")

    # Estatísticas de sobreposição
    membership_count = [0] * g.vcount()
    for comm in cover:
        for v in comm:
            membership_count[v] += 1
    n_in_multiple = sum(1 for c in membership_count if c > 1)
    n_isolated    = sum(1 for c in membership_count if c == 0)
    avg_memberships = np.mean([c for c in membership_count if c > 0])
    max_memberships = max(membership_count)

    log(f"[2/3] Nós em múltiplas comunidades: {n_in_multiple:,} ({100*n_in_multiple/g.vcount():.1f}%)")
    log(f"[2/3] Média de comunidades por nó: {avg_memberships:.3f}  max={max_memberships}")

    log("[2/3] Calculando Q Hedônico ...")
    t = time.time()
    q_hedonic = og.quality_overlapping(cover, args.resolution)
    log(f"[2/3] Q={q_hedonic:.6f}  ΔQ={q_hedonic - q_leiden:+.6f}", t)

    results["hedonic"] = {
        "n_communities": len(cover),
        "quality": q_hedonic,
        "time_s": t_hedonic,
        "n_overlapping_nodes": n_in_multiple,
        "pct_overlapping_nodes": round(100 * n_in_multiple / g.vcount(), 2),
        "avg_memberships_per_node": round(float(avg_memberships), 4),
        "max_memberships": int(max_memberships),
    }
    results["delta_quality"] = q_hedonic - q_leiden

    # ---- Equilíbrio de Nash ----
    log(f"\n[3/3] Verificando equilíbrio de Nash ...")
    t = time.time()
    is_eq = og.in_equilibrium_overlapping(cover, args.resolution)
    log(f"[3/3] {'✓ Em equilíbrio de Nash' if is_eq else '✗ Fora do equilíbrio'}  [{time.time()-t:.1f}s]")
    results["hedonic"]["in_equilibrium"] = is_eq

    # ---- Resumo ----
    log("\n" + "=" * 55)
    log(f"  Leiden  — {n_leiden:,} comunidades  Q={q_leiden:.6f}")
    log(f"  Hedonic — {len(cover):,} comunidades  Q={q_hedonic:.6f}")
    log(f"  ΔQ = {q_hedonic - q_leiden:+.6f}  {'✓' if q_hedonic >= q_leiden else '✗'}")
    log(f"  Nós overlapping: {n_in_multiple:,} ({100*n_in_multiple/g.vcount():.1f}%)")
    log(f"  Nash: {'✓ sim' if is_eq else '✗ não'}")
    log("=" * 55)

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(results, f, indent=2)
    log(f"\n[done] Resultados em {args.output}")


if __name__ == "__main__":
    main()
