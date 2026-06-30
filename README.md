# Detecção de Comunidades Overlapping via Jogo Hedônico Vetorizado

Extensão do algoritmo Leiden baseado em CPM para detectar comunidades **overlapping**
usando uma decomposição de teoria dos jogos. Cada vértice decide independentemente
se entra ou sai de cada comunidade; o delta de utilidade individual é igual ao delta
de qualidade global (CPM), preservando as garantias teóricas do jogo hedônico.

---

## Fundamentação Teórica

### Baseline não-overlapping (trabalho existente)

A qualidade CPM (*Constant Potts Model*) de uma partição é:

```
Q = (1/2m) · Σ_c [ e_c − γ · N_c² ]
```

onde `e_c` = peso de arestas internas, `N_c` = tamanho ponderado da comunidade, `γ` = resolução.

A decomposição hedônica mostra que o ganho ao mover o vértice `v` para a comunidade `c`
é igual à variação de `Q`:

```
ΔQ = Δvalor_hedônico(v)
```

### Jogo hedônico vetorizado (este trabalho)

Para comunidades overlapping, cada vértice `v` mantém um **vetor** de memberships.
A qualidade CPM overlapping é:

```
Q = (1/2m) · Σ_c [ e_c − γ · C(N_c, 2) ]
```

onde uma aresta contribui para `e_c` somente se **ambos** os seus extremos estão em `c`.

Para cada par `(v, c)` de forma independente:

| Condição | Fórmula | Decisão |
|----------|---------|---------|
| `v ∉ c`  | `ΔQ = deg(v,c) − γ · N_c` | entra se `> 0` |
| `v ∈ c`  | `ΔQ = −(deg(v,c) − γ · (N_c−1))` | sai se `> 0` |

onde `deg(v,c)` = soma dos pesos das arestas de `v` para outros membros de `c`.

**Propriedade central:** os ganhos são independentes entre comunidades, então todas as
decisões de entrada/saída de um vértice podem ser calculadas com um único scan de
vizinhança e aplicadas atomicamente — a convergência é garantida pois todo move aumenta Q estritamente.

Um cover é um **equilíbrio de Nash** do jogo hedônico vetorizado se e somente se
nenhum vértice quer entrar ou sair de nenhuma comunidade.

---

## Estrutura do Repositório

```
hedonic-overlapping/
│
├── c_patch/
│   └── leiden_overlapping.c        # Novas funções C para anexar ao leiden.c
│                                   # (3 funções, 492 linhas)
│
├── python_patch/
│   └── community_overlapping.py    # Wrapper Python + guia do graphobject.c
│
├── hedonic_ext/
│   └── overlapping_game.py         # Classe OverlappingGame (495 linhas)
│
├── scripts/
│   ├── test_small.py               # Validação em grafos pequenos
│   ├── dblp_experiment.py          # Experimento sweep no DBLP completo (317k nós)
│   └── subgraph_experiment.py      # Experimento em sub-redes L-hop (recomendado)
│
└── README.md
```

---

## Instalação

### Pré-requisitos

- Python ≥ 3.10
- `lucas-igraph` — fork do igraph com parâmetros extras no Leiden
  (`only_local_moving`, `allow_isolation`)
- `hedonic` — biblioteca do jogo hedônico (fork lucaslopes)

### Passo a passo

```bash
# 1. Instalar o lucas-igraph (o fork, não o igraph padrão)
pip install lucas-igraph

# 2. Instalar a biblioteca hedonic
pip install git+https://github.com/lucaslopes/hedonic.git

# 3. Re-fixar o lucas-igraph (o setup.py do hedonic instala o igraph padrão por cima)
pip install lucas-igraph --force-reinstall

# 4. Instalar o OverlappingGame dentro do pacote hedonic
cp hedonic_ext/overlapping_game.py \
   $(python -c "import hedonic; import os; print(os.path.dirname(hedonic.__file__))")/overlapping.py
```

Verificar:

```bash
python -c "
import igraph; print('igraph:', igraph.__version__)   # deve ser 0.11.9.x
from hedonic.overlapping import OverlappingGame
print('OverlappingGame: OK')
"
```

Saída esperada:
```
igraph: 0.11.9.3
OverlappingGame: OK
```

---

## Uso Rápido

