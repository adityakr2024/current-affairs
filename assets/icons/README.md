# Topic Icon Assets

Drop your icon files here. The system loads them automatically.

## File naming

| Topic | Filename |
|-------|----------|
| Polity & Governance | polity.png |
| International Relations | international.png |
| Economy | economy.png |
| Geography & Environment | environment.png |
| Science & Technology | science.png |
| Health & Social Issues | health.png |
| Defence & Security | defence.png |
| Agriculture & Rural | agriculture.png |
| Infrastructure | infrastructure.png |
| Schemes & Initiatives | schemes.png |
| History & Culture | culture.png |
| Prelims Special | prelims.png |
| Any topic (catch-all) | default.png |

## Specifications

- **Format**: PNG (preferred, supports transparency) or JPG or SVG
- **Size**: 300×300px minimum (circle is 210px — bigger is fine, system scales down)
- **Background**: Transparent PNG looks best — the topic colour shows behind the icon
- **SVG**: Supported if `cairosvg` is installed (`pip install cairosvg`)

## How it works

1. System looks for `assets/icons/<filename>` matching the article's UPSC topic
2. If found: loads it, composites onto topic-coloured background, places in circle
3. If missing: falls back to the built-in PIL geometric drawing (scales, globe, etc.)

## Where to find good icons

- https://www.svgrepo.com — thousands of free SVG icons
- https://flaticon.com — PNG icons (check license)
- https://icons8.com — PNG/SVG icons
- Search: "supreme court icon svg", "wheat icon svg", "atom icon svg" etc.

## Quick test

After adding an icon, run:
```bash
python3 -c "
import sys; sys.path.insert(0, '.')
import os; os.environ['OUTPUT_DIR'] = '/tmp/test_icon'
from generators.social_builder import build_social_post
from pathlib import Path
art = {'_id':'t1','title':'Test','upsc_topics':['Economy'],
       'gs_paper':'GS3','headline_social':'Test headline',
       'context_social':'Test context.','key_points':['Point one'],
       'policy_implication':'Test.','fact_confidence':4,'fact_flags':[],
       'article_image_url':'','_article_img':None}
p = build_social_post(art)
print(p)
"
```
