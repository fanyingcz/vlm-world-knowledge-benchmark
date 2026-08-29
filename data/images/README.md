# Dataset images

The 329 benchmark images are **not distributed with this repository**.

They were collected from publicly available educational sources, so
redistributing them would raise licensing questions that the author cannot
answer on the sources' behalf. Shipping only the questions keeps the repo small
(~1.5 MB) and puts the focus where it belongs — on the counterfactual question
design, the rubric, and the COT scaffolds.

## Expected layout

If you have the images, place them here (or point `VLM_BENCH_IMAGE_DIR` at any
directory with this layout):

```
data/images/
├── 物理/          # 131 images
├── 生物/          # 97 images
├── 化学/          # 67 images
└── 安全常识/      # 34 images
```

Filenames must match the `files` field of each unit in `data/*.json`, e.g.
`生物-酶的活性.jpg`.

```bash
export VLM_BENCH_IMAGE_DIR=/path/to/your/images
```

## Why the questions alone are still useful

Every unit carries everything needed to understand and reuse the design:

- `pre_question` / `pre_answer` — the world-knowledge probe
- `questions` — the counterfactual variants
- `question_type` — 简答题 / 选择题 / 判断题
- `answers` — reference answers
- `core` — the knowledge point the judge scores against
- `COT` — the human-written reasoning scaffold

You can re-collect images, substitute your own, or run the benchmark on a
different image set entirely — the methodology is what transfers.
