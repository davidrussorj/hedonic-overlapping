# CLAUDE.md — Overlapping Hedonic Game

## What this project is

Extension of the CPM-based Leiden algorithm to detect **overlapping** communities
via a vectorized hedonic game. The key theoretical contribution is showing that
the overlapping CPM quality function decomposes into per-vertex, per-community
utility functions, so a Nash equilibrium of the vectorized game corresponds to a
local maximum of Q.

This is joint work between the repository owner (implementor) and Sadoc (theory).

## Repository layout

```
hedonic-overlapping/
├── CLAUDE.md                             ← this file
├── README.md                             ← user-facing docs (432 lines, verified)
├── c_patch/leiden_overlapping.c          ← C code to append to leiden.c (492 lines)
├── python_patch/community_overlapping.py ← Python wrapper + graphobject.c guide
├── hedonic_ext/overlapping_game.py       ← OverlappingGame class (495 lines, source of truth)
└── scripts/
    ├── test_small.py                     ← toy-graph validation (runs now, no DBLP needed)
    └── dblp_experiment.py                ← DBLP validation script (200 lines)
```

## Three upstream forks (all by lucaslopes)

| Fork | Repo | Purpose |
|------|------|---------|
| igraph C | `lucaslopes/igraph` branch `lucas` | adds `allow_isolation`, `only_local_moving` to Leiden |
| python-igraph | `lucaslopes/python-igraph` branch `lucas` | exposes the above params; published as `lucas-igraph` on PyPI |
| hedonic lib | `lucaslopes/hedonic` | `hedonic.Game` class, experiment scripts |

The files in **this repo** are patches to be merged into those forks.

## Current environment (as of last session)

```
Python  : 3.12.10  (/usr/local/bin/python3.12)
igraph  : 0.11.9.3  (lucas-igraph fork — MUST stay pinned, see pitfalls)
numpy   : 2.3.2
hedonic : 0.0.1  (lucaslopes/hedonic)
OverlappingGame : installed at
  ~/.local/lib/python3.12/site-packages/hedonic/overlapping.py
```

## What is done ✅

### 1. Pure-Python overlapping Leiden (`hedonic_ext/overlapping_game.py`)

Class `OverlappingGame(Game)` with:

- `community_leiden_overlapping(resolution, n_iterations, initial_membership, weights)`
  — public entry point; tries C extension, falls back to Python
- `_community_leiden_overlapping_python(...)` — pure-Python local-move phase
- `_overlapping_fastmove(n, adj, vertex_comms, comm_members, comm_size, resolution)`
  — static; one full sweep over all vertices in random order
- `quality_overlapping(cover, resolution, weights)` — overlapping CPM quality Q
- `hedonic_value_overlapping(v, c_members, c_idx, resolution)` — per-vertex utility
- `in_equilibrium_overlapping(cover, resolution)` — Nash equilibrium check
- `evaluate_cover(predicted, ground_truth, n_vertices)` — F1, Jaccard, Omega metrics
- `_omega_index(pred, gt, n)` — Collins-Dent omega for overlapping covers

**Verified properties (test_small.py):**
- `in_equilibrium_overlapping` returns `True` after convergence at all tested γ
- `Q_overlapping ≥ Q_non_overlapping` always (monotone improvement)
- Nash equilibrium holds across γ ∈ {0.1, 0.2, 0.3, 0.4} on Petersen graph

### 2. C implementation (`c_patch/leiden_overlapping.c`)

Three functions ready to append to `leiden.c`:

| Function | Role |
|----------|------|
| `igraph_i_community_leiden_overlapping_quality` | Overlapping CPM Q |
| `igraph_i_community_leiden_overlapping_fastmove` | Queue-based local-move, igraph style |
| `igraph_community_leiden_overlapping` | Public API |

**Data structures used:**
```c
comm_vertices : igraph_vector_int_list_t   // community → [vertex, ...]
vertex_comms  : igraph_vector_int_list_t   // vertex    → [community, ...]
comm_weight   : igraph_vector_t            // N_c (weighted community size)
```

