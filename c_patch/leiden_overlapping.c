/* -*- mode: C -*-  */
/*
 * Overlapping Community Detection via Vectorized Hedonic Game
 *
 * Extension of the CPM-based Leiden algorithm to detect overlapping
 * communities. Each vertex independently decides whether to join or leave
 * each community, preserving the key property:
 *
 *   ΔQ_global = Δhedonic_value(v, c)
 *
 * for every (vertex v, community c) pair.
 *
 * Quality (overlapping CPM):
 *
 *   Q = (1/2m) * Σ_c [ e_c - γ * N_c * (N_c - 1) / 2 ]
 *
 * where:
 *   e_c = Σ_{(i,j)∈E} w(i,j) · 1[i∈c] · 1[j∈c]   (weighted internal edges)
 *   N_c = Σ_i n_i · 1[i∈c]                          (weighted community size)
 *   m   = Σ_{(i,j)∈E} w(i,j)                        (total edge weight)
 *
 * Gain from v joining c (v ∉ c):
 *   ΔQ = e(v→c) - γ · n_v · N_c          > 0  →  join
 *
 * Gain from v leaving c (v ∈ c):
 *   ΔQ = -(e(v→c) - γ · n_v · (N_c - n_v))  > 0  →  leave
 *
 * where e(v→c) = Σ_{u∈c\{v}, (v,u)∈E} w(v,u)
 *
 * These are the individual hedonic values in the vectorized hedonic game.
 * Each community is an independent binary decision for each vertex.
 *
 * ADD THIS FILE'S CONTENTS at the end of leiden.c in lucaslopes/igraph.
 * Also declare igraph_community_leiden_overlapping() in igraph_community.h.
 */

/* -----------------------------------------------------------------------
 * Internal: compute overlapping CPM quality
 * ----------------------------------------------------------------------- */

static igraph_error_t igraph_i_community_leiden_overlapping_quality(
        const igraph_t *graph,
        const igraph_inclist_t *edges_per_node,
        const igraph_vector_t *edge_weights,
        const igraph_vector_t *node_weights,
        const igraph_vector_int_list_t *comm_vertices, /* comm → [vertex, ...] */
        const igraph_vector_int_list_t *vertex_comms,  /* vertex → [comm, ...]  */
        const igraph_real_t resolution,
        igraph_real_t *quality) {

    igraph_integer_t n  = igraph_vcount(graph);
    igraph_integer_t nc = igraph_vector_int_list_size(comm_vertices);
    igraph_real_t total_edge_weight = 0.0;
    *quality = 0.0;

    /* total edge weight (denominator) */
    for (igraph_integer_t v = 0; v < n; v++) {
        igraph_vector_int_t *edges = igraph_inclist_get(edges_per_node, v);
        igraph_integer_t deg = igraph_vector_int_size(edges);
        for (igraph_integer_t i = 0; i < deg; i++) {
            igraph_integer_t e = VECTOR(*edges)[i];
            igraph_integer_t u = IGRAPH_OTHER(graph, e, v);
            if (u > v) {
                total_edge_weight += VECTOR(*edge_weights)[e];
            }
        }
    }

    if (total_edge_weight == 0.0) {
        return IGRAPH_SUCCESS;
    }

    /* For each community c: compute e_c and N_c */
    for (igraph_integer_t c = 0; c < nc; c++) {
        igraph_vector_int_t *members = igraph_vector_int_list_get_ptr(
                (igraph_vector_int_list_t *)comm_vertices, c);
        igraph_integer_t sz = igraph_vector_int_size(members);

        if (sz == 0) continue;

        /* N_c = sum of node weights in c */
        igraph_real_t Nc = 0.0;
        for (igraph_integer_t i = 0; i < sz; i++) {
            Nc += VECTOR(*node_weights)[VECTOR(*members)[i]];
        }

        /* e_c = sum of edge weights with both endpoints in c */
        igraph_real_t ec = 0.0;
        for (igraph_integer_t i = 0; i < sz; i++) {
            igraph_integer_t v = VECTOR(*members)[i];
            igraph_vector_int_t *vedges = igraph_inclist_get(edges_per_node, v);
            igraph_integer_t deg = igraph_vector_int_size(vedges);
            for (igraph_integer_t j = 0; j < deg; j++) {
                igraph_integer_t e = VECTOR(*vedges)[j];
                igraph_integer_t u = IGRAPH_OTHER(graph, e, v);
                if (u == v) continue;
                /* Check if u ∈ c: scan u's community list */
                igraph_vector_int_t *u_comms = igraph_vector_int_list_get_ptr(
                        (igraph_vector_int_list_t *)vertex_comms, u);
                igraph_integer_t u_nc = igraph_vector_int_size(u_comms);
                for (igraph_integer_t k = 0; k < u_nc; k++) {
                    if (VECTOR(*u_comms)[k] == c) {
                        ec += VECTOR(*edge_weights)[e];
                        break;
                    }
                }
            }
        }
        ec /= 2.0; /* each edge counted twice (once from each endpoint) */

        *quality += ec - resolution * Nc * (Nc - 1.0) / 2.0;
    }

    *quality /= (2.0 * total_edge_weight);
    return IGRAPH_SUCCESS;
}

