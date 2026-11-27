# Predicates

The machine-readable source is `references/relation-vocabulary.json`. The relation must be interpreted as:

```text
subject -> relation -> object
```

The default narrowest-relation policy is:

| Relation | Use when | Do not use when |
|---|---|---|
| `increases` | Subject raises the object's value or rate | Evidence shows no change or only association |
| `decreases` | Subject lowers the object's value or rate | Direction is not reported |
| `no_change` | Source explicitly reports no detected change | Only a missing result or nonsignificant secondary endpoint |
| `associates_with` | Association without causal support | Randomized or mechanistic causal evidence is explicit |
| `causes` | Source directly supports a causal effect | Evidence says `associated with`, `may`, `suggests` or similar |
| `enables` | Subject makes an object possible or operational | Subject merely mentions the object |
| `inhibits` | Subject reduces activity, growth or function | Subject reduces a numerical biomarker without an inhibition claim |
| `predicts` | Source reports prediction or predictive performance | Source reports only a concurrent correlation |
| `outperforms` | Subject performs better on a stated metric and baseline | Baseline or metric is absent |
| `equivalent_to` | Source reports equivalence under stated criteria | The study merely failed to detect a difference |
| `measured_as` | Source reports a measured value or estimate | Value is inferred from a chart without a readable label |
| `observed_in` | Subject is observed in a stated population or setting | The population is guessed from the paper's topic |
| `requires` | Source reports a prerequisite or dependency | Reverse implication is not directly stated |
| `produces` | Subject yields or generates the object | Subject only uses the object |
| `uses_method` | Subject uses the object as a method or instrument | Method is merely cited, not used |
| `validates` | Source reports validation in the stated direction | Validation target or metric is unclear |
| `contradicts` | Sources or claims conflict in a stated way | Difference is only a scope or measurement distinction |
| `limited_to` | Conclusion is explicitly restricted to a scope | Scope is added by the extractor |
| `not_reported` | Source does not report the requested quantity or relation | Source reports a negative experimental result |
| `uncertain` | Source is insufficient, ambiguous or conflicting | A clear result exists but is inconvenient |
| `other` | A scientific relation outside this vocabulary fits | `relation_detail` is missing |

## Direction and scope rules

- Preserve passive-to-active direction only when the result is explicit.
- Keep the comparator for `outperforms`, `equivalent_to` and comparative claims.
- Keep dose, time, population, model, assay and condition qualifiers.
- Do not turn `not_reported` into `no_change`.
- Do not turn `associates_with` into `causes`.
- If a relation is missing from the table, use `other` with a precise `relation_detail` and mark the semantic review boundary.