```python
import random
import igraph as ig
ig.set_random_number_generator(random.Random(42))  # reprodutível

from hedonic.overlapping import OverlappingGame

g = ig.Graph.Famous("Petersen")
og = OverlappingGame(g)

# Detectar comunidades overlapping
cover = og.community_leiden_overlapping(
    resolution=og.density(),   # γ = densidade de arestas do grafo
    n_iterations=-1,           # iterar até convergência
)

cover_lists = list(cover)      # [[v, v, ...], [v, v, ...], ...]
print(f"Comunidades: {len(cover_lists)}")
for i, members in enumerate(cover_lists):
    print(f"  c{i}: {sorted(members)}")

# Qualidade global
q = og.quality_overlapping(cover_lists, resolution=og.density())
print(f"Q = {q:.6f}")

# Verificação do equilíbrio de Nash
eq = og.in_equilibrium_overlapping(cover_lists, resolution=og.density())
print(f"Equilíbrio de Nash: {eq}")

# Comparação com o baseline não-overlapping
p_base = og.community_leiden(resolution=og.density(), n_iterations=-1)
cover_no = [[v for v, c in enumerate(p_base.membership) if c == ci]
            for ci in range(max(p_base.membership) + 1)]
q_no = og.quality_overlapping(cover_no, resolution=og.density())
print(f"Q não-overlapping: {q_no:.6f}")
print(f"ΔQ = {q - q_no:+.6f}")
```

Saída (grafo de Petersen, semente 42):
```
Comunidades: 5
  c0: [0, 1, 4]
  c1: [0, 1, 2]
  c2: [3, 5, 8]
  c3: [5, 7, 8]
  c4: [6, 8, 9]
Q = 0.166667
Equilíbrio de Nash: True
Q não-overlapping: 0.111111
ΔQ = +0.055556  ✓
```

---

## Executando os Testes

```bash
cd hedonic-overlapping
python3.12 scripts/test_small.py
```

O script executa três experimentos:

| Teste | Grafo | O que verifica |
|-------|-------|----------------|
| 1 | Petersen (n=10) | Cover overlapping + equilíbrio de Nash |
| 2 | SBM sintético (n=20, 2 blocos) | F1 / Jaccard / Omega vs. ground truth |
| 3 | Petersen | `Q_overlapping > Q_não_overlapping` |

---

## Experimento DBLP

### Download dos dados

```bash
mkdir -p data/dblp && cd data/dblp
wget https://snap.stanford.edu/data/com-dblp.ungraph.txt.gz
wget https://snap.stanford.edu/data/com-dblp.cmty.txt.gz
```

