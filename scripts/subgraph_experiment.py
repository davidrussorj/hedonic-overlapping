"""
Subgraph Experiment
===================
Extrai sub-redes ao redor de comunidades ground truth do DBLP e roda,
para cada uma: Leiden (baseline), Hedônico v1 (binário, atual),
Hedônico v2 (intensidade fracionária 1/√k, porta de c_patch/leiden.c) e
três coberturas de referência determinísticas — Singleton, Grand Coalition
e Total Overlap — que servem de "sanity bounds" (granularidade máxima,
granularidade mínima e redundância máxima).

Cada sub-rede é construída pegando os nós de uma comunidade GT
e expandindo L níveis de vizinhos.

Além do JSON de métricas (compatível com o formato anterior), salva um
cache pickle com as coberturas brutas (ids locais da sub-rede) para que
`scripts/score_covers.py` possa recalcular métricas — inclusive o Omega,
que aqui fica desligado por padrão por ser O(n²) — sem rodar os algoritmos
de novo.

Uso:
    python subgraph_experiment.py --data_dir data/dblp --levels 1 --n_communities 20
    python subgraph_experiment.py --data_dir data/dblp --levels 2 --community_idx 0
"""

import argparse
import json
import pickle
import time
from pathlib import Path

import igraph as ig
import numpy as np

ALL_METHODS = ["leiden", "hedonic_v1", "hedonic_v2", "singleton", "grand_coalition", "total_overlap"]
METHODS = list(ALL_METHODS)  # pode ser filtrado via --methods em main()


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
# Geração das coberturas (Leiden, Hedônico v1/v2, baselines)
# ---------------------------------------------------------------------------

def build_covers(subg, n_gt_in_subgraph, resolution, n_iterations, max_memberships):
    """Gera as 6 coberturas de referência para uma sub-rede.

    Retorna (covers: dict[str, list[list[int]]], timings: dict[str, float],
    resolution: float). Se `resolution` vier None, usa a densidade da própria
    sub-rede e retorna o valor efetivamente usado (para registro no resultado).
    Todas as coberturas usam ids locais da sub-rede (0..n_sub-1).
    """
    from hedonic.overlapping import OverlappingGame

    n_sub = subg.vcount()
    og = OverlappingGame(subg)
    covers, timings = {}, {}

    if resolution is None:
        resolution = og.density()

    # Leiden é sempre calculado (hedonic_v1 depende dele para initial_membership),
    # mas só entra no resultado se pedido em METHODS.
    t = time.time()
    part = og.community_leiden(resolution=resolution, n_iterations=-1)
    t_leiden = time.time() - t
    if "leiden" in METHODS:
        n_leiden = max(part.membership) + 1
        covers["leiden"] = [[v for v, c in enumerate(part.membership) if c == ci]
                             for ci in range(n_leiden)]
        timings["leiden"] = t_leiden

    if "hedonic_v1" in METHODS:
        t = time.time()
        cover_obj = og.community_leiden_overlapping(
            resolution=resolution,
            n_iterations=n_iterations,
            initial_membership=[[c] for c in part.membership],
        )
        covers["hedonic_v1"] = list(cover_obj)
        timings["hedonic_v1"] = time.time() - t

    if "hedonic_v2" in METHODS:
        t = time.time()
        cover_obj_v2 = og.community_leiden_overlapping_v2(
            resolution=resolution,
            max_memberships=max_memberships,
            n_iterations=n_iterations,
            verbose=False,
        )
        covers["hedonic_v2"] = list(cover_obj_v2)
        timings["hedonic_v2"] = time.time() - t

    if "singleton" in METHODS:
        covers["singleton"] = OverlappingGame.singleton_cover(n_sub)
    if "grand_coalition" in METHODS:
        covers["grand_coalition"] = OverlappingGame.grand_coalition_cover(n_sub)
    if "total_overlap" in METHODS:
        covers["total_overlap"] = OverlappingGame.total_overlap_cover(n_sub, max(1, n_gt_in_subgraph))

    return covers, timings, resolution


