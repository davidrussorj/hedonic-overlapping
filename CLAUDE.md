# CLAUDE.md — Overlapping Hedonic Game

---

## ⚡ PRÓXIMA SESSÃO — Fase 4: DBLP

**Fases 1, 2 e 3 estão concluídas.** Só falta rodar o experimento DBLP.

**Problema identificado na última tentativa:**
O `dblp_experiment.py` usa `load_dblp()` que chama `g.simplify()` após construir o grafo.
Para 317k nós + 1M arestas isso consome ~3.5GB RAM e >8 minutos só no carregamento.
O processo foi cancelado antes de chegar na parte do experimento.

**Solução para próxima sessão — remover o `simplify()` ou usar grafo pré-processado:**

Opção A (rápida): remover `g.simplify()` do `load_dblp()` em `scripts/dblp_experiment.py`
— o DBLP já não tem multi-arestas relevantes.

Opção B (robusta): pré-processar o DBLP uma vez e salvar como `.pkl`:
```python
import pickle, igraph as ig
# rodar uma vez:
g, gt, _ = load_dblp('data/dblp')
pickle.dump((g, gt), open('data/dblp/dblp.pkl', 'wb'))
# nas próximas execuções:
g, gt = pickle.load(open('data/dblp/dblp.pkl', 'rb'))
```

**Comando para rodar:**
```bash
cd /home/davidcubric/hedonic-overlapping
python3.12 scripts/dblp_experiment.py --data_dir data/dblp --resolution_sweep --output results/dblp_sweep.json
```

**Estado do OverlappingGame (já corrigido):**
O `hedonic/overlapping.py` agora usa o backend C corretamente via `GraphBase.community_leiden_overlapping()`.
Arquivo: `~/.local/lib/python3.12/site-packages/hedonic/overlapping.py`

---

## ⚡ PRÓXIMA SESSÃO — Fase 3 (graphobject.c)

**Objetivo:** expor `igraph_community_leiden_overlapping` ao Python retornando `VertexCover`.

**Tudo já está pronto para começar:**
- Função C compilada em `libigraph.a` ✅
- Conversores existem com nomes corretos ✅
  - `igraphmodule_PyObject_to_vector_int_list_t()` — Python list → C
  - `igraphmodule_vector_int_list_t_to_PyList()` — C → Python list
- Skeleton do wrapper já escrito no CLAUDE.md (seção Fase 3) ✅
- Wrapper Python (`community.py`) já escrito em `python_patch/community_overlapping.py` ✅

**4 passos na ordem:**

1. **Inserir wrapper em `graphobject.c`** — linha 13574 é onde `community_leiden` está definida; inserir logo abaixo (linha ~13700)
2. **Registrar na tabela de métodos** — linha 18551 é onde `community_leiden` está registrada; inserir logo abaixo
3. **Adicionar wrapper Python em `community.py`** — copiar de `python_patch/community_overlapping.py`
4. **Recompilar e testar:**
   ```bash
   cd /home/davidcubric/python-igraph
   python3.12 -m pip install -e . --no-build-isolation
   python3.12 scripts/test_small.py
   ```

**Atenção:** os binários de build em `/tmp/` são perdidos ao reiniciar. Recriar com:
```bash
cd /tmp && apt-get download bison flex m4
dpkg -x bison_*.deb ./bison_pkg && dpkg -x flex_*.deb ./flex_pkg && dpkg -x m4_*.deb ./m4_pkg
export PATH="/tmp/m4_pkg/usr/bin:/tmp/bison_pkg/usr/bin:/tmp/flex_pkg/usr/bin:$PATH"
export BISON_PKGDATADIR=/tmp/bison_pkg/usr/share/bison && export M4=/tmp/m4_pkg/usr/bin/m4
```

---

## O que é este projeto

Extensão do algoritmo Leiden baseado em CPM para detectar comunidades **overlapping**
via jogo hedônico vetorizado. A contribuição teórica central é mostrar que a função de
qualidade CPM overlapping se decompõe em valores de utilidade por par (vértice, comunidade),
de modo que um equilíbrio de Nash do jogo vetorizado corresponde a um máximo local de Q.

Trabalho conjunto entre o dono do repositório (implementação) e Sadoc (teoria).

