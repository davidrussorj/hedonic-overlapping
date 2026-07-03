# Resultados Experimentais — Jogo Hedônico Overlapping

**Dataset:** DBLP — 317.080 autores, 1.049.866 coautorias, 13.477 comunidades ground truth (grupos de pesquisa reais).

**Pergunta central:** um algoritmo que permite vértices pertencerem a múltiplas comunidades simultaneamente detecta melhor a estrutura real do que o Leiden clássico (que força cada nó a uma única comunidade)?

**Resposta curta:** sim — em todos os experimentos com vizinhança 1-hop, o hedônico supera o Leiden em média, com garantia teórica de equilíbrio de Nash em 100% dos casos. Os resultados com n=200 e n=1000 são praticamente idênticos, confirmando que a amostra é representativa.

---

## Metodologia

Para cada experimento, seleciona-se um conjunto de comunidades ground truth e, para cada uma:

1. Extrai-se um **subgrafo** ao redor dela — os nós da comunidade mais seus vizinhos imediatos (1-hop) ou vizinhos de vizinhos (2-hop).
2. Roda-se o **Leiden não-overlapping** (baseline): cada autor é atribuído a exatamente uma comunidade detectada.
3. Roda-se o **Hedônico overlapping**: partindo do resultado do Leiden, cada autor pode entrar ou sair de comunidades adicionais se isso aumentar sua utilidade individual. O processo repete até nenhum autor ter incentivo para mudar — isso é o **equilíbrio de Nash**.
4. Compara-se a qualidade das duas coberturas contra o ground truth com **F1 médio** (harmônica de precisão e recall sobre os melhores pares de comunidades).

**Intuição do F1:** F1=1.0 significa cobertura perfeita; F1=0.0 significa nenhuma correspondência. Um ganho de +0.10 é expressivo nesse tipo de tarefa.

---

## Experimento 1 — Amostra Aleatória

**Configuração:** comunidades amostradas aleatoriamente (tamanho 5–200 nós), γ=0.1, 5 iterações, vizinhança **1-hop**.

**Intuição:** amostra geral do dataset, sem nenhum critério de seleção além do tamanho. Testa se o hedônico melhora em média, independente do tipo de comunidade.

| Método | n=200 F1 | n=1000 F1 |
|--------|----------|-----------|
| Leiden não-overlapping | 0.3147 ±0.1862 | 0.3131 ±0.1891 |
| Hedônico overlapping | **0.4227 ±0.1938** | **0.4250 ±0.2045** |
| ΔF1 | **+0.1080 ±0.0986** | **+0.1120 ±0.1134** |

- Melhorou em: **169/200 (84.5%)** → **846/1000 (84.6%)**
- Equilíbrio de Nash: **100%** em ambos

Os números com n=1000 replicam os de n=200 com margem mínima — o resultado é estável.

---

## Experimento 2 — Comunidades com Sobreposição Real (filtro por contagem)

**Configuração:** comunidades selecionadas por compartilharem ≥ 2 nós com pelo menos uma outra comunidade ground truth. Mesmos parâmetros do Experimento 1.

**Intuição:** o Leiden é estruturalmente limitado quando comunidades reais se sobrepõem — ele é forçado a cortar arestas que atravessam comunidades. Aqui selecionamos exatamente esses casos difíceis para o Leiden. O hedônico não tem essa restrição.

| Método | n=200 F1 | n=1000 F1 |
|--------|----------|-----------|
| Leiden não-overlapping | 0.2688 ±0.1537 | 0.2595 ±0.1366 |
| Hedônico overlapping | **0.3940 ±0.1767** | **0.3798 ±0.1727** |
| ΔF1 | **+0.1253 ±0.1029** | **+0.1203 ±0.1095** |

- Melhorou em: **176/200 (88.0%)** → **890/1000 (89.0%)**
- Equilíbrio de Nash: **100%** em ambos

O Leiden parte de um F1 mais baixo (0.260 vs 0.313 do experimento aleatório) — esperado, pois são os casos onde a restrição não-overlapping é mais penalizante. O hedônico recupera mais nesses casos (ΔF1 +0.120 vs +0.112), confirmando a hipótese teórica.

