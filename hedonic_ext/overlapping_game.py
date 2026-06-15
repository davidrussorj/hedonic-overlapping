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
            from igraph import Graph as _G
            if hasattr(_G, '_community_leiden_overlapping_c'):
                from hedonic.python_patch import _community_leiden_overlapping
                return _community_leiden_overlapping(
                    self,
                    weights=weights,
                    resolution=resolution,
                    n_iterations=n_iterations,
                    initial_membership=initial_membership,
                )
        except Exception:
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
        while True:
            changed = self._overlapping_fastmove(
                n, adj, vertex_comms, comm_members, comm_size, resolution
            )
            itr += 1
            if not changed:
                break
            if n_iterations > 0 and itr >= n_iterations:
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

        for v in map(int, order):
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
    # Evaluation against ground truth (for DBLP experiments)
    # ------------------------------------------------------------------

    @staticmethod
    def evaluate_cover(
        predicted: list[list[int]],
        ground_truth: list[list[int]],
        n_vertices: int,
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

        Returns
        -------
        dict with keys 'f1', 'jaccard', 'precision', 'recall', 'omega'
        """
        pred_sets = [set(c) for c in predicted if c]
        gt_sets   = [set(c) for c in ground_truth if c]

        def best_match_f1(A_sets, B_sets):
            """For each set in A, find best F1 match in B."""
            total_f1 = 0.0
            for a in A_sets:
                best = 0.0
                for b in B_sets:
                    inter = len(a & b)
                    if inter == 0:
                        continue
                    p = inter / len(a)
                    r = inter / len(b)
                    f1 = 2 * p * r / (p + r)
                    if f1 > best:
                        best = f1
                total_f1 += best
            return total_f1 / len(A_sets) if A_sets else 0.0

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

        f1_pred_to_gt = best_match_f1(pred_sets, gt_sets)
        f1_gt_to_pred = best_match_f1(gt_sets, pred_sets)
        f1 = (f1_pred_to_gt + f1_gt_to_pred) / 2.0
        jaccard = (
            best_match_jaccard(pred_sets, gt_sets)
            + best_match_jaccard(gt_sets, pred_sets)
        ) / 2.0

        # Omega index (pairwise multi-membership agreement)
        omega = OverlappingGame._omega_index(
            predicted, ground_truth, n_vertices
        )

        return {
            "f1": f1,
            "jaccard": jaccard,
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
        """
        def co_count(cover, n):
            """co[i][j] = number of communities both i and j share."""
            co = np.zeros((n, n), dtype=np.int32)
            for members in cover:
                ms = list(members)
                for a in range(len(ms)):
                    for b in range(a + 1, len(ms)):
                        u, v = ms[a], ms[b]
                        co[u, v] += 1
                        co[v, u] += 1
            return co

        co_pred = co_count(pred, n)
        co_gt   = co_count(gt, n)

        max_k = max(co_pred.max(), co_gt.max()) + 1
        n_pairs = n * (n - 1) // 2

        # t_k = fraction of pairs that agree at level k
        t_k = np.zeros(max_k, dtype=float)
        expected_k = np.zeros(max_k, dtype=float)

        for u in range(n):
            for v in range(u + 1, n):
                k_pred = co_pred[u, v]
                k_gt   = co_gt[u, v]
                if k_pred == k_gt:
                    t_k[k_pred] += 1.0

        # Marginal distributions
        for k in range(max_k):
            n_pred_k = int((co_pred == k).sum()) // 2
            n_gt_k   = int((co_gt   == k).sum()) // 2
            expected_k[k] = n_pred_k * n_gt_k / (n_pairs ** 2) if n_pairs > 0 else 0.0

        observed = t_k.sum() / n_pairs if n_pairs > 0 else 0.0
        expected = expected_k.sum()

        if abs(1.0 - expected) < 1e-10:
            return 1.0
        return (observed - expected) / (1.0 - expected)
