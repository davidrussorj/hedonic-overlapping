"""
Score Covers
============
Recalcula métricas de acurácia a partir de um cache pickle de coberturas
gerado por `subgraph_experiment.py` (--covers_cache), sem rodar Leiden,
Hedônico v1/v2 ou as coberturas de referência de novo.

Isso permite testar métricas novas ou mais caras (ex: Omega, O(n²)) sobre
os mesmos resultados já computados.

Uso:
    python3.12 scripts/score_covers.py results/subgraph_L1_n200_covers.pkl
    python3.12 scripts/score_covers.py results/subgraph_L1_n200_covers.pkl --omega \
        --output results/subgraph_L1_n200_with_omega.json
"""

import argparse
import json
import pickle
import time
from pathlib import Path

import numpy as np

METHODS = ["leiden", "hedonic_v1", "hedonic_v2", "singleton", "grand_coalition", "total_overlap"]

METADATA_KEYS = [
    "community_idx", "gt_size", "n_partners", "shared_nodes",
    "subgraph_nodes", "subgraph_edges", "levels", "resolution",
    "n_gt_in_subgraph",
]


def log(msg, t0=None):
    elapsed = f"  [{time.time() - t0:.1f}s]" if t0 else ""
    print(f"{msg}{elapsed}", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("covers_cache", help="Pickle gerado por subgraph_experiment.py")
    parser.add_argument("--output", default=None,
                        help="Default: mesmo nome do cache, com extensão .json")
    parser.add_argument("--omega", action="store_true",
                        help="Também computa o índice Omega (O(n²) por comunidade — mais lento)")
    args = parser.parse_args()

    from hedonic.overlapping import OverlappingGame

    log(f"[load] {args.covers_cache} …")
    t0 = time.time()
    with open(args.covers_cache, "rb") as f:
        records = pickle.load(f)
    log(f"[load] {len(records):,} comunidades em cache", t0)

    results = []
    t0 = time.time()
    for i, rec in enumerate(records):
        n_sub = rec["subgraph_nodes"]
        gt_target = rec["ground_truth"]
        entry = {k: rec[k] for k in METADATA_KEYS if k in rec}
        for name in METHODS:
            cover = rec["covers"].get(name)
            if cover is None:
                continue
            metrics = OverlappingGame.evaluate_cover(
                cover, gt_target, n_sub, compute_omega=args.omega
            )
            metrics["n_communities"] = len(cover)
            entry[name] = metrics
        results.append(entry)
        if (i + 1) % 100 == 0:
            log(f"  {i + 1}/{len(records)} pontuadas  [{time.time() - t0:.1f}s]")

    log(f"[score] {len(results):,} comunidades pontuadas  [{time.time() - t0:.1f}s total]")

    log("=" * 55)
    for name in METHODS:
        f1s = [r[name]["f1"] for r in results if name in r]
        if not f1s:
            continue
        line = f"  {name:16s}  F1 médio = {np.mean(f1s):.4f}  (n={len(f1s)})"
        if args.omega:
            omegas = [r[name]["omega"] for r in results if name in r and r[name]["omega"] is not None]
            if omegas:
                line += f"   Omega médio = {np.mean(omegas):.4f}"
        log(line)
    log("=" * 55)

    output = args.output or str(Path(args.covers_cache).with_suffix(".json"))
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w") as f:
        json.dump(results, f, indent=2)
    log(f"[done] {output}")


if __name__ == "__main__":
    main()
