"""
Bench Omega
===========
Diagnóstico de custo do índice Omega (O(n²) por comunidade) sobre um cache
de coberturas gerado por `subgraph_experiment.py --covers_cache`.

Ao contrário de `score_covers.py --omega` (que só loga a cada 100
comunidades), este script imprime o tempo de CADA comunidade x método
imediatamente, para localizar exatamente onde o cálculo trava/fica lento.

Uso:
    python3.12 scripts/bench_omega.py results/subgraph_L1_n200_fixed_covers.pkl
    python3.12 scripts/bench_omega.py results/subgraph_L1_n200_fixed_covers.pkl \
        --sort desc --limit 20 --timeout 5
"""

import argparse
import pickle
import time

from hedonic.overlapping import OverlappingGame

METHODS = ["leiden", "hedonic_v1", "hedonic_v2", "singleton", "grand_coalition", "total_overlap"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("covers_cache", help="Pickle gerado por subgraph_experiment.py")
    parser.add_argument("--sort", choices=["asc", "desc", "none"], default="desc",
                         help="Ordena por subgraph_nodes. 'desc' testa os piores casos primeiro.")
    parser.add_argument("--limit", type=int, default=None,
                         help="Testa só as N primeiras comunidades (após ordenar)")
    parser.add_argument("--timeout", type=float, default=10.0,
                         help="Avisa (não interrompe) se uma comunidade/método passar disso, em segundos")
    args = parser.parse_args()

    with open(args.covers_cache, "rb") as f:
        records = pickle.load(f)
    print(f"[load] {len(records):,} comunidades em cache", flush=True)

    if args.sort != "none":
        records = sorted(records, key=lambda r: r["subgraph_nodes"],
                          reverse=(args.sort == "desc"))
    if args.limit:
        records = records[:args.limit]

    for i, rec in enumerate(records):
        n_sub = rec["subgraph_nodes"]
        gt_target = rec["ground_truth"]
        idx = rec.get("community_idx")
        print(f"\n[{i+1}/{len(records)}] comunidade {idx}  n_sub={n_sub:,}", flush=True)

        for name in METHODS:
            cover = rec["covers"].get(name)
            if cover is None:
                continue
            n_comms = len(cover)
            t0 = time.time()
            omega = OverlappingGame._omega_index(cover, gt_target, n_sub)
            dt = time.time() - t0
            flag = "  <-- LENTO" if dt > args.timeout else ""
            print(f"    {name:16s}  {n_comms:5,} comunidades  omega={omega:.4f}  [{dt:.2f}s]{flag}",
                  flush=True)


if __name__ == "__main__":
    main()