def score_covers(covers, gt_target, n_sub, compute_omega=False):
    """Avalia cada cobertura contra o ground truth local. Sem rodar nada de novo."""
    from hedonic.overlapping import OverlappingGame

    return {
        name: OverlappingGame.evaluate_cover(cover, gt_target, n_sub, compute_omega=compute_omega)
        for name, cover in covers.items()
    }


# ---------------------------------------------------------------------------
# Experimento numa única comunidade
# ---------------------------------------------------------------------------

def run_one(g_full, gt_community, all_gt, levels, resolution, n_iterations, max_memberships, comm_idx):
    # Extrair sub-rede
    t0 = time.time()
    subg, old2new, new2old = extract_subgraph(g_full, gt_community, levels)
    n_sub = subg.vcount()
    m_sub = subg.ecount()
    log(f"  sub-rede: {n_sub:,} nós, {m_sub:,} arestas  [{time.time()-t0:.1f}s]")

    if n_sub < 3 or m_sub == 0:
        log("  sub-rede muito pequena, pulando.")
        return None, None

    # Remapear GT da comunidade alvo para ids da sub-rede
    gt_target = [[old2new[v] for v in gt_community if v in old2new]]

    # Todas as GT que caem dentro da sub-rede (usado só para dimensionar Total Overlap)
    node_set = set(new2old)
    n_gt_in_subgraph = sum(
        1 for comm in all_gt
        if len([v for v in comm if v in node_set]) >= 2
    )

    covers, timings, resolution = build_covers(subg, n_gt_in_subgraph, resolution, n_iterations, max_memberships)
    metrics = score_covers(covers, gt_target, n_sub, compute_omega=False)

    for name in METHODS:
        m = metrics[name]
        log(f"  {name:16s}  {len(covers[name]):5,} comunidades  F1={m['f1']:.4f}  "
            f"P={m['precision']:.4f}  R={m['recall']:.4f}  [{timings.get(name, 0.0):.1f}s]")

    has_delta1 = "leiden" in METHODS and "hedonic_v1" in METHODS
    has_delta2 = "leiden" in METHODS and "hedonic_v2" in METHODS
    delta_f1 = metrics["hedonic_v1"]["f1"] - metrics["leiden"]["f1"] if has_delta1 else None
    delta_f1_v2 = metrics["hedonic_v2"]["f1"] - metrics["leiden"]["f1"] if has_delta2 else None
    msg1 = f"ΔF1 (v1-Leiden) = {delta_f1:+.4f}" if has_delta1 else "ΔF1 (v1-Leiden) = n/a"
    msg2 = f"ΔF1 (v2-Leiden) = {delta_f1_v2:+.4f}" if has_delta2 else "ΔF1 (v2-Leiden) = n/a"
    log(f"  {msg1}   {msg2}")

    result = {
        "community_idx":  comm_idx,
        "gt_size":        len(gt_community),
        "subgraph_nodes": n_sub,
        "subgraph_edges": m_sub,
        "levels":         levels,
        "resolution":     resolution,
        "n_gt_in_subgraph": n_gt_in_subgraph,
        **{name: {**metrics[name], "n_communities": len(covers[name]), "time_s": timings.get(name, 0.0)}
           for name in METHODS},
        "delta_f1":       delta_f1,
        "delta_f1_v2":    delta_f1_v2,
    }
    cover_record = {
        "community_idx":    comm_idx,
        "gt_size":          len(gt_community),
        "subgraph_nodes":   n_sub,
        "subgraph_edges":   m_sub,
        "levels":           levels,
        "resolution":       resolution,
        "n_gt_in_subgraph": n_gt_in_subgraph,
        "covers":           covers,
        "ground_truth":     gt_target,
    }
    return result, cover_record


# ---------------------------------------------------------------------------
# Seleção de comunidades com sobreposição real no ground truth
# ---------------------------------------------------------------------------