NOT yet compiled or tested — needs to be merged into the `lucaslopes/igraph` fork and built.

### 3. Python wrapper sketch (`python_patch/community_overlapping.py`)

Describes `_community_leiden_overlapping()` for `community.py` and the
`graphobject.c` C wrapper pattern. NOT yet merged into `lucaslopes/python-igraph`.

### 4. DBLP experiment script (`scripts/dblp_experiment.py`)

Complete CLI script with:
- `load_dblp(data_dir)` — loads SNAP DBLP files (`.txt.gz`)
- `run_experiment(g, gt, resolution, n_iter)` — Leiden baseline + overlapping + metrics
- `resolution_sweep(og, gt, resolutions, n_iter)` — 10 log-spaced γ values
- argparse CLI with `--data_dir`, `--resolution`, `--resolution_sweep`, `--output`

NOT yet run on DBLP (data not downloaded).

## What is NOT done ❌

### High priority (needed before paper experiments)

1. **C compilation** — `c_patch/leiden_overlapping.c` must be:
   - appended to `lucaslopes/igraph/src/community/leiden.c`
   - declared in `include/igraph_community.h` (signature below)
   - built with cmake
   - tested with a C unit test

2. **graphobject.c wrapper** — `lucaslopes/python-igraph` needs a new
   `igraphmodule_Graph_community_leiden_overlapping()` function in
   `src/_igraph/graphobject.c` that:
   - converts Python `list[list[int]]` → `igraph_vector_int_list_t` (use existing helper `igraphmodule_PyObject_to_vector_int_list_t`)
   - calls `igraph_community_leiden_overlapping()`
   - converts output `igraph_vector_int_list_t` back to Python list-of-lists

3. **DBLP experiment** — download data and run `scripts/dblp_experiment.py`

### Lower priority (future work)

4. **Refinement/aggregation phase for overlapping** — phases 2 and 3 of Leiden
   are currently skipped. Extending them requires a weighted bipartite aggregation
   that is still unformulated.

5. **Node weights support in Python** — `quality_overlapping` and
   `in_equilibrium_overlapping` currently assume unit node weights. The C code
   supports `node_weights` but the Python class does not pass them through.

6. **Performance on large graphs** — `in_equilibrium_overlapping` is O(n·k·d)
   where k = number of communities. For DBLP (n=317k) this may be slow in Python;
   should be checked with the C extension active.

## How to run

```bash
cd /home/davidcubric/hedonic-overlapping

# Quick validation (no DBLP, no C compilation needed)
python3.12 scripts/test_small.py

# DBLP experiment (after downloading data)
mkdir -p data/dblp && cd data/dblp
wget https://snap.stanford.edu/data/com-dblp.ungraph.txt.gz
wget https://snap.stanford.edu/data/com-dblp.cmty.txt.gz
cd /home/davidcubric/hedonic-overlapping
python3.12 scripts/dblp_experiment.py --data_dir data/dblp --resolution 1e-4
```

## Known pitfalls

### 1. igraph version conflict (CRITICAL)
`pip install hedonic` pulls in standard `igraph` (1.0.0) which overwrites
`lucas-igraph` (0.11.9.3). After installing hedonic, always run:
```bash
pip install lucas-igraph --force-reinstall
```
Verify with: `python3.12 -c "import igraph; print(igraph.__version__)"` → must be `0.11.9.3`

### 2. `VertexCover` API
`VertexCover` does NOT have `.membership_list`. Use:
- `list(cover)` → `[[v, v, ...], ...]`  (communities as vertex lists)
- `cover.membership` → `[[c, c, ...], ...]`  (vertices as community-id lists, inverted)

### 3. numpy integers in `_overlapping_fastmove`
`np.random.permutation(n)` returns `np.int64`. Community dict lookups fail
with numpy integers in some contexts. The fix is applied:
```python
for v in map(int, order):   # not: for v in order
```

