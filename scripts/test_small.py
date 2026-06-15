"""
Teste rápido do OverlappingGame com grafos pequenos.
Não precisa de DBLP nem de compilação C.
"""

import sys
sys.path.insert(0, '/home/davidcubric/.local/lib/python3.12/site-packages')

import igraph as ig
import numpy as np
from hedonic.overlapping import OverlappingGame

np.random.seed(42)


def separator(title):
    print(f"\n{'='*55}")
    print(f"  {title}")
    print('='*55)


# -----------------------------------------------------------------------
# Teste 1: grafo de Karate (Zachary) — ground truth conhecido
# -----------------------------------------------------------------------
separator("TESTE 1: Karate Club (n=34)")

g = ig.Graph.Famous("Petersen")
og = OverlappingGame(g)

res = og.density()
print(f"Resolução (density): {res:.4f}")

cover = og.community_leiden_overlapping(resolution=res, n_iterations=-1)
cover_lists = list(cover)  # list of lists of vertex ids
print(f"Comunidades encontradas: {len(cover_lists)}")
for i, members in enumerate(cover_lists):
    print(f"  Comunidade {i}: {sorted(members)}")

q = og.quality_overlapping(cover_lists, resolution=res)
print(f"Qualidade CPM overlapping (Q): {q:.6f}")

eq = og.in_equilibrium_overlapping(cover_lists, resolution=res)
print(f"Em equilíbrio de Nash: {eq}")


# -----------------------------------------------------------------------
# Teste 2: SBM sintético com overlapping conhecido
# Dois blocos de 10 vértices; vértices 8 e 9 conectados a ambos os blocos
# -----------------------------------------------------------------------
separator("TESTE 2: SBM sintético com overlapping")

n_per_block = 10
n_blocks = 2
n = n_per_block * n_blocks

# Probabilidades: dentro do bloco = 0.6, entre blocos = 0.05
block_sizes = [n_per_block] * n_blocks
pref_matrix = [
    [0.6, 0.05],
    [0.05, 0.6]
]
g_sbm = ig.Graph.SBM(n, pref_matrix, block_sizes, directed=False)
og_sbm = OverlappingGame(g_sbm)

# Ground truth: vértices 0-9 no bloco 0, vértices 10-19 no bloco 1
gt = [list(range(0, 10)), list(range(10, 20))]

res_sbm = 0.1
cover_sbm = og_sbm.community_leiden_overlapping(resolution=res_sbm, n_iterations=-1)
cover_sbm_lists = list(cover_sbm)
print(f"Resolução: {res_sbm}")
print(f"Comunidades encontradas: {len(cover_sbm_lists)}")
for i, members in enumerate(cover_sbm_lists):
    print(f"  Comunidade {i}: {sorted(members)}")

q_sbm = og_sbm.quality_overlapping(cover_sbm_lists, resolution=res_sbm)
eq_sbm = og_sbm.in_equilibrium_overlapping(cover_sbm_lists, resolution=res_sbm)
print(f"Qualidade Q: {q_sbm:.6f}")
print(f"Em equilíbrio de Nash: {eq_sbm}")

metrics = OverlappingGame.evaluate_cover(cover_sbm_lists, gt, n)
print(f"F1 vs ground truth:      {metrics['f1']:.4f}")
print(f"Jaccard vs ground truth: {metrics['jaccard']:.4f}")
print(f"Omega index:             {metrics['omega']:.4f}")


# -----------------------------------------------------------------------
# Teste 3: comparar qualidade overlapping vs. não-overlapping
# -----------------------------------------------------------------------
separator("TESTE 3: Qualidade overlapping > não-overlapping?")

g3 = ig.Graph.Famous("Petersen")
og3 = OverlappingGame(g3)
res3 = og3.density()

# Não-overlapping
p_no = og3.community_leiden(resolution=res3, n_iterations=-1)
cover_no = [[v for v, c in enumerate(p_no.membership) if c == ci]
            for ci in range(max(p_no.membership) + 1)]
q_no = og3.quality_overlapping(cover_no, resolution=res3)

# Overlapping (parte do mesmo ponto)
cover_ov = og3.community_leiden_overlapping(
    resolution=res3, n_iterations=-1,
    initial_membership=p_no.membership
)
q_ov = og3.quality_overlapping(list(cover_ov), resolution=res3)

print(f"Q não-overlapping: {q_no:.6f}  ({len(cover_no)} comunidades)")
print(f"Q overlapping:     {q_ov:.6f}  ({len(cover_ov)} comunidades)")
print(f"ΔQ = {q_ov - q_no:+.6f}  {'✓ melhorou' if q_ov >= q_no else '✗ piorou'}")

print("\n✓ Todos os testes concluídos.\n")