---

## Repositórios no GitHub

| Repositório | URL | Branch | Status |
|-------------|-----|--------|--------|
| Este repo (patches + experimentos) | https://github.com/davidrussorj/hedonic-overlapping | `main` | ✅ atualizado |
| igraph C fork | https://github.com/davidrussorj/igraph | `overlapping` | ✅ Fase 2 commitada |
| python-igraph fork | https://github.com/davidrussorj/python-igraph | — | ❌ Fase 3 pendente |
| hedonic lib (upstream) | https://github.com/lucaslopes/hedonic | — | OverlappingGame instalada localmente |

---

## Estrutura do repositório local

```
hedonic-overlapping/          ← github.com/davidrussorj/hedonic-overlapping
├── CLAUDE.md                 ← este arquivo
├── README.md                 ← documentação em português (432 linhas, verificada)
├── c_patch/
│   └── leiden_overlapping.c  ← código C (492 linhas) — já aplicado ao igraph fork
├── python_patch/
│   └── community_overlapping.py  ← wrapper Python + guia graphobject.c (Fase 3)
├── hedonic_ext/
│   └── overlapping_game.py   ← classe OverlappingGame (495 linhas, fonte da verdade)
└── scripts/
    ├── test_small.py         ← validação em grafos pequenos (roda agora)
    └── dblp_experiment.py    ← experimento DBLP (200 linhas)

/home/davidcubric/igraph/                     ← clone do fork C (lucaslopes/igraph)
  branch: overlapping                         ← nossa branch com a Fase 2
  remote davidrussorj → github.com/davidrussorj/igraph

/home/davidcubric/python-igraph/              ← clone do fork Python (lucaslopes/python-igraph)
  branch: lucas                               ← sem mudanças commitadas ainda (Fase 3)
  vendor/install/igraph/lib/libigraph.a       ← biblioteca compilada com nossa função
```

---

## Ambiente atual

```
Python          : 3.12.10  (/usr/local/bin/python3.12)
igraph          : 0.11.9.3  (instalado de /home/davidcubric/python-igraph em modo editable)
numpy           : 2.3.2
hedonic         : 0.0.1  (lucaslopes/hedonic)
OverlappingGame : ~/.local/lib/python3.12/site-packages/hedonic/overlapping.py
```

### Ferramentas de build (sem sudo)

```
cmake  : ~/.local/bin/cmake  (instalado via pip)
bison  : /tmp/bison_pkg/usr/bin/bison  (extraído de .deb via apt-get download)
flex   : /tmp/flex_pkg/usr/bin/flex    (extraído de .deb via apt-get download)
m4     : /tmp/m4_pkg/usr/bin/m4        (extraído de .deb via apt-get download)
```

⚠️ Os binários em `/tmp/` são temporários e serão perdidos ao reiniciar o sistema.
Para recompilar, reextrair com:
```bash
cd /tmp
apt-get download bison flex m4
dpkg -x bison_*.deb ./bison_pkg
dpkg -x flex_*.deb  ./flex_pkg
dpkg -x m4_*.deb    ./m4_pkg
export PATH="/tmp/m4_pkg/usr/bin:/tmp/bison_pkg/usr/bin:/tmp/flex_pkg/usr/bin:$PATH"
export BISON_PKGDATADIR=/tmp/bison_pkg/usr/share/bison
export M4=/tmp/m4_pkg/usr/bin/m4
```

### Flags de compilação usadas

```bash
cmake .. \
  -DIGRAPH_WARNINGS_AS_ERRORS=OFF \
  -DIGRAPH_GLPK_SUPPORT=OFF \
  -DIGRAPH_GMP_SUPPORT=OFF \
  -DIGRAPH_GRAPHML_SUPPORT=OFF \
  -DIGRAPH_OPENMP_SUPPORT=OFF \
  -DBISON_EXECUTABLE=/tmp/bison_pkg/usr/bin/bison \
  -DFLEX_EXECUTABLE=/tmp/flex_pkg/usr/bin/flex \
  -DCMAKE_POSITION_INDEPENDENT_CODE=ON
```

---

## O que está feito ✅

### Fase 1 — Python puro