### 4. Reproducing results
igraph uses its own internal RNG separate from numpy. To get reproducible output:
```python
import random, igraph as ig
ig.set_random_number_generator(random.Random(42))
```

### 5. `OverlappingGame` install location
The class is installed directly into the site-packages of the hedonic package:
```
~/.local/lib/python3.12/site-packages/hedonic/overlapping.py
```
Source of truth is `hedonic_ext/overlapping_game.py`. After editing the source,
copy it back:
```bash
cp hedonic_ext/overlapping_game.py \
   ~/.local/lib/python3.12/site-packages/hedonic/overlapping.py
```

## Key mathematical facts

**Overlapping CPM quality:**
```
Q = (1/2m) · Σ_c [ e_c − γ · N_c · (N_c − 1) / 2 ]
```

**ΔQ when v joins c (v ∉ c):**
```
ΔQ = e(v→c) − γ · n_v · N_c
```

**ΔQ when v leaves c (v ∈ c):**
```
ΔQ = −( e(v→c) − γ · n_v · (N_c − n_v) )
```

**Independence property:** gains across different communities are independent —
`e(v→c)` does not change when v moves in/out of a different community `c'`.
This means all join/leave decisions for vertex v can be computed from a single
neighbor-scan and applied without re-evaluation.

**Nash equilibrium condition:**
```
∀ v, ∀ c :  v ∈ c  →  e(v→c) ≥ γ·(N_c−1)   (no incentive to leave)
            v ∉ c  →  e(v→c) ≤ γ·N_c          (no incentive to join)
```

## C function signature to add to `igraph_community.h`

```c
IGRAPH_EXPORT igraph_error_t igraph_community_leiden_overlapping(
    const igraph_t *graph,
    const igraph_vector_t *edge_weights,       /* NULL → all 1.0 */
    const igraph_vector_t *node_weights,       /* NULL → all 1.0 */
    igraph_real_t resolution_parameter,
    igraph_integer_t n_iterations,             /* < 0 → until convergence */
    const igraph_vector_int_list_t *initial_cover, /* NULL → singleton cover */
    igraph_vector_int_list_t *cover,           /* OUTPUT */
    igraph_real_t *quality);                   /* OUTPUT, NULL → skip */
```

## graphobject.c wrapper — key steps

Follow `igraphmodule_Graph_community_leiden()` in `src/_igraph/graphobject.c`:

```c
/* 1. Parse Python args */
PyObject *initial_cover_obj = Py_None;
double resolution = 1.0;
long n_iterations = -1;
// ...

/* 2. Convert initial_cover Python list-of-lists → igraph type */
igraph_vector_int_list_t initial_cover;
igraph_vector_int_list_init(&initial_cover, 0);
igraphmodule_PyObject_to_vector_int_list_t(initial_cover_obj, &initial_cover);

/* 3. Allocate output cover */
igraph_vector_int_list_t cover;
igraph_vector_int_list_init(&cover, 0);

/* 4. Call C function */
igraph_community_leiden_overlapping(
    &self->g,
    edge_weights_ptr,
    NULL,            /* node weights */
    resolution,
    n_iterations,
    &initial_cover,
    &cover,
    &quality
);

/* 5. Convert cover → Python list-of-lists */
PyObject *result = igraphmodule_vector_int_list_t_to_PyList(&cover);
igraph_vector_int_list_destroy(&cover);
igraph_vector_int_list_destroy(&initial_cover);
return result;
```

## Evaluation target (DBLP)

Dataset: https://snap.stanford.edu/data/com-DBLP.html
- 317,080 nodes, 1,049,866 edges, 13,477 ground-truth communities
- Expected γ range: 1e-5 to 1e-3
- Primary metrics: F1 (best-match macro), Omega index
- Baseline to beat: non-overlapping Leiden + same metrics