def find_overlapping_communities(gt, min_overlap=2, min_overlap_ratio=0.0, min_size=5, max_size=200):
    """Retorna lista de (idx, {parceiro: n_nodes_compartilhados}) para comunidades
    que compartilham >= min_overlap nós com pelo menos uma outra comunidade GT.

    min_overlap_ratio: overlap coefficient mínimo por par = interseção / min(|i|, |j|).
    Garante interseção significativa independente do tamanho das comunidades.
    """

    # índice invertido: vértice → lista de comunidades
    vertex_to_comms = {}
    for i, comm in enumerate(gt):
        for v in comm:
            if v not in vertex_to_comms:
                vertex_to_comms[v] = []
            vertex_to_comms[v].append(i)

    gt_sizes = [len(c) for c in gt]

    result = []
    for i, comm in enumerate(gt):
        if not (min_size <= len(comm) <= max_size):
            continue
        partners = {}
        for v in comm:
            for j in vertex_to_comms.get(v, []):
                if j != i:
                    partners[j] = partners.get(j, 0) + 1
        valid = {
            j: cnt for j, cnt in partners.items()
            if cnt >= min_overlap
            and cnt / min(len(comm), gt_sizes[j]) >= min_overlap_ratio
        }
        if valid:
            result.append((i, valid))

    return result