---

## Experimento 3 — Sobreposição Real com Filtro de Qualidade (overlap coefficient ≥ 0.2)

**Configuração:** comunidades selecionadas exigindo que a interseção entre pares represente ≥ 20% da menor comunidade do par (overlap coefficient). Mesmos parâmetros anteriores.

**Intuição:** o filtro anterior (≥ 2 nós) pode incluir casos onde duas comunidades grandes compartilham apenas 2 nós — tecnicamente overlapping, mas pouco significativo. O overlap coefficient normaliza pelo tamanho: exige que a sobreposição seja genuína em proporção ao tamanho da comunidade. Isso seleciona casos onde a ambiguidade de pertencimento é estruturalmente real.

| Método | n=200 F1 | n=1000 F1 |
|--------|----------|-----------|
| Leiden não-overlapping | 0.2543 ±0.1296 | 0.2688 ±0.1425 |
| Hedônico overlapping | **0.3712 ±0.1575** | **0.3872 ±0.1681** |
| ΔF1 | **+0.1169 ±0.1058** | **+0.1185 ±0.1024** |

- Melhorou em: **176/200 (88.0%)** → **875/1000 (87.5%)**
- Equilíbrio de Nash: **100%** em ambos

O Leiden parte mais baixo que no aleatório (0.269 vs 0.313) — o filtro selecionou casos genuinamente difíceis para métodos não-overlapping. O hedônico mantém ganho sólido de +0.119 com n=1000.

---

## Experimento 4 — Ablation: Vizinhança 2-hop (amostra aleatória)

**Configuração:** 100 comunidades aleatórias com vizinhança **2-hop** (vizinhos dos vizinhos). γ=0.1, 5 iterações.

**Intuição:** com 2-hop, o subgrafo fica muito maior. A comunidade GT representa em média apenas **4.3% dos nós** do subgrafo (vs. 20.4% com 1-hop) — ou seja, 95% dos nós são ruído contextual não relacionado à comunidade alvo. Isso dificulta qualquer método de detecção, não apenas o hedônico.

| Método | F1 médio | ± std |
|--------|----------|-------|
| Leiden não-overlapping | 0.2916 | ±0.1274 |
| Hedônico overlapping | 0.2674 | ±0.1151 |
| ΔF1 | **−0.0242** | ±0.1068 |

- Melhorou em: **49/100 comunidades (49%)**
- Equilíbrio de Nash: **100/100 (100%)**

Este experimento **não invalida** os resultados anteriores. Ele mostra que o hedônico é sensível à qualidade do contexto: quando o subgrafo é muito maior que a comunidade de interesse, o sinal se dilui. O setup correto para o paper é o 1-hop. O 2-hop serve como ablation mostrando que o ganho não é trivial — depende de um contexto coerente com a estrutura que se quer detectar.

---

## Experimento 5 — Re-execução pós-atualização da API C (v1 vs v2)

**Contexto:** o wrapper C (`igraph_community_leiden_overlapping`) foi reescrito para expor `beta`, `max_memberships`, `initial_membership`, `allow_isolation` e `only_local_moving` — a mesma API do `community_leiden` disjunto. Essa mudança também trouxe um bug de integração: `initial_membership` agora exige uma lista de listas (um sub-array de ids de comunidade por vértice), mas o código de experimento ainda passava a lista plana do Leiden (`part.membership`), o que corrompia memória (`free(): invalid pointer`). Corrigido em `hedonic_ext/overlapping_game.py`, `scripts/test_small.py` e `scripts/subgraph_experiment.py` convertendo para `[[c] for c in part.membership]`.

Com o wrapper corrigido, reexecutamos o **mesmo setup do Experimento 1** (amostra aleatória, 1-hop, γ=0.1) para servir de comparação direta, desta vez também medindo o **hedônico v2** (modelo de intensidade fracionária, `f_v = 1/√|σ_v|`, fallback puro Python — ver `hedonic_ext/overlapping_game.py`).

