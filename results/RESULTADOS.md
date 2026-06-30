# Resultados Experimentais — Jogo Hedônico Overlapping

Dataset: DBLP (317.080 autores, 1.049.866 coautorias, 13.477 comunidades ground truth)
Metodologia: sub-redes L-hop ao redor de comunidades ground truth selecionadas

---

## Experimento 1 — Amostra Aleatória

**Configuração:** 200 comunidades amostradas aleatoriamente (tamanho 5–200 nós), γ=0.1, 5 iterações, vizinhança 1-hop.

| Método | F1 médio | ± std |
|--------|----------|-------|
| Leiden não-overlapping | 0.3147 | ±0.1862 |
| Hedônico overlapping | **0.4227** | ±0.1938 |
| ΔF1 | **+0.1080** | ±0.0986 |

- Melhorou em: **169/200 comunidades (84.5%)**
- Equilíbrio de Nash: **200/200 (100%)**

---

## Experimento 2 — Comunidades com Sobreposição Real

**Configuração:** 200 comunidades selecionadas por possuírem ≥ 2 nós compartilhados com pelo menos uma outra comunidade ground truth. Mesmos parâmetros do Experimento 1.

Média de 20.3 parceiros GT por comunidade, com 97.2 nós compartilhados em média.

| Método | F1 médio | ± std |
|--------|----------|-------|
| Leiden não-overlapping | 0.2688 | ±0.1537 |
| Hedônico overlapping | **0.3940** | ±0.1767 |
| ΔF1 | **+0.1253** | ±0.1029 |

- Melhorou em: **176/200 comunidades (88.0%)**
- Equilíbrio de Nash: **200/200 (100%)**

---

## Comparação entre experimentos

| | Aleatório | Overlapping real |
|---|---|---|
| F1 Leiden | 0.315 | 0.269 |
| F1 Hedonic | 0.423 | 0.394 |
| ΔF1 médio | +0.108 | **+0.125** |
| Melhorou em | 84.5% | **88.0%** |
| Nash eq | **100%** | **100%** |

O Leiden parte de um F1 mais baixo nas comunidades com sobreposição real (0.269 vs 0.315) — esperado, pois são exatamente os casos onde a restrição não-overlapping é mais limitante. O algoritmo hedônico recupera mais nesses casos (ΔF1 +0.125 vs +0.108), confirmando a hipótese teórica.

---

## Experimento 3 — Sobreposição com Coeficiente Mínimo (ratio ≥ 0.2)

**Configuração:** 200 comunidades com interseção ≥ 20% do tamanho da menor comunidade do par. Garante sobreposição significativa independente do tamanho.

| Método | F1 médio |
|--------|----------|
| Leiden não-overlapping | 0.2543 |
| Hedônico overlapping | **0.3712** |
| ΔF1 | **+0.1169** |

- Melhorou em: **178/200 comunidades (89.0%)**
- Equilíbrio de Nash: **200/200 (100%)**

---

## Experimento 4 — Vizinhança 2-hop (L=2)

**Configuração:** 100 comunidades aleatórias com sub-redes expandidas 2 níveis de vizinhos.

| Método | F1 médio |
|--------|----------|
| Leiden não-overlapping | 0.2916 |
| Hedônico overlapping | 0.2674 |
| ΔF1 | **-0.0242** |

- Melhorou em: **49/100 comunidades (49.0%)**
- Equilíbrio de Nash: **100/100 (100%)**

**Interpretação:** com sub-redes maiores (2-hop), o algoritmo tem mais comunidades para gerenciar e o ruído supera o ganho do overlap. O nível 1-hop é o contexto ótimo para este dataset.

---

## Resumo geral

| Experimento | n | L | Seleção | ΔF1 médio | Melhorou | Nash |
|-------------|---|---|---------|-----------|----------|------|
| Aleatório | 200 | 1 | aleatória | +0.108 | 84.5% | **100%** |
| Overlapping real | 200 | 1 | ≥2 nós compartilhados | +0.125 | 88.0% | **100%** |
| Overlap ratio | 200 | 1 | ratio ≥ 0.2 | +0.117 | 89.0% | **100%** |
| 2-hop | 100 | 2 | aleatória | -0.024 | 49.0% | **100%** |

---

## Garantia de Equilíbrio de Nash

Em **700/700 experimentos (100%)** o cover final é um equilíbrio de Nash do jogo hedônico vetorizado — nenhum vértice tem incentivo para entrar ou sair de qualquer comunidade. Isso confirma empiricamente a garantia teórica central do modelo.

---

## Melhores casos (Experimento 2)

| Comunidade | Tamanho GT | Parceiros | F1 Leiden | F1 Hedonic | ΔF1 |
|-----------|-----------|-----------|-----------|-----------|-----|
| 8696 | 21 | 2 | 0.388 | 0.787 | +0.399 |
| 12034 | 27 | 1 | 0.524 | 0.900 | +0.376 |
| 1870 | 6 | 1 | 0.271 | 0.606 | +0.335 |
| 862 | 11 | 7 | 0.203 | 0.528 | +0.325 |
| 10540 | 7 | 2 | 0.271 | 0.593 | +0.322 |
