"""
OverlappingGame — extends hedonic.Game for overlapping community detection.

Add this class to lucaslopes/hedonic (e.g., hedonic/overlapping.py)
and import it from hedonic/__init__.py.

Usage example:
    import igraph as ig
    from hedonic.overlapping import OverlappingGame

    g = ig.Graph.Famous("Petersen")
    og = OverlappingGame(g)
    cover = og.community_leiden_overlapping(resolution=og.density())
    print(cover)
    print("Quality:", og.quality_overlapping(cover.membership_list, og.density()))
"""

from __future__ import annotations

import math
import time
import numpy as np
from collections import defaultdict
from igraph import Graph
from igraph.clustering import VertexCover

try:
    from hedonic import Game
except ImportError:
    # allow standalone testing
    from igraph import Graph as Game


class OverlappingGame(Game):
    """
    Vectorized hedonic game for overlapping community detection.

    Each vertex v independently decides for each community c whether to
    join or leave, based on:

        join  c if  deg(v, c) > γ · N_c          (v ∉ c)
        leave c if  deg(v, c) < γ · (N_c − 1)    (v ∈ c, unit node weights)

    where deg(v, c) = number of v's neighbors in c
          N_c       = number of vertices in c
          γ         = resolution parameter

    The global overlapping CPM quality is:
        Q = (1/2m) · Σ_c [ e_c − γ · C(N_c, 2) ]
    """

    # ------------------------------------------------------------------
    # Main detection method
    # ------------------------------------------------------------------

    def community_leiden_overlapping(
        self,
        resolution: float | None = None,
        n_iterations: int = -1,
        initial_membership: list[int] | None = None,
        weights: list[float] | None = None,
    ) -> VertexCover:
        """Run overlapping community detection via the vectorized hedonic game.

        Calls the C-level igraph_community_leiden_overlapping() through the
        python-igraph fork.  Falls back to a pure-Python implementation when
        the C extension is not available (useful for testing).

        Parameters
        ----------
        resolution : float
            CPM resolution γ.  Defaults to graph density.
        n_iterations : int
            Outer iterations (-1 = until convergence).
        initial_membership : list[int] or None
            Starting non-overlapping partition.  None → standard Leiden first.
        weights : list[float] or None
            Edge weights.

        Returns
        -------
        VertexCover
        """
        if resolution is None:
            resolution = self.density()

        # Try C extension first
        try:
            from igraph.community import _community_leiden_overlapping
            return _community_leiden_overlapping(
                self,
                weights=weights,
                resolution=resolution,
                n_iterations=n_iterations,
                initial_membership=initial_membership,
            )
        except (ImportError, AttributeError):
            pass

        # Pure-Python fallback
        return self._community_leiden_overlapping_python(
            resolution=resolution,
            n_iterations=n_iterations,
            initial_membership=initial_membership,
            weights=weights,
        )

    # ------------------------------------------------------------------
    # Pure-Python implementation (for validation / debugging)
    # ------------------------------------------------------------------

    def _community_leiden_overlapping_python(
        self,
        resolution: float,
        n_iterations: int,
        initial_membership: list[int] | None,
        weights: list[float] | None,
    ) -> VertexCover:
        """Pure-Python local-moving phase for overlapping communities."""
        n = self.vcount()

        # Resolve edge weights
        if weights is None:
            w = [1.0] * self.ecount()
        else:
            w = list(weights)

        # Build adjacency: adj[v] = [(u, weight), ...]
        adj: list[list[tuple[int, float]]] = [[] for _ in range(n)]
        for e_idx, (src, tgt) in enumerate(self.get_edgelist()):
            adj[src].append((tgt, w[e_idx]))
            adj[tgt].append((src, w[e_idx]))

        # Get initial non-overlapping partition
        if initial_membership is None:
            init = self.community_leiden(
                resolution=resolution, n_iterations=-1
            )
            initial_membership = init.membership

        # Build cover as list-of-sets
        n_comms = max(initial_membership) + 1
        comm_members: list[set[int]] = [set() for _ in range(n_comms)]
        for v, c in enumerate(initial_membership):
            comm_members[c].add(v)

        # vertex → set of communities
        vertex_comms: list[set[int]] = [set() for _ in range(n)]
        for c, members in enumerate(comm_members):
            for v in members:
                vertex_comms[v].add(c)

        # community size (unit node weights: N_c = |c|)
        comm_size = [len(m) for m in comm_members]

        # Run local-moving iterations
        itr = 0
        t0_total = time.time()
        while True:
            t_sweep = time.time()
            n_active = sum(1 for s in comm_members if s)
            print(f"[fastmove] sweep {itr + 1} — {n:,} vértices, {n_active:,} comunidades …", flush=True)
            changed = self._overlapping_fastmove(
                n, adj, vertex_comms, comm_members, comm_size, resolution
            )
            itr += 1
            elapsed = time.time() - t_sweep
            n_active = sum(1 for s in comm_members if s)
            status = "mudou" if changed else "estável"
            print(f"[fastmove] sweep {itr} — {n_active:,} comunidades  [{elapsed:.1f}s]  {status}", flush=True)
            if not changed:
                print(f"[fastmove] convergiu após {itr} sweep(s)  [{time.time() - t0_total:.1f}s total]", flush=True)
                break
            if n_iterations > 0 and itr >= n_iterations:
                print(f"[fastmove] atingiu limite de {n_iterations} iterações  [{time.time() - t0_total:.1f}s total]", flush=True)
                break

        # Build output: list of sorted vertex lists per non-empty community
        cover_lists = [
            sorted(members)
            for members in comm_members
            if members
        ]
        return VertexCover(self, cover_lists)

    @staticmethod
    def _overlapping_fastmove(
        n: int,
        adj: list[list[tuple[int, float]]],
        vertex_comms: list[set[int]],
        comm_members: list[set[int]],
        comm_size: list[int],
        resolution: float,
    ) -> bool:
        """One sweep of the overlapping local-moving phase.

        Returns True if any vertex changed membership.
        """
        changed = False
        order = np.random.permutation(n)
        checkpoint = max(1, n // 10)
        t_start = time.time()

        for i, v in enumerate(map(int, order)):
            if i > 0 and i % checkpoint == 0:
                pct = 100 * i // n
                print(f"[fastmove]   {pct:3d}%  [{time.time() - t_start:.0f}s]", flush=True)
            # Accumulate edge weight to each community seen in neighborhood
            ewc: dict[int, float] = defaultdict(float)
            for u, wvu in adj[v]:
                for c in vertex_comms[u]:
                    ewc[c] += wvu
            # Also include v's own communities (even if no neighbor there)
            for c in vertex_comms[v]:
                if c not in ewc:
                    ewc[c] = 0.0

            to_join = []
            to_leave = []

            for c, ew in ewc.items():
                Nc = comm_size[c]
                if c in vertex_comms[v]:
                    # v ∈ c: leave if deg(v,c) < γ*(Nc-1)
                    gain_leave = -(ew - resolution * (Nc - 1))
                    if gain_leave > 0:
                        to_leave.append(c)
                else:
                    # v ∉ c: join if deg(v,c) > γ*Nc
                    gain_join = ew - resolution * Nc
                    if gain_join > 0:
                        to_join.append(c)

            for c in to_leave:
                vertex_comms[v].discard(c)
                comm_members[c].discard(v)
                comm_size[c] -= 1
                changed = True

            for c in to_join:
                vertex_comms[v].add(c)
                comm_members[c].add(v)
                comm_size[c] += 1
                changed = True

        return changed

    # ------------------------------------------------------------------
    # v2: fractional-intensity hedonic game (ports c_patch/leiden.c)
    # ------------------------------------------------------------------
    #
    # Different quality model from the v1 methods above: each vertex v
    # holds a membership *vector* sigma_v and participates in every
    # community c in sigma_v with fractional intensity f_v = 1/sqrt(|sigma_v|)
    # instead of a binary 0/1 weight. This keeps the pairwise interaction
    # coefficient kappa_ij = |sigma_i ∩ sigma_j| / sqrt(k_i k_j) <= 1, so
    # edges are never double-counted and the model reduces exactly to plain
    # CPM when every vertex has a single membership. See the header comment
    # of the "Overlapping (vectorized) extension" section in c_patch/leiden.c
    # for the full derivation (exact potential game, ADD/REMOVE/SUBSTITUTE
    # best response, convergence proof).
    #
    # This Python port only implements Phase 1 (local moving) of that file,
    # matching the scope of the v1 `_community_leiden_overlapping_python`
    # fallback above — it does not run the token-graph refinement/
    # aggregation phases (2 and 3), which are a Leiden-specific performance
    # optimization, not part of the hedonic-game equilibrium guarantee.
    # `beta` is accepted for API parity with the future C binding but has
    # no effect here since it only governs that skipped refinement step.

    def community_leiden_overlapping_v2(
        self,
        resolution: float | None = None,
        beta: float = 0.01,
        max_memberships: int = 4,
        n_iterations: int = -1,
        weights: list[float] | None = None,
        verbose: bool = False,
    ) -> VertexCover:
        """Run the fractional-intensity overlapping hedonic game (v2).

        Calls the C-level igraph_community_leiden_overlapping() (new
        signature, once wired through the python-igraph fork) through
        `igraph.community._community_leiden_overlapping_v2`. Falls back to
        a pure-Python implementation when the C extension is not available.

        Parameters
        ----------
        resolution : float
            CPM resolution γ. Defaults to graph density.
        beta : float
            Refinement randomness, as in igraph's community_leiden. Unused
            in the pure-Python fallback (see module note above).
        max_memberships : int
            Maximum number of communities K a vertex may belong to at once.
            K = 1 recovers a disjoint clustering.
        n_iterations : int
            Outer iterations (-1 = until quality stops improving).
        weights : list[float] or None
            Edge weights.
        verbose : bool
            Print per-sweep progress (pure-Python fallback only). Keep off
            when running many small instances in a batch experiment.

        Returns
        -------
        VertexCover
        """
        if resolution is None:
            resolution = self.density()

        try:
            from igraph.community import _community_leiden_overlapping_v2
            return _community_leiden_overlapping_v2(
                self,
                weights=weights,
                resolution=resolution,
                beta=beta,
                max_memberships=max_memberships,
                n_iterations=n_iterations,
            )
        except (ImportError, AttributeError):
            pass

        return self._community_leiden_overlapping_v2_python(
            resolution=resolution,
            beta=beta,
            max_memberships=max_memberships,
            n_iterations=n_iterations,
            weights=weights,
            verbose=verbose,
        )

    def _community_leiden_overlapping_v2_python(
        self,
        resolution: float,
        beta: float,
        max_memberships: int,
        n_iterations: int,
        weights: list[float] | None,
        verbose: bool = False,
    ) -> VertexCover:
        """Pure-Python local-moving phase for the v2 (fractional) hedonic game."""
        n = self.vcount()

        if weights is None:
            w = [1.0] * self.ecount()
        else:
            w = list(weights)

        adj: list[list[tuple[int, float]]] = [[] for _ in range(n)]
        for e_idx, (src, tgt) in enumerate(self.get_edgelist()):
            if src == tgt:
                continue  # self-loops contribute to Q independently of membership
            adj[src].append((tgt, w[e_idx]))
            adj[tgt].append((src, w[e_idx]))

        # Start from the singleton cover: node v belongs to community v only.
        sigma: list[set[int]] = [{v} for v in range(n)]
        comm_mass: dict[int, float] = {v: 1.0 for v in range(n)}  # S_c, unit node weights
        next_comm_id = n

        inv_sqrt_cache: dict[int, float] = {}

        def inv_sqrt(k: int) -> float:
            val = inv_sqrt_cache.get(k)
            if val is None:
                val = 1.0 / math.sqrt(k)
                inv_sqrt_cache[k] = val
            return val

        itr = 0
        t0_total = time.time()
        while True:
            t_sweep = time.time()
            n_comms = len(comm_mass)
            if verbose:
                print(f"[fastmove_v2] sweep {itr + 1} — {n:,} vértices, {n_comms:,} comunidades …", flush=True)
            changed, next_comm_id = self._overlapping_fastmove_v2(
                n, adj, sigma, comm_mass, resolution, max_memberships,
                next_comm_id, inv_sqrt, verbose,
            )
            itr += 1
            elapsed = time.time() - t_sweep
            status = "mudou" if changed else "estável"
            if verbose:
                print(f"[fastmove_v2] sweep {itr} — {len(comm_mass):,} comunidades  [{elapsed:.1f}s]  {status}", flush=True)
            if not changed:
                if verbose:
                    print(f"[fastmove_v2] convergiu após {itr} sweep(s)  [{time.time() - t0_total:.1f}s total]", flush=True)
                break
            if n_iterations > 0 and itr >= n_iterations:
                if verbose:
                    print(f"[fastmove_v2] atingiu limite de {n_iterations} iterações  [{time.time() - t0_total:.1f}s total]", flush=True)
                break

        # Compact community ids 0..K-1 in order of first appearance and
        # build the community → vertices cover expected by the rest of the API.
        renumber: dict[int, int] = {}
        cover_lists: list[list[int]] = []
        for v in range(n):
            for c in sorted(sigma[v]):
                if c not in renumber:
                    renumber[c] = len(cover_lists)
                    cover_lists.append([])
                cover_lists[renumber[c]].append(v)

        return VertexCover(self, cover_lists)

    @staticmethod
    def _overlapping_fastmove_v2(
        n: int,
        adj: list[list[tuple[int, float]]],
        sigma: list[set[int]],
        comm_mass: dict[int, float],
        resolution: float,
        max_memberships: int,
        next_comm_id: int,
        inv_sqrt,
        verbose: bool = False,
    ) -> tuple[bool, int]:
        """One sweep of the v2 local-moving phase.

        For each vertex, computes the exact best-response membership set:
        candidates (own communities + neighbours' + one fresh empty
        community) are scored by gain g_c = L_v^c - γ·n_v·W_v^c and the
        prefix of the gain-descending sorted candidates maximizing
        (sum of top-j gains)/sqrt(j), j <= max_memberships, is adopted
        whenever it strictly beats the current score.

        Returns (changed, next_comm_id).
        """
        changed = False
        order = np.random.permutation(n)
        checkpoint = max(1, n // 10)
        t_start = time.time()

        for i, v in enumerate(map(int, order)):
            if verbose and i > 0 and i % checkpoint == 0:
                pct = 100 * i // n
                print(f"[fastmove_v2]   {pct:3d}%  [{time.time() - t_start:.0f}s]", flush=True)

            k = len(sigma[v])
            fv = inv_sqrt(k)
            nv = 1.0  # unit node weights

            # L_v^c: fractional edge weight from v to each candidate community
            edge_w_to_comm: dict[int, float] = defaultdict(float)
            for u, wvu in adj[v]:
                ku = len(sigma[u])
                fu = inv_sqrt(ku)
                wf = wvu * fu
                for c in sigma[u]:
                    edge_w_to_comm[c] += wf

            candidates = set(sigma[v])
            candidates.update(edge_w_to_comm.keys())
            empty_c = next_comm_id  # fresh recyclable candidate; subsumes isolation moves
            candidates.add(empty_c)

            gains: dict[int, float] = {}
            for c in candidates:
                gain = edge_w_to_comm.get(c, 0.0) - resolution * nv * comm_mass.get(c, 0.0)
                if c in sigma[v]:
                    # comm_mass[c] still includes v's own mass; add it back so
                    # gain reflects W_v^c = S_c - n_v*f_v, not S_c itself.
                    gain += resolution * nv * nv * fv
                gains[c] = gain

            cur_score = fv * sum(gains[c] for c in sigma[v])

            cand_sorted = sorted(candidates, key=lambda c: (-gains[c], c))

            best_score = cur_score
            best_j = 0
            prefix = 0.0
            jmax = min(len(cand_sorted), max_memberships)
            for j in range(1, jmax + 1):
                prefix += gains[cand_sorted[j - 1]]
                score = prefix * inv_sqrt(j)
                if score > best_score:
                    best_score = score
                    best_j = j

            if best_j > 0:
                chosen = set(cand_sorted[:best_j])
                if chosen != sigma[v]:
                    changed = True
                    fnew = inv_sqrt(best_j)
                    for c in sigma[v] - chosen:
                        comm_mass[c] -= nv * fv
                        if comm_mass[c] <= 1e-12:
                            del comm_mass[c]
                    for c in chosen & sigma[v]:
                        comm_mass[c] += nv * (fnew - fv)
                    for c in chosen - sigma[v]:
                        comm_mass[c] = comm_mass.get(c, 0.0) + nv * fnew
                    if empty_c in chosen:
                        next_comm_id += 1
                    sigma[v] = chosen

        return changed, next_comm_id

    # ------------------------------------------------------------------
    # Quality metrics
    # ------------------------------------------------------------------

    def quality_overlapping(
        self,
        cover: list[list[int]],
        resolution: float,
        weights: list[float] | None = None,
    ) -> float:
        """Compute overlapping CPM quality.

        Q = (1/2m) · Σ_c [ e_c − γ · C(N_c, 2) ]

        Parameters
        ----------
        cover : list of list of int
            Each inner list is the vertices belonging to that community.
        resolution : float
            CPM resolution γ.
        weights : list[float] or None
            Edge weights.

        Returns
        -------
        float
        """
        if weights is None:
            w = [1.0] * self.ecount()
        else:
            w = list(weights)

        total_w = sum(w)
        if total_w == 0:
            return 0.0

        # Build vertex → set of communities for fast lookup
        n = self.vcount()
        v_comms: list[set[int]] = [set() for _ in range(n)]
        for c_idx, members in enumerate(cover):
            for v in members:
                v_comms[v].add(c_idx)

        quality = 0.0
        for c_idx, members in enumerate(cover):
            Nc = len(members)
            if Nc == 0:
                continue
            member_set = set(members)
            # Count internal edges
            ec = 0.0
            for e_idx, (src, tgt) in enumerate(self.get_edgelist()):
                if src in member_set and tgt in member_set:
                    ec += w[e_idx]
            quality += ec - resolution * Nc * (Nc - 1) / 2.0

        return quality / (2.0 * total_w)

    def quality_overlapping_v2(
        self,
        cover: list[list[int]],
        resolution: float,
        weights: list[float] | None = None,
    ) -> float:
        """Compute the v2 (fractional-intensity) overlapping CPM quality.

        Q = (1/2m) · Σ_c [ 2·E_c − γ·S_c² ]  (self-pair terms folded in as
        in c_patch/leiden.c's igraph_i_community_leiden_ov_quality), where
        each vertex v participates in c ∈ sigma_v with intensity
        f_v = 1/sqrt(|sigma_v|), E_c interaction between an edge (i,j) is
        weighted by |sigma_i ∩ sigma_j| / sqrt(k_i · k_j), and
        S_c = Σ_v f_v^c (unit node weights).

        Reduces exactly to `quality_overlapping`'s CPM value when every
        vertex has a single membership (k_v = 1 everywhere).

        Parameters
        ----------
        cover : list of list of int
            Each inner list is the vertices belonging to that community.
        resolution : float
            CPM resolution γ.
        weights : list[float] or None
            Edge weights.

        Returns
        -------
        float
        """
        if weights is None:
            w = [1.0] * self.ecount()
        else:
            w = list(weights)

        n = self.vcount()
        v_comms: list[set[int]] = [set() for _ in range(n)]
        for c_idx, members in enumerate(cover):
            for v in members:
                v_comms[v].add(c_idx)

        comm_mass: dict[int, float] = defaultdict(float)
        for v in range(n):
            k = len(v_comms[v])
            if k == 0:
                continue
            fv = 1.0 / math.sqrt(k)
            for c in v_comms[v]:
                comm_mass[c] += fv

        total_w = sum(w)
        q = 0.0
        for e_idx, (src, tgt) in enumerate(self.get_edgelist()):
            we = w[e_idx]
            if src == tgt:
                q += 2.0 * we
                continue
            ks, kt = len(v_comms[src]), len(v_comms[tgt])
            if ks == 0 or kt == 0:
                continue
            shared = len(v_comms[src] & v_comms[tgt])
            if shared:
                q += 2.0 * we * shared / math.sqrt(ks * kt)

        q -= resolution * sum(m * m for m in comm_mass.values())

        return q / (2.0 * total_w) if total_w > 0 else 0.0

    def hedonic_value_overlapping(
        self,
        v: int,
        c_members: set[int],
        c_idx: int,
        resolution: float,
        weights: list[float] | None = None,
    ) -> float:
        """Individual hedonic value of vertex v in community c.

        H(v, c) = deg(v, c) - γ · (N_c - 1)   if v ∈ c (stability check)
        H(v, c) = deg(v, c) - γ · N_c           if v ∉ c (join incentive)
        """
        in_c = v in c_members
        Nc = len(c_members)
        deg_vc = 0.0
        for u in self.neighbors(v):
            if u in c_members and u != v:
                deg_vc += 1.0
        if in_c:
            return deg_vc - resolution * (Nc - 1)
        else:
            return deg_vc - resolution * Nc

    # ------------------------------------------------------------------
    # Nash equilibrium check for overlapping cover
    # ------------------------------------------------------------------

    def in_equilibrium_overlapping(
        self,
        cover: list[list[int]],
        resolution: float,
    ) -> bool:
        """Check if the cover is a Nash equilibrium of the vectorized hedonic game.

        A cover C is in equilibrium iff for every (v, c) pair:
          - if v ∈ c: H(v, c) ≥ 0  (v does not want to leave)
          - if v ∉ c: H(v, c) ≤ 0  (v does not want to join)
        """
        n = self.vcount()
        v_comms: list[set[int]] = [set() for _ in range(n)]
        comm_sets = []
        for c_idx, members in enumerate(cover):
            ms = set(members)
            comm_sets.append(ms)
            for v in members:
                v_comms[v].add(c_idx)

        for v in range(n):
            # Build deg_vc for all communities at once
            deg_vc: dict[int, float] = defaultdict(float)
            for u in self.neighbors(v):
                for c in v_comms[u]:
                    if u != v:
                        deg_vc[c] += 1.0

            for c_idx, ms in enumerate(comm_sets):
                Nc = len(ms)
                ew = deg_vc.get(c_idx, 0.0)
                if c_idx in v_comms[v]:
                    # v ∈ c: should not want to leave
                    if ew - resolution * (Nc - 1) < 0:
                        return False
                else:
                    # v ∉ c: should not want to join
                    if ew - resolution * Nc > 0:
                        return False
        return True

    # ------------------------------------------------------------------
    # Baseline reference covers (extreme points of the cover space)
    # ------------------------------------------------------------------

    @staticmethod
    def singleton_cover(n: int) -> list[list[int]]:
        """Maximum-granularity cover: every vertex isolated in its own community."""
        return [[v] for v in range(n)]

    @staticmethod
    def grand_coalition_cover(n: int) -> list[list[int]]:
        """Minimum-granularity cover: every vertex in a single shared community."""
        return [list(range(n))]

    @staticmethod
    def total_overlap_cover(n: int, n_communities: int) -> list[list[int]]:
        """Maximum-redundancy cover: `n_communities` identical communities,
        each containing every vertex, so every vertex's membership vector is
        identical (co-membership count = n_communities for every pair).

        Under best-match metrics (F1, Jaccard) this is indistinguishable
        from `grand_coalition_cover` by construction — only multiplicity-
        sensitive metrics (e.g. the Omega index) tell them apart, which is
        the point of including it as a distinct reference point.
        """
        full = list(range(n))
        return [list(full) for _ in range(max(1, n_communities))]

    # ------------------------------------------------------------------
    # Evaluation against ground truth (for DBLP experiments)
    # ------------------------------------------------------------------

    @staticmethod
    def evaluate_cover(
        predicted: list[list[int]],
        ground_truth: list[list[int]],
        n_vertices: int,
        compute_omega: bool = True,
    ) -> dict:
        """Compute evaluation metrics between predicted and ground-truth covers.

        Metrics:
          - F1 (set-matching, macro average)
          - Jaccard (macro average, best-match)
          - Precision / Recall (macro average)
          - Omega index (agreement on pairwise multi-community co-memberships)

        Parameters
        ----------
        predicted : list of list of int
        ground_truth : list of list of int
        n_vertices : int
        compute_omega : bool
            Omega is O(n_vertices²); set False to skip it on large instances
            (e.g. inside a batch experiment) and compute it later from a
            cached cover via `_omega_index` directly.

        Returns
        -------
        dict with keys 'f1', 'jaccard', 'precision', 'recall', 'omega'
        ('omega' is None when compute_omega=False)
        """
        pred_sets = [set(c) for c in predicted if c]
        gt_sets   = [set(c) for c in ground_truth if c]

        def best_match_f1_precision_recall(A_sets, B_sets):
            """For each set in A, find the B match with the best F1 and
            report that match's F1, precision and recall (macro-averaged)."""
            total_f1 = total_p = total_r = 0.0
            for a in A_sets:
                best_f1 = best_p = best_r = 0.0
                for b in B_sets:
                    inter = len(a & b)
                    if inter == 0:
                        continue
                    p = inter / len(a)
                    r = inter / len(b)
                    f1 = 2 * p * r / (p + r)
                    if f1 > best_f1:
                        best_f1, best_p, best_r = f1, p, r
                total_f1 += best_f1
                total_p += best_p
                total_r += best_r
            if not A_sets:
                return 0.0, 0.0, 0.0
            return total_f1 / len(A_sets), total_p / len(A_sets), total_r / len(A_sets)

        def best_match_jaccard(A_sets, B_sets):
            total = 0.0
            for a in A_sets:
                best = 0.0
                for b in B_sets:
                    inter = len(a & b)
                    union = len(a | b)
                    j = inter / union if union > 0 else 0.0
                    if j > best:
                        best = j
                total += best
            return total / len(A_sets) if A_sets else 0.0

        # best_match_f1_precision_recall(A, B) macro-averages, per set in A,
        # the F1-best match in B along with that match's |inter|/|A-set| and
        # |inter|/|B-set|. With A=pred it's (f1, precision, _); with A=gt
        # the first ratio |inter|/|gt-set| is recall.
        f1_pred_to_gt, precision, _ = best_match_f1_precision_recall(pred_sets, gt_sets)
        f1_gt_to_pred, recall, _ = best_match_f1_precision_recall(gt_sets, pred_sets)
        f1 = (f1_pred_to_gt + f1_gt_to_pred) / 2.0
        jaccard = (
            best_match_jaccard(pred_sets, gt_sets)
            + best_match_jaccard(gt_sets, pred_sets)
        ) / 2.0

        # Omega index (pairwise multi-membership agreement) — O(n²), optional
        omega = (
            OverlappingGame._omega_index(predicted, ground_truth, n_vertices)
            if compute_omega else None
        )

        return {
            "f1": f1,
            "jaccard": jaccard,
            "precision": precision,
            "recall": recall,
            "omega": omega,
            "n_predicted_comms": len(pred_sets),
            "n_gt_comms": len(gt_sets),
        }

    @staticmethod
    def _omega_index(
        pred: list[list[int]],
        gt: list[list[int]],
        n: int,
    ) -> float:
        """Omega index for overlapping community comparison.

        Collins & Dent (1988) / Esquivel & Rosvall (2011).

        Counts how often a pair of vertices appears together in exactly
        k communities in both the predicted and ground-truth covers.

        Vectorized: co-membership counts come from a sparse
        membership @ membership.T product (no Python loop over
        community-internal pairs — cheap for both many-tiny-communities
        covers like `singleton` and few-huge-communities covers like
        `grand_coalition`/`total_overlap`), and the pairwise agreement /
        marginal distributions are computed with numpy over the dense
        upper triangle instead of a Python double loop over all n(n-1)/2
        pairs. The naive Python loops this replaces are unusable above a
        few hundred vertices; this scales to n in the thousands.
        """
        from scipy import sparse

        def co_count(cover, n):
            """co[i, j] = number of communities both i and j belong to (i != j)."""
            c_count = len(cover)
            if c_count == 0:
                return np.zeros((n, n), dtype=np.int32)
            rows, cols = [], []
            for c, members in enumerate(cover):
                ms = list(members)
                rows.extend(ms)
                cols.extend([c] * len(ms))
            if not rows:
                return np.zeros((n, n), dtype=np.int32)
            data = np.ones(len(rows), dtype=np.int32)
            m = sparse.csr_matrix((data, (rows, cols)), shape=(n, c_count))
            # Generic sparse-sparse matmul is fast when the membership matrix
            # is genuinely sparse (leiden, hedonic, singleton), but covers like
            # grand_coalition/total_overlap put (almost) every vertex in every
            # community — a dense matrix in sparse disguise — where dense BLAS
            # matmul beats it by 1-2 orders of magnitude.
            density = len(rows) / (n * c_count)
            if density > 0.05:
                md = m.toarray().astype(np.float64)
                co = (md @ md.T).astype(np.int32)
            else:
                co = (m @ m.T).toarray().astype(np.int32)
            np.fill_diagonal(co, 0)
            return co

        co_pred = co_count(pred, n)
        co_gt   = co_count(gt, n)

        n_pairs = n * (n - 1) // 2
        if n_pairs == 0:
            return 1.0

        iu, iv = np.triu_indices(n, k=1)
        k_pred = co_pred[iu, iv]
        k_gt   = co_gt[iu, iv]
        max_k = int(max(k_pred.max(), k_gt.max())) + 1

        observed = np.count_nonzero(k_pred == k_gt) / n_pairs

        n_pred_k = np.bincount(k_pred, minlength=max_k).astype(np.float64)
        n_gt_k   = np.bincount(k_gt, minlength=max_k).astype(np.float64)
        expected = float(np.sum(n_pred_k * n_gt_k) / (n_pairs ** 2))

        if abs(1.0 - expected) < 1e-10:
            return 1.0
        return (observed - expected) / (1.0 - expected)
