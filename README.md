# Overlapping Community Detection via Vectorized Hedonic Game

Extension of the CPM-based Leiden algorithm to detect **overlapping** communities
using a game-theoretic decomposition.  Each vertex independently decides whether to
join or leave each community; the delta in individual utility equals the delta in
global quality (CPM), preserving the theoretical guarantees of the hedonic game framework.

---

## Theoretical Background

### Non-overlapping baseline (existing work)

The Constant Potts Model (CPM) quality of a partition is:

```
Q = (1/2m) · Σ_c [ e_c − γ · N_c² ]
```

where `e_c` = internal edge weight, `N_c` = weighted community size, `γ` = resolution.

The hedonic decomposition shows that the gain from moving vertex `v` from its
current community to community `c` equals the change in `Q`:

```
ΔQ = Δhedonic_value(v)
```

### Vectorized hedonic game (this work)

For overlapping communities each vertex `v` holds a **vector** of memberships.
The overlapping CPM quality is:

```
Q = (1/2m) · Σ_c [ e_c − γ · C(N_c, 2) ]
```

where an edge contributes to `e_c` if **both** its endpoints are in `c`.

For each `(v, c)` pair independently:

| Condition | Formula | Decision |
|-----------|---------|----------|
| `v ∉ c`   | `ΔQ = deg(v,c) − γ · N_c` | join if `> 0` |
| `v ∈ c`   | `ΔQ = −(deg(v,c) − γ · (N_c−1))` | leave if `> 0` |

where `deg(v,c)` = sum of edge weights from `v` to other members of `c`.

**Key property:** gains are independent across communities, so all join/leave
decisions for a single vertex can be computed from one neighbor-scan and applied
atomically — convergence is guaranteed because every move strictly increases `Q`.

A cover is a **Nash equilibrium** of the vectorized hedonic game iff no vertex
wants to join or leave any community.

---

## Repository Structure

```
hedonic-overlapping/
│
├── c_patch/
│   └── leiden_overlapping.c        # New C functions to append to leiden.c
│                                   # (3 functions, 492 lines)
│
├── python_patch/
│   └── community_overlapping.py    # Python wrapper + graphobject.c guide
│
├── hedonic_ext/
│   └── overlapping_game.py         # OverlappingGame class (495 lines)
│
├── scripts/
│   ├── test_small.py               # Quick validation on toy graphs
│   └── dblp_experiment.py          # Full DBLP experiment (200 lines)
│
└── README.md
```

---

## Setup

### Prerequisites

- Python ≥ 3.10
- `lucas-igraph` — fork of igraph with extra Leiden parameters
  (`only_local_moving`, `allow_isolation`)
- `hedonic` — hedonic game library (lucaslopes fork)

### Installation

```bash
# 1. Install lucas-igraph (the fork, not the standard igraph)
pip install lucas-igraph

# 2. Install hedonic library
pip install git+https://github.com/lucaslopes/hedonic.git

# 3. Re-pin lucas-igraph (hedonic's setup.py pulls in standard igraph)
pip install lucas-igraph --force-reinstall

# 4. Install OverlappingGame into the hedonic package
cp hedonic_ext/overlapping_game.py \
   $(python -c "import hedonic; import os; print(os.path.dirname(hedonic.__file__))")/overlapping.py
```

Verify:

```bash
python -c "
import igraph; print('igraph:', igraph.__version__)   # must be 0.11.9.x
from hedonic.overlapping import OverlappingGame
print('OverlappingGame: OK')
"
```

Expected output:
```
igraph: 0.11.9.3
OverlappingGame: OK
```

---

## Quick Start

```python
import random
import igraph as ig
ig.set_random_number_generator(random.Random(42))  # reproducible

from hedonic.overlapping import OverlappingGame

g = ig.Graph.Famous("Petersen")
og = OverlappingGame(g)

# Detect overlapping communities
cover = og.community_leiden_overlapping(
    resolution=og.density(),   # γ = edge density of the graph
    n_iterations=-1,           # iterate until convergence
)

cover_lists = list(cover)      # [[v, v, ...], [v, v, ...], ...]
print(f"Communities: {len(cover_lists)}")
for i, members in enumerate(cover_lists):
    print(f"  c{i}: {sorted(members)}")

# Global quality
q = og.quality_overlapping(cover_lists, resolution=og.density())
print(f"Q = {q:.6f}")

# Nash equilibrium check
eq = og.in_equilibrium_overlapping(cover_lists, resolution=og.density())
print(f"Nash equilibrium: {eq}")

# Comparison with non-overlapping baseline
p_base = og.community_leiden(resolution=og.density(), n_iterations=-1)
cover_no = [[v for v, c in enumerate(p_base.membership) if c == ci]
            for ci in range(max(p_base.membership) + 1)]
q_no = og.quality_overlapping(cover_no, resolution=og.density())
print(f"Q non-overlapping: {q_no:.6f}")
print(f"ΔQ = {q - q_no:+.6f}")
```