`hedonic_ext/overlapping_game.py` → instalado em `hedonic/overlapping.py`

Classe `OverlappingGame(Game)` com:

| Método | Descrição |
|--------|-----------|
| `community_leiden_overlapping(resolution, n_iterations, initial_membership, weights)` | Entrada principal; tenta C, cai em Python |
| `_community_leiden_overlapping_python(...)` | Fase de local-move pura em Python |
| `_overlapping_fastmove(n, adj, vertex_comms, comm_members, comm_size, resolution)` | Um sweep completo em ordem aleatória |
| `quality_overlapping(cover, resolution, weights)` | Qualidade CPM overlapping Q |
| `hedonic_value_overlapping(v, c_members, c_idx, resolution)` | Utilidade individual |
| `in_equilibrium_overlapping(cover, resolution)` | Verificação de equilíbrio de Nash |
| `evaluate_cover(predicted, ground_truth, n_vertices)` | F1, Jaccard, Omega |
| `_omega_index(pred, gt, n)` | Índice omega de Collins-Dent |

**Propriedades verificadas:**
- `in_equilibrium_overlapping` retorna `True` após convergência em todos os γ testados
- `Q_overlapping ≥ Q_non_overlapping` sempre (melhoria monotônica)
- Equilíbrio de Nash verificado para γ ∈ {0.1, 0.2, 0.3, 0.4} no grafo de Petersen

---

### Fase 2 — Biblioteca C ✅

**Commit:** `e317b763c` na branch `overlapping` de `davidrussorj/igraph`
**URL:** https://github.com/davidrussorj/igraph/tree/overlapping

**Dois arquivos modificados:**

#### `src/community/leiden.c` (+492 linhas)

Três novas funções adicionadas ao final do arquivo:

| Função | Linhas | Papel |
|--------|--------|-------|
| `igraph_i_community_leiden_overlapping_quality` | ~70 | Calcula Q do CPM overlapping |
| `igraph_i_community_leiden_overlapping_fastmove` | ~230 | Fase de local-move com fila, estilo igraph |
| `igraph_community_leiden_overlapping` | ~130 | API pública, gerencia estruturas de dados |

**Estruturas de dados usadas:**
```c
comm_vertices : igraph_vector_int_list_t   // comunidade → [vértice, ...]
vertex_comms  : igraph_vector_int_list_t   // vértice    → [comunidade, ...]
comm_weight   : igraph_vector_t            // N_c para cada comunidade
```

**Decisões acumulador + bitset** (mesmo padrão do `fastmovenodes` original):
```c
igraph_vector_t ewc;          // acumulador de peso de arestas por comunidade
igraph_bitset_t member_of;    // v ∈ c?
igraph_bitset_t seen;         // c foi visitada neste turno?
igraph_dqueue_int_t queue;    // fila de vértices instáveis
```

#### `include/igraph_community.h` (+12 linhas)

Declaração pública adicionada após `igraph_community_leiden`:

```c
IGRAPH_EXPORT igraph_error_t igraph_community_leiden_overlapping(
    const igraph_t *graph,
    const igraph_vector_t *edge_weights,       /* NULL → tudo 1.0 */
    const igraph_vector_t *node_weights,       /* NULL → tudo 1.0 */
    igraph_real_t resolution_parameter,
    igraph_integer_t n_iterations,             /* < 0 → até convergência */
    const igraph_vector_int_list_t *initial_cover, /* NULL → cover singleton */
    igraph_vector_int_list_t *cover,           /* SAÍDA */
    igraph_real_t *quality);                   /* SAÍDA, NULL → ignorar */
```

**Verificação de compilação:**
```
nm /home/davidcubric/igraph/build/src/libigraph.a | grep igraph_community_leiden_overlapping
→ 0000000000002da0 T igraph_community_leiden_overlapping  ✓
```

**Por que o símbolo não aparece no `.so` ainda?**
O linker só inclui símbolos da `libigraph.a` que são referenciados pelo código da extensão Python (`graphobject.c`). Como o wrapper ainda não existe (Fase 3), o símbolo está na `.a` mas não no `.so`. Isso é esperado.

---

## O que NÃO está feito ❌

### Fase 3 — Wrapper Python em `graphobject.c` (próximo passo)