Estatísticas do dataset: 317.080 nós · 1.049.866 arestas · 13.477 comunidades ground truth.
Fonte: [SNAP — DBLP](https://snap.stanford.edu/data/com-DBLP.html)

### Abordagem recomendada — sub-redes L-hop

Em vez de rodar na rede completa (317k nós), extraímos sub-redes ao redor de cada
comunidade ground truth expandindo L níveis de vizinhos. Isso torna os experimentos
tratáveis e permite comparação direta com a comunidade alvo.

```bash
# Nível 1: comunidade GT + vizinhos diretos (~100–300 nós por sub-rede)
python3.12 scripts/subgraph_experiment.py \
    --data_dir data/dblp \
    --levels 1 \
    --n_communities 100 \
    --resolution 0.1 \
    --output results/subgraph_L1.json

# Nível 2: inclui amigos de amigos (~500–2000 nós)
python3.12 scripts/subgraph_experiment.py \
    --data_dir data/dblp \
    --levels 2 \
    --n_communities 100 \
    --resolution 0.1 \
    --output results/subgraph_L2.json
```

### Resultados obtidos (20 comunidades, γ=0.1, levels=1)

| Método | F1 médio | Jaccard médio |
|--------|----------|---------------|
| Leiden não-overlapping | 0.3452 | — |
| **Hedônico overlapping** | **0.4236** | — |
| **ΔF1** | **+0.0784** | — |

O algoritmo overlapping melhora em **16/20 comunidades (80%)**.
Melhor caso: ΔF1 = +0.356 (F1 de 0.43 → 0.79).

### Varredura de resolução na rede completa

```bash
python3.12 scripts/dblp_experiment.py \
    --data_dir data/dblp \
    --resolution_sweep \
    --n_iterations 5 \
    --output results/sweep.json
```

Varre `γ ∈ [0.01, 1.0]` (10 valores em escala logarítmica). Use `n_iterations` baixo
(5–10) para evitar tempo excessivo na rede completa.

### Métricas de saída

| Métrica | Descrição |
|---------|-----------|
| `f1` | F1 macro-average best-match entre o cover predito e o ground truth |
| `jaccard` | Índice de Jaccard macro-average best-match |
| `quality` | Qualidade CPM overlapping Q |
| `n_predicted_comms` | Número de comunidades não-vazias encontradas |

---

## API do OverlappingGame

```python
from hedonic.overlapping import OverlappingGame

og = OverlappingGame(grafo_igraph)
```

### Detecção de comunidades

```python
cover = og.community_leiden_overlapping(
    resolution=0.0001,          # γ — maior → comunidades menores e mais densas
    n_iterations=-1,            # -1 = até convergência; positivo = número fixo
    initial_membership=None,    # list[int] — partição inicial; None = roda Leiden primeiro
    weights=None,               # list[float] ou nome do atributo de aresta
)
# retorna igraph.VertexCover
cover_lists = list(cover)       # converte para lista de listas
```

### Qualidade

```python
q = og.quality_overlapping(
    cover=cover_lists,          # lista de listas de ids de vértices
    resolution=0.0001,
    weights=None,
)
# retorna float
```

### Equilíbrio de Nash

```python
eq = og.in_equilibrium_overlapping(
    cover=cover_lists,
    resolution=0.0001,
)
# retorna bool
```

### Avaliação vs. ground truth

```python
metrics = OverlappingGame.evaluate_cover(
    predicted=cover_lists,
    ground_truth=gt_cover,      # lista de listas
    n_vertices=g.vcount(),
)
# retorna dict: {'f1', 'jaccard', 'omega', 'n_predicted_comms', 'n_gt_comms'}
```

### Valor hedônico individual

```python
h = og.hedonic_value_overlapping(
    v=5,                        # id do vértice
    c_members={0, 1, 2, 5},    # membros atuais da comunidade c
    c_idx=2,                    # índice da comunidade
    resolution=0.0001,
)
# positivo → v quer ficar / entrar; negativo → v quer sair / não entrar
```

---

## Roteiro de Implementação ✅

Todas as fases estão concluídas.

### Fase 1 — Python Puro ✅

`hedonic_ext/overlapping_game.py` — `OverlappingGame._community_leiden_overlapping_python()`

Implementação de referência em Python puro. Valida a lógica em grafos pequenos
sem compilação C. Funciona como fallback automático quando o backend C não está disponível.

### Fase 2 — Biblioteca C ✅

**Repositório:** `davidrussorj/igraph` · **Branch:** `overlapping`

Três funções adicionadas ao final de `src/community/leiden.c`:

| Função | Papel |
|--------|-------|
| `igraph_i_community_leiden_overlapping_quality` | Calcula Q overlapping |
| `igraph_i_community_leiden_overlapping_fastmove` | Local-move com fila de vértices instáveis |
| `igraph_community_leiden_overlapping` | API pública |

### Fase 3 — Wrapper Python ✅

**Repositório:** `davidrussorj/python-igraph` · **Branch:** `lucas`

- `src/_igraph/graphobject.c` — expõe a função C ao Python
- `src/igraph/community.py` — wrapper que retorna `VertexCover`
- `src/igraph/__init__.py` — registra o método no objeto `Graph`

### Fase 4 — Validação no DBLP ✅

Experimento de subgrafos L-hop obteve ΔF1 médio de +0.078 (16/20 comunidades melhoram).
Ver seção [Experimento DBLP](#experimento-dblp).

---

## Decisões de Design

**Por que não tem fase de refinamento/agregação?**
As fases 2 (refinamento) e 3 (agregação) do Leiden original constroem um grafo
quociente hierárquico, o que pressupõe uma partição não-overlapping em cada nível.
Estender essas fases para memberships overlapping requer uma formulação diferente
(ex: agregação bipartida ponderada) e é deixado como trabalho futuro. A fase de
local-move sozinha é suficiente para provar a decomposição hedônica e validar no DBLP.

**Por que partir do resultado do Leiden não-overlapping?**
Partir de uma boa partição não-overlapping e "abrir" para overlapping é mais rápido
e produz resultados melhores do que começar de singletons, porque as comunidades
iniciais já têm boa densidade interna. A fase overlapping então refina os vértices
nas fronteiras das comunidades.

**Por que os ganhos são independentes entre comunidades?**
`deg(v, c)` (peso de arestas de `v` para membros de `c`) não muda quando `v` entra
ou sai de uma comunidade *diferente* `c'`. Portanto, todas as decisões de entrada/saída
do vértice `v` podem ser calculadas com um único scan de vizinhança, e os moves são
aplicados sem re-avaliação.

---

## Repositórios Relacionados

| Repositório | Branch | Descrição |
|-------------|--------|-----------|
| [davidrussorj/igraph](https://github.com/davidrussorj/igraph/tree/overlapping) | `overlapping` | Fork da biblioteca C com `igraph_community_leiden_overlapping` |
| [davidrussorj/python-igraph](https://github.com/davidrussorj/python-igraph/tree/lucas) | `lucas` | Fork do wrapper Python com o método exposto ao Python |
| [lucaslopes/hedonic](https://github.com/lucaslopes/hedonic) | — | Biblioteca hedonic game (base da classe `OverlappingGame`) |

---

## Referências

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