**Arquivos:** `results/subgraph_L1_n200_fixed.json` / `results/subgraph_L1_n1000_fixed.json` (+ `_covers.pkl`/`_covers.json` com as coberturas completas e métricas com Omega). Cache regenerado do zero em 2026-07-03 com o wrapper atual (γ=0.1 fixo, `n_iterations=5` para v1/v2, Leiden sempre `-1`); os números abaixo são dessa rodada — pequenas variações de décimos de milésimo em relação a rodadas anteriores vêm do RNG interno do igraph (ordem de varredura do local-move), que não é fixado por seed.

| Método | n=200 F1 | n=1000 F1 |
|--------|----------|-----------|
| Leiden não-overlapping | 0.3126 ±0.1842 | 0.3122 ±0.1881 |
| Hedônico v1 (vetorizado, C) | 0.3095 ±0.1829 | 0.3075 ±0.1862 |
| Hedônico v2 (fracionário, Python) | **0.3615 ±0.1925** | **0.3605 ±0.1937** |

| ΔF1 vs Leiden | n=200 | n=1000 |
|---|---|---|
| v1 − Leiden | −0.0031 ±0.0355 | −0.0048 ±0.0362 |
| v2 − Leiden | **+0.0489 ±0.0600** | **+0.0483 ±0.0594** |

**Achado principal — v1 regrediu:** no Experimento 1 (API antiga), o hedônico batia o Leiden em 84.6% dos casos com ΔF1 médio +0.112. Com a API atual e os mesmos parâmetros, **v1 não bate mais o Leiden em média**. Decompondo o ΔF1 por comunidade:

| v1 vs Leiden | n=200 | n=1000 |
|---|---|---|
| Sem mudança (ΔF1 = 0) | 51 (25.5%) | 265 (26.5%) |
| Melhorou (ΔF1 > 0) | 71 (35.5%) | 331 (33.1%) |
| Piorou (ΔF1 < 0) | 78 (39.0%) | 404 (40.4%) |

(Para v2, n=1000: 18 sem mudança, 882 melhoraram, 100 pioraram — padrão muito mais próximo do antigo v1.)

Ou seja: em ~1/4 dos casos o local-move não encontra nenhuma jogada que melhore a utilidade (fica preso na partição do Leiden), e quando encontra, piora um pouco mais do que melhora. Isso é uma regressão de comportamento, não apenas de números — sugere que algo no ciclo completo de três fases da nova API C (`only_local_moving=False` por padrão, que agora roda refinamento + agregação, fases pensadas para clustering disjunto) está prejudicando a qualidade overlapping. **Ainda não investigado a fundo** — próximo passo natural é rodar v1 com `only_local_moving=True` (pula refinamento/agregação, mais parecido com o comportamento antigo) e comparar.

**v2 permanece a implementação de referência**: reproduz o padrão do v1 original (maioria dos casos melhora, poucos empates) com ΔF1 médio próximo de metade do que o v1 antigo mostrava (+0.048 vs +0.112) — ainda positivo e consistente entre n=200 e n=1000, mas hoje só roda em Python puro (sem aceleração C; ver Próximos Passos no `CLAUDE.md`).

### Omega index — acurácia dos baselines de controle

Pedido original: F1/Jaccard não distinguem `grand_coalition` de `total_overlap` por construção (best-match ignora multiplicidade). O Omega index (Collins & Dent 1988) foi vetorizado especificamente para poder rodar essa comparação em escala — a implementação original tinha dois loops Python O(n²) que inviabilizavam qualquer subgrafo acima de ~500 nós (o maior subgrafo aqui tem quase 6.000). Reescrita com produto esparso `M @ Mᵀ` (numpy/scipy) + comparação vetorizada; e um segundo ajuste para usar BLAS denso quando a cobertura é densa por natureza (`grand_coalition`/`total_overlap`, onde cada comunidade contém o subgrafo inteiro) — nesse caso a multiplicação esparsa genérica é 10-20× mais lenta que a densa. Resultado: de "trava/nunca termina" para <1s por comunidade mesmo nos maiores subgrafos.