**Repositório:** `davidrussorj/python-igraph` (ainda não criado — fork de `lucaslopes/python-igraph`)
**Arquivo:** `src/_igraph/graphobject.c`

Adicionar função `igraphmodule_Graph_community_leiden_overlapping()` seguindo o padrão
de `igraphmodule_Graph_community_leiden()`.

**Etapas:**

1. Criar fork `davidrussorj/python-igraph` no GitHub
2. Adicionar a função em `graphobject.c` (esqueleto abaixo)
3. Registrar a função na tabela de métodos do objeto Graph
4. Adicionar wrapper Python em `src/igraph/community.py` (já escrito em `python_patch/community_overlapping.py`)
5. Rebuild com `pip install -e . --no-build-isolation`

**Esqueleto do wrapper `graphobject.c`:**

```c
/** \ingroup python_interface_graph
 * \brief Finds overlapping communities via vectorized hedonic game (CPM)
 */
PyObject *igraphmodule_Graph_community_leiden_overlapping(
    igraphmodule_GraphObject *self, PyObject *args, PyObject *kwds)
{
  static char *kwlist[] = {
    "resolution", "n_iterations", "weights", "initial_cover", NULL
  };
  PyObject *weights_o = Py_None;
  PyObject *initial_cover_o = Py_None;
  PyObject *result_o;
  double resolution = 1.0;
  long int n_iterations = -1;
  igraph_vector_t weights;
  igraph_vector_int_list_t initial_cover, cover;
  igraph_real_t quality;
  igraph_bool_t has_weights = false;

  if (!PyArg_ParseTupleAndKeywords(args, kwds, "|dlOO", kwlist,
        &resolution, &n_iterations, &weights_o, &initial_cover_o))
    return NULL;

  /* Convert edge weights */
  if (weights_o != Py_None) {
    if (igraphmodule_attrib_to_vector_t(weights_o, self, &weights,
          ATTRIBUTE_TYPE_EDGE)) return NULL;
    has_weights = true;
  }

  /* Convert initial_cover (Python list-of-lists → igraph_vector_int_list_t) */
  igraph_vector_int_list_init(&initial_cover, 0);
  if (initial_cover_o != Py_None) {
    if (igraphmodule_PyObject_to_vector_int_list_t(initial_cover_o, &initial_cover)) {
      if (has_weights) igraph_vector_destroy(&weights);
      igraph_vector_int_list_destroy(&initial_cover);
      return NULL;
    }
  }

  /* Allocate output cover */
  if (igraph_vector_int_list_init(&cover, 0)) {
    if (has_weights) igraph_vector_destroy(&weights);
    igraph_vector_int_list_destroy(&initial_cover);
    return NULL;
  }

  /* Call C function */
  if (igraph_community_leiden_overlapping(
        &self->g,
        has_weights ? &weights : NULL,
        NULL,                   /* node weights = 1 */
        (igraph_real_t)resolution,
        (igraph_integer_t)n_iterations,
        initial_cover_o != Py_None ? &initial_cover : NULL,
        &cover,
        &quality)) {
    igraphmodule_handle_igraph_error();
    if (has_weights) igraph_vector_destroy(&weights);
    igraph_vector_int_list_destroy(&initial_cover);
    igraph_vector_int_list_destroy(&cover);
    return NULL;
  }

  /* Convert output cover → Python list-of-lists */
  result_o = igraphmodule_vector_int_list_t_to_PyList(&cover);

  /* Cleanup */
  if (has_weights) igraph_vector_destroy(&weights);
  igraph_vector_int_list_destroy(&initial_cover);
  igraph_vector_int_list_destroy(&cover);

  /* Return (cover_list, quality) */
  return Py_BuildValue("(Od)", result_o, (double)quality);
}
```

**Registrar na tabela de métodos** (buscar por `community_leiden` em `graphobject.c`):
```c
{"community_leiden_overlapping",
 (PyCFunction) igraphmodule_Graph_community_leiden_overlapping,
 METH_VARARGS | METH_KEYWORDS,
 "community_leiden_overlapping(resolution, n_iterations, weights, initial_cover)\n--\n\n"
 "Detects overlapping communities via vectorized hedonic game.\n"},
```