Output (Petersen graph, seed=42):
```
Communities: 5
  c0: [0, 1, 4]
  c1: [0, 1, 2]
  c2: [3, 5, 8]
  c3: [5, 7, 8]
  c4: [6, 8, 9]
Q = 0.166667
Nash equilibrium: True
Q non-overlapping: 0.111111
ΔQ = +0.055556  ✓
```

---

## Running the Tests

```bash
cd hedonic-overlapping
python3.12 scripts/test_small.py
```

The test script runs three experiments:

| Test | Graph | What it checks |
|------|-------|---------------|
| 1 | Petersen (n=10) | Overlapping cover + Nash equilibrium |
| 2 | SBM synthetic (n=20, 2 blocks) | F1 / Jaccard / Omega vs. ground truth |
| 3 | Petersen | `Q_overlapping > Q_non_overlapping` |

---

## DBLP Experiment

### Download data

```bash
mkdir -p data/dblp && cd data/dblp
wget https://snap.stanford.edu/data/com-dblp.ungraph.txt.gz
wget https://snap.stanford.edu/data/com-dblp.cmty.txt.gz
```

Dataset stats: 317,080 nodes · 1,049,866 edges · 13,477 ground-truth communities.
Source: [SNAP — DBLP](https://snap.stanford.edu/data/com-DBLP.html)

### Single run

```bash
python3.12 scripts/dblp_experiment.py \
    --data_dir data/dblp \
    --resolution 1e-4 \
    --output results/dblp_1e-4.json
```

### Resolution sweep (recommended first)

```bash
python3.12 scripts/dblp_experiment.py \
    --data_dir data/dblp \
    --resolution_sweep \
    --output results/sweep.json
```

Sweeps `γ ∈ [1e-5, 1e-2]` (10 log-spaced values) and reports F1, Jaccard,
Omega and Q for each.

### Output metrics

| Metric | Description |
|--------|-------------|
| `f1` | Macro-average best-match F1 between predicted cover and ground truth |
| `jaccard` | Macro-average best-match Jaccard index |
| `omega` | Collins–Dent omega index (pairwise multi-membership agreement) |
| `quality` | Overlapping CPM quality Q |
| `n_predicted_comms` | Number of non-empty communities found |
| `in_equilibrium` | Whether the cover is a Nash equilibrium |

---

## OverlappingGame API

```python
from hedonic.overlapping import OverlappingGame

og = OverlappingGame(igraph_graph)
```

### Community detection

```python
cover = og.community_leiden_overlapping(
    resolution=0.0001,          # γ — higher → smaller, denser communities
    n_iterations=-1,            # -1 = until convergence; positive = fixed count
    initial_membership=None,    # list[int] — starting partition; None = run Leiden first
    weights=None,               # list[float] or edge attribute name
)
# returns igraph.VertexCover
cover_lists = list(cover)       # convert to list of lists
```

### Quality

```python
q = og.quality_overlapping(
    cover=cover_lists,          # list of lists of vertex ids
    resolution=0.0001,
    weights=None,
)
# returns float
```

### Nash equilibrium

```python
is_eq = og.in_equilibrium_overlapping(
    cover=cover_lists,
    resolution=0.0001,
)
# returns bool
```

### Evaluation vs. ground truth

```python
metrics = OverlappingGame.evaluate_cover(
    predicted=cover_lists,
    ground_truth=gt_cover,      # list of lists
    n_vertices=g.vcount(),
)
# returns dict: {'f1', 'jaccard', 'omega', 'n_predicted_comms', 'n_gt_comms'}
```

### Individual hedonic value

```python
h = og.hedonic_value_overlapping(
    v=5,                        # vertex id
    c_members={0, 1, 2, 5},    # current members of community c
    c_idx=2,                    # community index (for membership lookup)
    resolution=0.0001,
)
# positive → v wants to stay / join; negative → v wants to leave / not join
```

---

## Implementation Roadmap

The pure-Python implementation in `OverlappingGame` is fully functional and
sufficient for experiments.  The C extension speeds up large graphs significantly.

### Phase 1 — Pure Python ✅ (done)

`hedonic_ext/overlapping_game.py` — `OverlappingGame._community_leiden_overlapping_python()`

Validates the algorithm logic on toy graphs without any C compilation.

### Phase 2 — C library

**Repository:** `lucaslopes/igraph` · **Branch:** `lucas`

Append `c_patch/leiden_overlapping.c` to `src/community/leiden.c` and add the
public declaration to `include/igraph_community.h`:

```c
IGRAPH_EXPORT igraph_error_t igraph_community_leiden_overlapping(
    const igraph_t *graph,
    const igraph_vector_t *edge_weights,      /* NULL → all 1.0 */
    const igraph_vector_t *node_weights,      /* NULL → all 1.0 */
    igraph_real_t resolution_parameter,
    igraph_integer_t n_iterations,            /* < 0 → until convergence */
    const igraph_vector_int_list_t *initial_cover, /* NULL → singleton */
    igraph_vector_int_list_t *cover,          /* OUTPUT */
    igraph_real_t *quality);                  /* OUTPUT, NULL → skip */
```

**Three functions added:**

| Function | Lines | Role |
|----------|-------|------|
| `igraph_i_community_leiden_overlapping_quality` | 70 | Computes overlapping CPM Q |
| `igraph_i_community_leiden_overlapping_fastmove` | 230 | Queue-based local-move phase |
| `igraph_community_leiden_overlapping` | 130 | Public API, manages data structures |

**Key data structures:**

```c
comm_vertices : igraph_vector_int_list_t   // community → [vertex, ...]
vertex_comms  : igraph_vector_int_list_t   // vertex    → [community, ...]
comm_weight   : igraph_vector_t            // N_c for each community
```

**Build:**

```bash
cd /path/to/lucaslopes/igraph
mkdir build && cd build
cmake .. -DIGRAPH_WARNINGS_AS_ERRORS=OFF
make -j$(nproc)
```

### Phase 3 — Python wrapper (graphobject.c)

**Repository:** `lucaslopes/python-igraph`

Follow the pattern of `igraphmodule_Graph_community_leiden()` in
`src/_igraph/graphobject.c`.  Key differences:

- **Input:** `initial_cover` as Python `list[list[int]]`
  → convert with `igraphmodule_PyObject_to_vector_int_list_t()`
- **Output:** `cover` as `igraph_vector_int_list_t`
  → convert back to Python `list[list[int]]`
  → wrap as `VertexCover` in `community.py`

The Python-level wrapper is in `python_patch/community_overlapping.py`.

### Phase 4 — DBLP validation

```bash
python3.12 scripts/dblp_experiment.py --data_dir data/dblp --resolution_sweep
```

---

## Design Decisions

**Why no refinement/aggregation phase?**
The refinement (phase 2) and aggregation (phase 3) of the original Leiden
algorithm build a hierarchical quotient graph, which assumes a non-overlapping
partition at each level. Extending these phases to overlapping memberships
requires a different formulation (e.g., weighted bipartite aggregation) and is
left as future work. The local-move phase alone is sufficient to prove the
hedonic decomposition and validate against DBLP.

**Why start from the non-overlapping Leiden result?**
Starting from a good non-overlapping partition and "opening" it to overlapping
is faster and produces better results than starting from singletons, because
the initial communities already have good internal density. The overlapping
phase then refines vertices on the boundaries.

**Why are gains independent across communities?**
`deg(v, c)` (edge weight from `v` to members of `c`) does not change when `v`
joins or leaves a *different* community `c'`. Therefore all join/leave decisions
for vertex `v` can be computed from a single neighbor-scan, and the moves are
applied without re-evaluation.

---

## Related Repositories

| Repository | Description |
|------------|-------------|
| [lucaslopes/igraph](https://github.com/lucaslopes/igraph/tree/lucas) | C library fork with `only_local_moving` and `allow_isolation` |
| [lucaslopes/python-igraph](https://github.com/lucaslopes/python-igraph) | Python wrapper fork (`lucas-igraph` on PyPI) |
| [lucaslopes/hedonic](https://github.com/lucaslopes/hedonic) | Hedonic game library (installs `lucas-igraph`) |

---

## References

- Traag, V. A., Waltman, L., & van Eck, N. J. (2019). From Louvain to Leiden:
  guaranteeing well-connected communities. *Scientific Reports*, 9(1), 5233.

- Traag, V. A., Van Dooren, P., & Nesterov, Y. (2011). Narrow scope for
  resolution-limit-free community detection. *Physical Review E*, 84, 016114.

- Yang, J., & Leskovec, J. (2012). Defining and Evaluating Network Communities
  based on Ground-truth. *ICDM*.
  Dataset: https://snap.stanford.edu/data/com-DBLP.html

- Collins, L. M., & Dent, C. W. (1988). Omega: A general formulation of the
  Rand Index of cluster recovery suitable for non-disjoint solutions.
  *Multivariate Behavioral Research*, 23(2), 231–242.