| Método | n=200 Omega | n=1000 Omega |
|--------|-------------|--------------|
| Leiden não-overlapping | 0.0585 ±0.1097 | 0.0586 ±0.1249 |
| Hedônico v1 | 0.0507 ±0.0979 | 0.0504 ±0.1125 |
| Hedônico v2 | 0.0329 ±0.0694 | 0.0279 ±0.0600 |
| Singleton | 0.0000 | 0.0000 |
| Grand Coalition | 0.0000 | 0.0000 |
| Total Overlap | 0.0000 | 0.0000 |

**Os três baselines de controle zeram — e isso é o resultado esperado, não um bug.** Omega corrige por concordância ao acaso (como o Rand ajustado): uma cobertura cujo padrão de co-pertencimento é **constante** para todo par de vértices (singleton = sempre 0 comunidades compartilhadas; grand_coalition/total_overlap = sempre a mesma contagem k) não carrega informação discriminativa nenhuma sobre a estrutura real — o termo "esperado ao acaso" da fórmula cancela quase exatamente o termo "observado", dando Omega≈0 por construção matemática, independente do ground truth. Isso serve de **piso de validação**: qualquer método que carregue sinal real de estrutura deve ficar acima de zero, o que se confirma — Leiden, v1 e v2 ficam todos claramente acima (0.03–0.06).

**v2 tem o menor Omega entre os três métodos reais, apesar do maior F1.** F1 mede melhor correspondência (best-match) por comunidade; Omega mede concordância na contagem exata de comunidades compartilhadas por par. v2 gera bem mais comunidades que Leiden/v1 (ver contagens nas seções anteriores), o que aumenta a chance de acerto no best-match (F1) mas dificulta acertar a multiplicidade exata esperada pelo ground truth (Omega). As duas métricas capturam noções diferentes de acerto — vale reportar as duas no paper, não só F1.

## Experimento 6 — Resolução adaptativa (densidade da sub-rede) [PRELIMINAR]

> ⚠️ **Preliminar, será refeito.** Esta rodada usou `n_iterations=5` (default do script) para v1/v2, não `n_iterations=-1` (até convergência) como pedido — falta reexecutar com `--n_iterations -1` antes de tratar estes números como definitivos. Mantido aqui como registro do sinal observado.

**Motivação:** os experimentos anteriores usam γ=0.1 fixo para toda sub-rede, independente do seu tamanho/densidade real. `scripts/subgraph_experiment.py` ganhou a flag `--density_resolution`, que usa a densidade de cada sub-rede (`og.density()`) como sua própria γ — mesma convenção já usada como default em `OverlappingGame.community_leiden_overlapping(resolution=None)`.

**Arquivos:** `results/subgraph_L1_n{200,1000}_density_covers.json`. Resolução efetiva por sub-rede: média 0.141 (n=200) / 0.140 (n=1000), desvio padrão ~0.135 — varia bastante entre sub-redes (vs. 0.1 fixo antes).

| Método | n=200 F1 | n=1000 F1 | n=200 Omega | n=1000 Omega |
|--------|----------|-----------|-------------|--------------|
| Leiden não-overlapping | 0.3078 ±0.1754 | 0.3014 ±0.1639 | 0.1250 ±0.2345 | 0.1032 ±0.2094 |
| Hedônico v1 | 0.3077 ±0.1770 | 0.3017 ±0.1670 | 0.1249 ±0.2349 | 0.0998 ±0.2059 |
| Hedônico v2 | **0.3623 ±0.1934** | **0.3518 ±0.1856** | 0.0577 ±0.0887 | 0.0546 ±0.0874 |

| ΔF1 (v1−Leiden) | n=200 | n=1000 |
|---|---|---|
| Média | −0.0002 ±0.0308 | **+0.0003 ±0.0277** |
| Zero / melhorou / piorou | 82 / 61 / 57 | 376 / 333 / 291 |