**Wrapper Python** (`src/igraph/community.py`) — já escrito em `python_patch/community_overlapping.py`.
Retorna `VertexCover` em vez de `VertexClustering`.

---

### Fase 4 — Experimento DBLP

Não depende da Fase 3 — pode rodar com Python puro (lento para 317k nós).

```bash
cd /home/davidcubric/hedonic-overlapping
mkdir -p data/dblp && cd data/dblp
wget https://snap.stanford.edu/data/com-dblp.ungraph.txt.gz
wget https://snap.stanford.edu/data/com-dblp.cmty.txt.gz
cd ..
python3.12 scripts/dblp_experiment.py --data_dir data/dblp --resolution_sweep
```

---

## Como executar o que já funciona

```bash
cd /home/davidcubric/hedonic-overlapping

# Testes rápidos (Python puro, sem compilação C)
python3.12 scripts/test_small.py
```

---

## Armadilhas conhecidas

### 1. Conflito igraph/lucas-igraph (CRÍTICO)
`pip install hedonic` instala o igraph padrão por cima do lucas-igraph. Após instalar:
```bash
pip install lucas-igraph --force-reinstall
```
Verificar: `python3.12 -c "import igraph; print(igraph.__version__)"` → deve ser `0.11.9.3`

### 2. API do `VertexCover`
`VertexCover` não tem `.membership_list`. Usar:
- `list(cover)` → `[[v, v, ...], ...]`  (comunidades como listas de vértices)
- `cover.membership` → `[[c, c, ...], ...]`  (vértices indexados por id, invertido)

### 3. Inteiros numpy em `_overlapping_fastmove`
`np.random.permutation(n)` retorna `np.int64`. Correção aplicada:
```python
for v in map(int, order):   # não: for v in order
```

### 4. Reproduzir resultados
O igraph tem seu próprio RNG separado do numpy:
```python
import random, igraph as ig
ig.set_random_number_generator(random.Random(42))
```

### 5. Localização do `OverlappingGame`
Instalado diretamente no site-packages do hedonic:
```
~/.local/lib/python3.12/site-packages/hedonic/overlapping.py
```
Fonte da verdade: `hedonic_ext/overlapping_game.py`. Após editar, copiar:
```bash
cp hedonic_ext/overlapping_game.py \
   ~/.local/lib/python3.12/site-packages/hedonic/overlapping.py
```

### 6. Recompilar após reiniciar o sistema
Os binários em `/tmp/` são perdidos. Recriar com:
```bash
cd /tmp && apt-get download bison flex m4
dpkg -x bison_*.deb ./bison_pkg && dpkg -x flex_*.deb ./flex_pkg && dpkg -x m4_*.deb ./m4_pkg
export PATH="/tmp/m4_pkg/usr/bin:/tmp/bison_pkg/usr/bin:/tmp/flex_pkg/usr/bin:$PATH"
export BISON_PKGDATADIR=/tmp/bison_pkg/usr/share/bison && export M4=/tmp/m4_pkg/usr/bin/m4
cd /home/davidcubric/igraph/build && make -j$(nproc)
cd /home/davidcubric/python-igraph && python3.12 -m pip install -e . --no-build-isolation
```

---

## Fundamento matemático

**Qualidade CPM overlapping:**
```
Q = (1/2m) · Σ_c [ e_c − γ · N_c · (N_c − 1) / 2 ]
```

**ΔQ ao entrar em c (v ∉ c):**
```
ΔQ = e(v→c) − γ · n_v · N_c
```

**ΔQ ao sair de c (v ∈ c):**
```
ΔQ = −( e(v→c) − γ · n_v · (N_c − n_v) )
```

**Propriedade de independência:** `e(v→c)` não muda quando v entra/sai de uma comunidade
diferente `c'`. Portanto todas as decisões de entrada/saída de v podem ser calculadas
com um único scan de vizinhança e aplicadas sem reavaliação.

**Condição de equilíbrio de Nash:**
```
∀ v, ∀ c :  v ∈ c  →  e(v→c) ≥ γ·(N_c−1)   (sem incentivo para sair)
            v ∉ c  →  e(v→c) ≤ γ·N_c          (sem incentivo para entrar)
```