/* -----------------------------------------------------------------------
 * Internal: local moving phase for overlapping communities
 *
 * For each vertex v (queue-based):
 *   1. Scan neighbors → accumulate edge_weight_to_comm[c] for all communities
 *      reachable from v (either because v is in c, or a neighbor is in c).
 *   2. For each c ∋ v:   gain_leave = -(ewc - nv*(Nc-nv)*γ); leave if > 0
 *   3. For each c ∌ v:   gain_join  = ewc - nv*Nc*γ;         join  if > 0
 *   4. All gains are independent across communities, so all moves can be
 *      decided from the same ewc snapshot and applied atomically.
 * ----------------------------------------------------------------------- */

static igraph_error_t igraph_i_community_leiden_overlapping_fastmove(
        const igraph_t *graph,
        const igraph_inclist_t *edges_per_node,
        const igraph_vector_t *edge_weights,
        const igraph_vector_t *node_weights,
        const igraph_real_t resolution,
        igraph_vector_int_list_t *vertex_comms, /* vertex → [comm, ...] */
        igraph_vector_int_list_t *comm_vertices, /* comm   → [vertex, ...] */
        igraph_vector_t *comm_weight,            /* Nc for each community  */
        igraph_bool_t *changed) {

    igraph_integer_t n  = igraph_vcount(graph);
    igraph_integer_t nc = igraph_vector_int_list_size(comm_vertices);
    int iter = 0;

    /* Dense accumulator: edge weight from current vertex to each community */
    igraph_vector_t ewc;
    IGRAPH_VECTOR_INIT_FINALLY(&ewc, nc);

    /* Visited community list for cleanup per vertex */
    igraph_vector_int_t visited;
    IGRAPH_VECTOR_INT_INIT_FINALLY(&visited, 0);

    /* Bitset: is current vertex a member of community c? */
    igraph_bitset_t member_of;
    IGRAPH_BITSET_INIT_FINALLY(&member_of, nc);

    /* Bitset: has community c been added to visited list? */
    igraph_bitset_t seen;
    IGRAPH_BITSET_INIT_FINALLY(&seen, nc);

    /* Queue of unstable vertices */
    igraph_dqueue_int_t queue;
    IGRAPH_DQUEUE_INT_INIT_FINALLY(&queue, n);
    igraph_bitset_t in_queue;
    IGRAPH_BITSET_INIT_FINALLY(&in_queue, n);

    /* Pending joins/leaves collected per vertex before applying */
    igraph_vector_int_t to_join;
    igraph_vector_int_t to_leave;
    IGRAPH_VECTOR_INT_INIT_FINALLY(&to_join, 0);
    IGRAPH_VECTOR_INT_INIT_FINALLY(&to_leave, 0);

    /* Shuffle initial order */
    igraph_vector_int_t node_order;
    IGRAPH_CHECK(igraph_vector_int_init_range(&node_order, 0, n));
    IGRAPH_FINALLY(igraph_vector_int_destroy, &node_order);
    IGRAPH_CHECK(igraph_vector_int_shuffle(&node_order));
    for (igraph_integer_t i = 0; i < n; i++) {
        igraph_integer_t v = VECTOR(node_order)[i];
        IGRAPH_CHECK(igraph_dqueue_int_push(&queue, v));
        IGRAPH_BIT_SET(in_queue, v);
    }
    igraph_vector_int_destroy(&node_order);
    IGRAPH_FINALLY_CLEAN(1);

    *changed = false;

    while (!igraph_dqueue_int_empty(&queue)) {
        igraph_integer_t v = igraph_dqueue_int_pop(&queue);
        IGRAPH_BIT_CLEAR(in_queue, v);

        igraph_real_t nv = VECTOR(*node_weights)[v];
        igraph_vector_int_t *v_comms = igraph_vector_int_list_get_ptr(vertex_comms, v);
        igraph_integer_t v_nc = igraph_vector_int_size(v_comms);

        /* Mark v's current communities in member_of and visited */
        for (igraph_integer_t i = 0; i < v_nc; i++) {
            igraph_integer_t c = VECTOR(*v_comms)[i];
            IGRAPH_BIT_SET(member_of, c);
            if (!IGRAPH_BIT_TEST(seen, c)) {
                IGRAPH_BIT_SET(seen, c);
                IGRAPH_CHECK(igraph_vector_int_push_back(&visited, c));
            }
            /* ewc[c] starts at 0 (cleaned up from last iteration) */
        }

        /* Scan neighbors, accumulate edge weights per community */
        igraph_vector_int_t *edges = igraph_inclist_get(edges_per_node, v);
        igraph_integer_t deg = igraph_vector_int_size(edges);
        for (igraph_integer_t i = 0; i < deg; i++) {
            igraph_integer_t e  = VECTOR(*edges)[i];
            igraph_integer_t u  = IGRAPH_OTHER(graph, e, v);
            if (u == v) continue;
            igraph_real_t    w  = VECTOR(*edge_weights)[e];
            igraph_vector_int_t *u_comms = igraph_vector_int_list_get_ptr(vertex_comms, u);
            igraph_integer_t u_nc = igraph_vector_int_size(u_comms);
            for (igraph_integer_t j = 0; j < u_nc; j++) {
                igraph_integer_t c = VECTOR(*u_comms)[j];
                if (!IGRAPH_BIT_TEST(seen, c)) {
                    IGRAPH_BIT_SET(seen, c);
                    IGRAPH_CHECK(igraph_vector_int_push_back(&visited, c));
                }
                VECTOR(ewc)[c] += w;
            }
        }

        /* Evaluate each candidate community and collect decisions */
        igraph_integer_t n_visited = igraph_vector_int_size(&visited);
        for (igraph_integer_t i = 0; i < n_visited; i++) {
            igraph_integer_t c  = VECTOR(visited)[i];
            igraph_real_t    Nc = VECTOR(*comm_weight)[c];
            igraph_real_t    w  = VECTOR(ewc)[c];

            if (IGRAPH_BIT_TEST(member_of, c)) {
                /* v ∈ c: should v leave? */
                /* ΔQ_leave = -(e(v→c) - nv*(Nc-nv)*γ) > 0 iff e(v→c) < nv*(Nc-nv)*γ */
                igraph_real_t gain = -(w - nv * (Nc - nv) * resolution);
                if (gain > 0.0) {
                    IGRAPH_CHECK(igraph_vector_int_push_back(&to_leave, c));
                }
            } else {
                /* v ∉ c: should v join? */
                /* ΔQ_join = e(v→c) - nv*Nc*γ > 0 */
                igraph_real_t gain = w - nv * Nc * resolution;
                if (gain > 0.0) {
                    IGRAPH_CHECK(igraph_vector_int_push_back(&to_join, c));
                }
            }
        }

        igraph_bool_t v_changed = false;

        /* Apply LEAVE moves */
        igraph_integer_t n_leave = igraph_vector_int_size(&to_leave);
        for (igraph_integer_t i = 0; i < n_leave; i++) {
            igraph_integer_t c = VECTOR(to_leave)[i];

            /* Remove v from comm_vertices[c] */
            igraph_vector_int_t *cverts = igraph_vector_int_list_get_ptr(comm_vertices, c);
            igraph_integer_t csz = igraph_vector_int_size(cverts);
            for (igraph_integer_t j = 0; j < csz; j++) {
                if (VECTOR(*cverts)[j] == v) {
                    igraph_vector_int_remove(cverts, j);
                    break;
                }
            }
            /* Remove c from vertex_comms[v] */
            igraph_integer_t vcsz = igraph_vector_int_size(v_comms);
            for (igraph_integer_t j = 0; j < vcsz; j++) {
                if (VECTOR(*v_comms)[j] == c) {
                    igraph_vector_int_remove(v_comms, j);
                    break;
                }
            }
            VECTOR(*comm_weight)[c] -= nv;
            IGRAPH_BIT_CLEAR(member_of, c);
            v_changed = true;
        }

        /* Apply JOIN moves */
        igraph_integer_t n_join = igraph_vector_int_size(&to_join);
        for (igraph_integer_t i = 0; i < n_join; i++) {
            igraph_integer_t c = VECTOR(to_join)[i];
            IGRAPH_CHECK(igraph_vector_int_push_back(
                    igraph_vector_int_list_get_ptr(comm_vertices, c), v));
            IGRAPH_CHECK(igraph_vector_int_push_back(v_comms, c));
            VECTOR(*comm_weight)[c] += nv;
            v_changed = true;
        }

        if (v_changed) {
            *changed = true;
            /* Re-add neighbors to queue */
            for (igraph_integer_t i = 0; i < deg; i++) {
                igraph_integer_t e = VECTOR(*edges)[i];
                igraph_integer_t u = IGRAPH_OTHER(graph, e, v);
                if (u != v && !IGRAPH_BIT_TEST(in_queue, u)) {
                    IGRAPH_CHECK(igraph_dqueue_int_push(&queue, u));
                    IGRAPH_BIT_SET(in_queue, u);
                }
            }
        }

        /* Cleanup for next vertex */
        for (igraph_integer_t i = 0; i < n_visited; i++) {
            igraph_integer_t c = VECTOR(visited)[i];
            VECTOR(ewc)[c] = 0.0;
            IGRAPH_BIT_CLEAR(seen, c);
            IGRAPH_BIT_CLEAR(member_of, c);
        }
        igraph_vector_int_clear(&visited);
        igraph_vector_int_clear(&to_join);
        igraph_vector_int_clear(&to_leave);

        IGRAPH_ALLOW_INTERRUPTION_LIMITED(iter, 1 << 14);
    }

    igraph_vector_int_destroy(&to_leave);
    igraph_vector_int_destroy(&to_join);
    igraph_bitset_destroy(&in_queue);
    igraph_dqueue_int_destroy(&queue);
    igraph_bitset_destroy(&seen);
    igraph_bitset_destroy(&member_of);
    igraph_vector_int_destroy(&visited);
    igraph_vector_destroy(&ewc);
    IGRAPH_FINALLY_CLEAN(8);

    return IGRAPH_SUCCESS;
}