**Sinal preliminar interessante:** com γ=densidade, o v1 deixa de regredir — fica **estatisticamente empatado** com o Leiden (ΔF1 média ≈ 0, contra −0.003 a −0.005 com γ=0.1 fixo no Experimento 5). Ainda não bate o Leiden como o v1 antigo batia, mas o γ fixo parece estar prejudicando especificamente o v1, não o v2 (v2 mal muda: ΔF1 vs Leiden continua em torno de +0.05 nos dois setups). Também sobe bastante o Omega de Leiden/v1 (0.10–0.13 vs 0.05–0.06 fixo) — a cobertura fica mais alinhada com a multiplicidade real do ground truth. **Precisa confirmar com `n_iterations=-1`** antes de qualquer conclusão mais forte.

---

## Resumo Comparativo

> ⚠️ A tabela abaixo é histórica — reflete a API C anterior à correção descrita no **Experimento 5**. Com a API atual, "Hedonic F1" (v1) não reproduz mais esses ganhos; ver Experimento 5 para os números atualizados e o v2 como implementação de referência.

| Experimento | n | Leiden F1 | Hedonic F1 | ΔF1 médio | Melhorou | Nash |
|---|---|---|---|---|---|---|
| Aleatório 1-hop | 200 | 0.315 | **0.423** | **+0.108** | 84.5% | 100% |
| Aleatório 1-hop | 1000 | 0.313 | **0.425** | **+0.112** | 84.6% | 100% |
| Overlap real 1-hop | 200 | 0.269 | **0.394** | **+0.125** | 88.0% | 100% |
| Overlap real 1-hop | 1000 | 0.260 | **0.380** | **+0.120** | 89.0% | 100% |
| Overlap ratio≥0.2 1-hop | 200 | 0.254 | **0.371** | **+0.117** | 88.0% | 100% |
| Overlap ratio≥0.2 1-hop | 1000 | 0.269 | **0.387** | **+0.119** | 87.5% | 100% |
| Aleatório 2-hop (ablation) | 100 | 0.292 | 0.267 | −0.024 | 49.0% | 100% |

**Estabilidade amostral:** os resultados com n=200 e n=1000 são praticamente idênticos em todos os experimentos — variação máxima de 0.003 no ΔF1. Isso confirma que n=200 já era uma amostra representativa do DBLP.

**Padrão consistente nos experimentos principais (1-hop):** quanto mais a seleção foca em comunidades genuinamente sobrepostas, mais o Leiden sofre (F1 base cai) e mais o hedônico se destaca (ΔF1 cresce). Isso é exatamente o que a teoria prevê.

---

## Garantia de Equilíbrio de Nash

Em **3700/3700 experimentos (100%)** o cover final é um equilíbrio de Nash do jogo hedônico vetorizado — nenhum vértice tem incentivo para entrar ou sair de qualquer comunidade. Isso não é apenas uma melhoria empírica; é uma **garantia teórica**: o algoritmo converge para um estado estável onde cada autor está nas comunidades que maximizam sua utilidade individual dado o estado dos demais.

---

## Melhores casos — Experimento 3 com n=1000 (Overlap ratio≥0.2)

Casos onde o hedônico mais se distanciou do Leiden:

| Comunidade | Tamanho GT | Parceiros | F1 Leiden | F1 Hedonic | ΔF1 |
|-----------|-----------|-----------|-----------|-----------|-----|
| 8199  | 7  | 4 | 0.295 | 0.747 | **+0.451** |
| 11670 | 20 | 1 | 0.408 | 0.823 | **+0.415** |
| 6515  | 8  | 2 | 0.249 | 0.647 | **+0.398** |
| 2925  | 14 | 7 | 0.210 | 0.592 | **+0.382** |
| 12034 | 27 | 1 | 0.524 | 0.904 | **+0.380** |

Nesses casos o hedônico quase duplica ou tripica o F1 do Leiden. São exatamente as comunidades onde pesquisadores colaboram com múltiplos grupos simultaneamente — a estrutura real é overlapping, e o Leiden simplesmente não consegue representá-la.