def run_one_overlapping(g_full, gt, comm_idx, partners, levels, resolution, n_iterations, max_memberships):
    """Experimento para uma comunidade com sobreposição real.

    A sub-rede inclui os nós da comunidade alvo + todos os parceiros overlapping + L-hop.
    """
    # Seed = apenas a comunidade alvo; os parceiros são captados pela expansão L-hop
    seed_nodes = set(gt[comm_idx])

    t0 = time.time()
    subg, old2new, new2old = extract_subgraph(g_full, seed_nodes, levels)
    n_sub = subg.vcount()
    m_sub = subg.ecount()
    log(f"  sub-rede: {n_sub:,} nós, {m_sub:,} arestas  "
        f"(seed={len(seed_nodes)}, {len(partners)} parceiros, {levels}-hop)  [{time.time()-t0:.1f}s]")

    if n_sub < 3 or m_sub == 0:
        log("  sub-rede muito pequena, pulando.")
        return None, None

    node_set = set(new2old)
    n_gt_in_subgraph = sum(
        1 for comm in gt
        if len([v for v in comm if v in node_set]) >= 2
    )

    # GT apenas da comunidade alvo (métrica focada, igual ao run_one)
    gt_target = [[old2new[v] for v in gt[comm_idx] if v in old2new]]

    covers, timings, resolution = build_covers(subg, n_gt_in_subgraph, resolution, n_iterations, max_memberships)
    metrics = score_covers(covers, gt_target, n_sub, compute_omega=False)

    for name in METHODS:
        m = metrics[name]
        log(f"  {name:16s}  {len(covers[name]):5,} comunidades  F1={m['f1']:.4f}  [{timings.get(name, 0.0):.1f}s]")

    has_delta1 = "leiden" in METHODS and "hedonic_v1" in METHODS
    has_delta2 = "leiden" in METHODS and "hedonic_v2" in METHODS
    delta_f1 = metrics["hedonic_v1"]["f1"] - metrics["leiden"]["f1"] if has_delta1 else None
    delta_f1_v2 = metrics["hedonic_v2"]["f1"] - metrics["leiden"]["f1"] if has_delta2 else None
    shared = sum(partners.values())
    msg1 = f"ΔF1(v1)={delta_f1:+.4f}" if has_delta1 else "ΔF1(v1)=n/a"
    msg2 = f"ΔF1(v2)={delta_f1_v2:+.4f}" if has_delta2 else "ΔF1(v2)=n/a"
    log(f"  {msg1}  {msg2}  parceiros={len(partners)}  nós_compartilhados={shared}")

    result = {
        "community_idx":    comm_idx,
        "gt_size":          len(gt[comm_idx]),
        "n_partners":       len(partners),
        "shared_nodes":     shared,
        "subgraph_nodes":   n_sub,
        "subgraph_edges":   m_sub,
        "levels":           levels,
        "resolution":       resolution,
        "n_gt_in_subgraph": n_gt_in_subgraph,
        **{name: {**metrics[name], "n_communities": len(covers[name]), "time_s": timings.get(name, 0.0)}
           for name in METHODS},
        "delta_f1":         delta_f1,
        "delta_f1_v2":      delta_f1_v2,
    }
    cover_record = {
        "community_idx":    comm_idx,
        "gt_size":          len(gt[comm_idx]),
        "n_partners":       len(partners),
        "shared_nodes":     shared,
        "subgraph_nodes":   n_sub,
        "subgraph_edges":   m_sub,
        "levels":           levels,
        "resolution":       resolution,
        "n_gt_in_subgraph": n_gt_in_subgraph,
        "covers":           covers,
        "ground_truth":     gt_target,
    }
    return result, cover_record


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data_dir",       default="./data/dblp")
    parser.add_argument("--levels",         type=int,   default=1)
    parser.add_argument("--resolution",     type=float, default=0.1)
    parser.add_argument("--density_resolution", action="store_true",
                        help="Ignora --resolution e usa a densidade de cada sub-rede como γ")
    parser.add_argument("--n_iterations",   type=int,   default=5)
    parser.add_argument("--max_memberships", type=int,  default=4,
                        help="K máximo de comunidades por vértice no Hedônico v2")
    parser.add_argument("--methods",        default=",".join(ALL_METHODS),
                        help="Subconjunto separado por vírgula de: " + ",".join(ALL_METHODS))
    parser.add_argument("--n_communities",  type=int,   default=20,
                        help="Número de comunidades GT a testar")
    parser.add_argument("--community_idx",  type=int,   default=None,
                        help="Índice específico de comunidade GT")
    parser.add_argument("--overlapping_only", action="store_true",
                        help="Selecionar apenas comunidades com sobreposição real no GT")
    parser.add_argument("--min_overlap",    type=int,   default=2,
                        help="Mínimo de nós compartilhados para considerar sobreposição")
    parser.add_argument("--min_overlap_ratio", type=float, default=0.0,
                        help="Overlap coefficient mínimo por par: interseção/min(|i|,|j|). "
                             "Ex: 0.2 exige que pelo menos 20%% da menor comunidade seja compartilhada")
    parser.add_argument("--output",         default="results/subgraph_experiment.json")
    parser.add_argument("--covers_cache",   default=None,
                        help="Caminho do cache pickle com as coberturas brutas "
                             "(default: mesmo nome do --output, sufixo _covers.pkl)")
    args = parser.parse_args()
    resolution = None if args.density_resolution else args.resolution

    selected = [m.strip() for m in args.methods.split(",") if m.strip()]
    invalid = [m for m in selected if m not in ALL_METHODS]
    if invalid:
        parser.error(f"--methods inválido(s): {invalid}. Opções: {ALL_METHODS}")
    METHODS[:] = selected

    log("=" * 55)
    log("  DBLP Subgraph Experiment")
    log("=" * 55)
    log(f"  levels        : {args.levels}")
    log(f"  resolution    : {'densidade de cada sub-rede' if resolution is None else f'{resolution:.2e}'}")
    log(f"  n_iterations  : {args.n_iterations}")
    log(f"  max_memberships (v2): {args.max_memberships}")
    log(f"  methods       : {METHODS}")
    log("=" * 55)

    # Carregar dados
    cache = Path(args.data_dir) / "dblp.pkl"
    log(f"[load] {cache} …")
    t0 = time.time()
    g, gt, node_map = pickle.load(open(cache, "rb"))
    log(f"[load] {g.vcount():,} nós, {g.ecount():,} arestas, {len(gt):,} GT", t0)

    # Selecionar comunidades a testar (modo padrão)
    if not args.overlapping_only:
        if args.community_idx is not None:
            indices = [args.community_idx]
        else:
            candidates = [i for i, c in enumerate(gt) if 5 <= len(c) <= 200]
            rng = np.random.default_rng(42)
            indices = rng.choice(candidates, size=min(args.n_communities, len(candidates)),
                                 replace=False).tolist()

    results = []
    covers_cache = []

    if args.overlapping_only:
        log(f"\n[select] Buscando comunidades com sobreposição real (min_overlap={args.min_overlap}) …")
        t_sel = time.time()
        overlapping_list = find_overlapping_communities(
            gt, min_overlap=args.min_overlap, min_overlap_ratio=args.min_overlap_ratio,
            min_size=5, max_size=200
        )
        log(f"[select] {len(overlapping_list):,} comunidades com sobreposição encontradas  [{time.time()-t_sel:.1f}s]")
        rng = np.random.default_rng(42)
        chosen = rng.choice(len(overlapping_list),
                            size=min(args.n_communities, len(overlapping_list)),
                            replace=False)
        overlapping_sample = [overlapping_list[i] for i in chosen]
        log(f"[select] Amostradas {len(overlapping_sample)} comunidades\n")

        for rank, (idx, partners) in enumerate(overlapping_sample):
            log(f"[{rank+1}/{len(overlapping_sample)}] comunidade {idx}  "
                f"({len(gt[idx])} nós GT, {len(partners)} parceiros)")
            t_comm = time.time()
            result, cover_record = run_one_overlapping(
                g, gt, idx, partners, args.levels, resolution,
                args.n_iterations, args.max_memberships,
            )
            if result:
                results.append(result)
                covers_cache.append(cover_record)
            log(f"  total: {time.time()-t_comm:.1f}s\n")
    else:
        gamma_log = 'densidade de cada sub-rede' if resolution is None else f'{resolution:.2e}'
        log(f"\n[exp] {len(indices)} comunidades  levels={args.levels}  γ={gamma_log}\n")

        for rank, idx in enumerate(indices):
            gt_comm = gt[idx]
            log(f"[{rank+1}/{len(indices)}] comunidade {idx}  ({len(gt_comm)} nós GT)")
            t_comm = time.time()
            result, cover_record = run_one(
                g, gt_comm, gt, args.levels, resolution,
                args.n_iterations, args.max_memberships, idx,
            )
            if result:
                results.append(result)
                covers_cache.append(cover_record)
            log(f"  total: {time.time()-t_comm:.1f}s\n")

    # Resumo
    if results:
        log("=" * 55)
        for name in METHODS:
            f1s = [r[name]["f1"] for r in results]
            log(f"  {name:16s}  F1 médio = {np.mean(f1s):.4f}")
        if "leiden" in METHODS and "hedonic_v1" in METHODS:
            n_improved_v1 = sum(1 for r in results if r["delta_f1"] >= 0)
            log(f"  ΔF1 médio (v1-Leiden) : {np.mean([r['delta_f1'] for r in results]):+.4f}"
                f"   melhorou em {n_improved_v1}/{len(results)}")
        if "leiden" in METHODS and "hedonic_v2" in METHODS:
            n_improved_v2 = sum(1 for r in results if r["delta_f1_v2"] >= 0)
            log(f"  ΔF1 médio (v2-Leiden) : {np.mean([r['delta_f1_v2'] for r in results]):+.4f}"
                f"   melhorou em {n_improved_v2}/{len(results)}")
        log("=" * 55)

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(results, f, indent=2)
    log(f"\n[done] Resultados em {args.output}")

    covers_cache_path = args.covers_cache or str(Path(args.output).with_name(
        Path(args.output).stem + "_covers.pkl"))
    Path(covers_cache_path).parent.mkdir(parents=True, exist_ok=True)
    with open(covers_cache_path, "wb") as f:
        pickle.dump(covers_cache, f)
    log(f"[done] Cache de coberturas em {covers_cache_path}")


if __name__ == "__main__":
    main()