/* -----------------------------------------------------------------------
 * Public API
 *
 * igraph_community_leiden_overlapping()
 *
 * Parameters:
 *   graph              - undirected input graph
 *   edge_weights       - edge weights (NULL = all 1.0)
 *   node_weights       - node weights (NULL = all 1.0)
 *   resolution         - CPM resolution parameter γ
 *   n_iterations       - number of outer iterations (< 0 = until convergence)
 *   initial_cover      - initial cover as list of vertex lists per community
 *                        (NULL = start from non-overlapping singleton cover,
 *                         i.e., each vertex in its own community)
 *   cover              - OUTPUT: final cover (list of vertex lists per community)
 *   quality            - OUTPUT: final quality (NULL = don't compute)
 *
 * Recommended workflow:
 *   1. Run igraph_community_leiden() to get a non-overlapping partition.
 *   2. Convert membership vector to initial_cover.
 *   3. Call this function to refine into overlapping communities.
 * ----------------------------------------------------------------------- */

igraph_error_t igraph_community_leiden_overlapping(
        const igraph_t *graph,
        const igraph_vector_t *edge_weights,
        const igraph_vector_t *node_weights,
        const igraph_real_t resolution,
        const igraph_integer_t n_iterations,
        const igraph_vector_int_list_t *initial_cover,
        igraph_vector_int_list_t *cover,
        igraph_real_t *quality) {

    igraph_integer_t n = igraph_vcount(graph);

    if (igraph_is_directed(graph)) {
        IGRAPH_ERROR("Overlapping Leiden is only implemented for undirected graphs.",
                     IGRAPH_EINVAL);
    }

    /* ---- default edge weights ---- */
    igraph_vector_t *i_edge_weights;
    igraph_vector_t default_edge_weights;
    if (!edge_weights) {
        IGRAPH_VECTOR_INIT_FINALLY(&default_edge_weights, igraph_ecount(graph));
        igraph_vector_fill(&default_edge_weights, 1.0);
        i_edge_weights = &default_edge_weights;
    } else {
        i_edge_weights = (igraph_vector_t *)edge_weights;
    }

    /* ---- default node weights ---- */
    igraph_vector_t *i_node_weights;
    igraph_vector_t default_node_weights;
    if (!node_weights) {
        IGRAPH_VECTOR_INIT_FINALLY(&default_node_weights, n);
        igraph_vector_fill(&default_node_weights, 1.0);
        i_node_weights = &default_node_weights;
    } else {
        i_node_weights = (igraph_vector_t *)node_weights;
    }

    /* ---- build comm_vertices (the cover) ---- */
    igraph_integer_t nc;  /* number of communities */
    igraph_vector_int_list_t comm_vertices;

    if (initial_cover) {
        nc = igraph_vector_int_list_size(initial_cover);
        IGRAPH_VECTOR_INT_LIST_INIT_FINALLY(&comm_vertices, nc);
        for (igraph_integer_t c = 0; c < nc; c++) {
            igraph_vector_int_t *src = igraph_vector_int_list_get_ptr(
                    (igraph_vector_int_list_t *)initial_cover, c);
            igraph_vector_int_t *dst = igraph_vector_int_list_get_ptr(&comm_vertices, c);
            IGRAPH_CHECK(igraph_vector_int_update(dst, src));
        }
    } else {
        /* singleton cover: each vertex is its own community */
        nc = n;
        IGRAPH_VECTOR_INT_LIST_INIT_FINALLY(&comm_vertices, nc);
        for (igraph_integer_t v = 0; v < n; v++) {
            IGRAPH_CHECK(igraph_vector_int_push_back(
                    igraph_vector_int_list_get_ptr(&comm_vertices, v), v));
        }
    }

    /* ---- build vertex_comms (inverse index) ---- */
    igraph_vector_int_list_t vertex_comms;
    IGRAPH_VECTOR_INT_LIST_INIT_FINALLY(&vertex_comms, n);
    for (igraph_integer_t c = 0; c < nc; c++) {
        igraph_vector_int_t *members = igraph_vector_int_list_get_ptr(&comm_vertices, c);
        igraph_integer_t sz = igraph_vector_int_size(members);
        for (igraph_integer_t i = 0; i < sz; i++) {
            igraph_integer_t v = VECTOR(*members)[i];
            IGRAPH_CHECK(igraph_vector_int_push_back(
                    igraph_vector_int_list_get_ptr(&vertex_comms, v), c));
        }
    }

    /* ---- build comm_weight (N_c for each community) ---- */
    igraph_vector_t comm_weight;
    IGRAPH_VECTOR_INIT_FINALLY(&comm_weight, nc);
    for (igraph_integer_t c = 0; c < nc; c++) {
        igraph_vector_int_t *members = igraph_vector_int_list_get_ptr(&comm_vertices, c);
        igraph_integer_t sz = igraph_vector_int_size(members);
        for (igraph_integer_t i = 0; i < sz; i++) {
            VECTOR(comm_weight)[c] += VECTOR(*i_node_weights)[VECTOR(*members)[i]];
        }
    }

    /* ---- incidence list for fast neighbor iteration ---- */
    igraph_inclist_t edges_per_node;
    IGRAPH_CHECK(igraph_inclist_init(graph, &edges_per_node, IGRAPH_ALL, IGRAPH_LOOPS_TWICE));
    IGRAPH_FINALLY(igraph_inclist_destroy, &edges_per_node);

    /* ---- main loop ---- */
    igraph_bool_t changed = true;
    for (igraph_integer_t itr = 0;
         n_iterations < 0 ? changed : itr < n_iterations;
         itr++) {
        IGRAPH_CHECK(igraph_i_community_leiden_overlapping_fastmove(
                graph, &edges_per_node,
                i_edge_weights, i_node_weights,
                resolution,
                &vertex_comms, &comm_vertices, &comm_weight,
                &changed));
    }

    /* ---- compute quality ---- */
    if (quality) {
        IGRAPH_CHECK(igraph_i_community_leiden_overlapping_quality(
                graph, &edges_per_node,
                i_edge_weights, i_node_weights,
                &comm_vertices, &vertex_comms,
                resolution, quality));
    }

    /* ---- write output cover (skip empty communities) ---- */
    igraph_vector_int_list_clear(cover);
    for (igraph_integer_t c = 0; c < nc; c++) {
        igraph_vector_int_t *members = igraph_vector_int_list_get_ptr(&comm_vertices, c);
        if (igraph_vector_int_size(members) > 0) {
            IGRAPH_CHECK(igraph_vector_int_list_push_back_copy(cover, members));
        }
    }

    igraph_inclist_destroy(&edges_per_node);
    igraph_vector_destroy(&comm_weight);
    igraph_vector_int_list_destroy(&vertex_comms);
    igraph_vector_int_list_destroy(&comm_vertices);
    IGRAPH_FINALLY_CLEAN(4);

    if (!node_weights) {
        igraph_vector_destroy(&default_node_weights);
        IGRAPH_FINALLY_CLEAN(1);
    }
    if (!edge_weights) {
        igraph_vector_destroy(&default_edge_weights);
        IGRAPH_FINALLY_CLEAN(1);
    }

    return IGRAPH_SUCCESS;
}
