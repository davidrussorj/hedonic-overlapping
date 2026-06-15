"""
Additions to lucaslopes/python-igraph — src/igraph/community.py

1. Paste _community_leiden_overlapping() into community.py alongside the existing
   _community_leiden() function.

2. Add the method binding in graphobject.c (see note below).

3. The C-level function igraph_community_leiden_overlapping() must be declared
   in igraph_community.h and exposed via graphobject.c exactly like
   community_leiden is (see the two existing commits in the fork for the pattern).

NOTE on graphobject.c:
  The new C wrapper in graphobject.c should follow the same pattern as
  igraphmodule_Graph_community_leiden() but:
    - Accept initial_cover as a list-of-lists (converted to igraph_vector_int_list_t)
    - Return the cover as a list-of-lists → VertexCover
  See the pattern for returning covers in igraphmodule_Graph_community_edge_betweenness().
"""

from igraph import Graph
from igraph.clustering import VertexCover


def _community_leiden_overlapping(
    graph: Graph,
    weights=None,
    resolution: float = 1.0,
    n_iterations: int = -1,
    initial_membership=None,
):
    """Detect overlapping communities via the vectorized hedonic game.

    Extends the CPM-based Leiden algorithm so each vertex can belong to
    multiple communities simultaneously.  Each (vertex, community) pair is
    an independent binary decision:

      join  community c if  edges(v→c) > γ · n_v · N_c
      leave community c if  edges(v→c) < γ · n_v · (N_c − n_v)

    The algorithm starts from the non-overlapping Leiden result and then
    allows vertices to join additional communities.

    Parameters
    ----------
    weights : str, list, or None
        Edge weight attribute name or list of edge weights.
    resolution : float
        CPM resolution parameter γ.  Higher values → smaller, denser
        communities.  Use graph.density() as a sensible default.
    n_iterations : int
        Number of outer iterations.  -1 means iterate until convergence.
    initial_membership : list[int] or None
        Non-overlapping starting partition (one integer per vertex).
        If None, runs standard Leiden first to obtain an initial partition.

    Returns
    -------
    VertexCover
        Overlapping cover where each vertex may appear in multiple communities.
    """
    # Step 1: resolve edge weights
    edge_weights = None
    if weights is not None:
        if isinstance(weights, str):
            edge_weights = graph.es[weights]
        else:
            edge_weights = list(weights)

    # Step 2: get initial non-overlapping partition if not provided
    if initial_membership is None:
        init = graph.community_leiden(
            weights=edge_weights,
            resolution=resolution,
            n_iterations=-1,
        )
        initial_membership = init.membership

    # Step 3: convert membership to initial_cover (list of lists)
    n_comms = max(initial_membership) + 1
    initial_cover = [[] for _ in range(n_comms)]
    for v, c in enumerate(initial_membership):
        initial_cover[c].append(v)

    # Step 4: call the C-level overlapping Leiden
    # This calls igraph_community_leiden_overlapping() via the C extension.
    # The C function is exposed as GraphBase.community_leiden_overlapping().
    cover_lists = graph._community_leiden_overlapping_c(
        edge_weights=edge_weights,
        resolution=resolution,
        n_iterations=n_iterations,
        initial_cover=initial_cover,
    )

    return VertexCover(graph, cover_lists)


# ---------------------------------------------------------------------------
# graphobject.c — C wrapper sketch (pseudo-code / reference)
# ---------------------------------------------------------------------------
# The actual C implementation follows the same boilerplate as
# igraphmodule_Graph_community_leiden().  Key differences:
#
#  INPUT:  initial_cover as Python list-of-lists
#          → igraph_vector_int_list_t initial_cover_c
#
#  CALL:   igraph_community_leiden_overlapping(
#              &self->g,
#              edge_weights_ptr,   /* or NULL */
#              NULL,               /* node weights = 1 */
#              resolution,
#              n_iterations,
#              &initial_cover_c,
#              &cover_c,
#              &quality
#          );
#
#  OUTPUT: igraph_vector_int_list_t cover_c
#          → Python list-of-lists  (communities as lists of vertex ids)
#          → wrapped as VertexCover in Python
#
# Use igraph_vector_int_list_init() / igraph_vector_int_list_destroy() for
# the cover_c buffer.  Convert Python list-of-lists to/from
# igraph_vector_int_list_t with the helpers already present in igraphmodule.c
# (search for igraphmodule_PyObject_to_vector_int_list_t).
