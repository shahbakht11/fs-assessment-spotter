# Manual test cases

Run the app (`npm run dev` in `frontend/`, `manage.py runserver` in `backend/`) and open
http://localhost:5173. Weather is a live forecast, so exact risk levels vary from day to day. The
expected results below are what must hold whatever the weather is. The fixed rule checks (risk table,
load rules, ranking) are automated in `backend/planner/tests/test_assessment_spec.py`.

## A. Inputs (brief: origin & destination, departure, load weight)

| # | Steps | Expected |
|---|---|---|
| A1 | Type `New York City` in **From** | Suggestions appear within about a second; **New York, US** (the city) is first. ↑/↓ and Enter select a suggestion. |
| A2 | Clear **To** and type nothing | The button is disabled with the hint "Pick both places from the suggestions". |
| A3 | Make From and To the same city, then submit | Red error: "Origin and destination are the same place." |
| A4 | Type load `90000` | The note turns into "Load must be between 0 and 80,000 lb." and the button is disabled. |
| A5 | Click load chips **Empty → 20k → 35k → 45k** | The meter fills. The note changes from *standard limits* to *45+ mph is No Travel* (35k) to *35–44 mph is Severe, 45+ mph is No Travel* (45k). |
| A6 | Click **Next hour / +6 h / Tomorrow 6 AM** | The departure field updates and the active chip is highlighted. |
| A7 | Click the **⇅** swap button | From and To swap, and the A/B pins on the map swap. |

## B. Three route options

| # | Steps | Expected |
|---|---|---|
| B1 | Sample trip **Chicago → Denver** | 3 route cards (A, B, C) with different roads (e.g. I-80/I-76 and I-70). The map shows the selected route in risk colours and the others dotted. |
| B2 | Sample trip **Seattle → Portland** (short trip) | Still 3 distinct routes. |
| B3 | Plan **New York → Los Angeles** | 3 routes, plus the notice "Truck routing is unavailable for this trip … 65 mph truck speed cap". Multi-day travel times. |
| B4 | Click a dotted route on the map, or a route card | That route becomes selected: risk colours, checkpoints and timeline switch to it. |

## C. Checkpoints every 10 / 25 / 50 miles at the truck's ETA

| # | Steps | Expected |
|---|---|---|
| C1 | Chicago → Denver, Route A (~1,015 mi). Toggle **10 / 25 / 50 mi** and open *All N checkpoints* | Roughly **103 / 42 / 22** checkpoints. Mileposts are 0, 10, 20 … (or 0, 25, 50 … / 0, 50, 100 …), and the last row is the destination. |
| C2 | Same trip, look at the first and last checkpoint ETAs | First ETA = departure time; last ETA = the card's arrival time. ETAs only ever increase. |
| C3 | Look at the trip timeline | 30m and 10h markers after about 8 h and 11 h of driving. Checkpoints after the 10 h marker are ~10 h later than the ones before it. |
| C4 | Turn **Hours-of-service stops** off and re-plan | The rest markers disappear and the arrival is ~10.5 h earlier (≈ 15 h 45 m instead of ≈ 1 d 2 h). |
| C5 | Change **Departure** by +6 h and re-plan | Every ETA shifts by 6 h, and conditions or risk levels can change because a different forecast hour is read. |
| C6 | Hover a checkpoint dot on the map | Tooltip shows mile, ETA, level, wind (gust), rain, snow and temperature, and which condition drove the level. |

## D. Risk & load rules

| # | Steps | Expected |
|---|---|---|
| D1 | In the checkpoint table, compare each row with the brief's table | Wind <25 Low, 25–34 Moderate, 35–44 High, 45–54 Severe, ≥55 No Travel; rain and snow per the table. The row's level is the worst of the three, and the deciding value is highlighted. |
| D2 | Find a windy trip (use the **Wind** heatmap layer and look for yellow/orange). Plan it with **20k**, then **45k** | Where wind is 35–44 mph, checkpoints go from **High** (20k) to **Severe** (45k). Where wind is 45–54 mph, they go from **Severe** to **No Travel** (any load over 30k). |
| D3 | Same trip with **35k** | 35–44 mph stays **High**; 45–54 mph becomes **No Travel**. |

## E. Recommendation (fewest Severe → fewest High → lowest average risk → shortest time)

| # | Steps | Expected |
|---|---|---|
| E1 | Calm-weather trip (e.g. Chicago → Denver) | The fastest route is recommended, and the reason says "Shorter travel time … Tied on No Travel, Severe, High miles and average risk." |
| E2 | Trip through active weather (pick one with colour on the heatmap; New York → Boston has been active) | The recommended route has the fewest Severe miles, even if slower. The reason names the deciding criterion with numbers, e.g. "Fewer High-risk miles than Route B (22 vs 75 mi)". |
| E3 | Compare all three cards for E2 | Ranks #1 → #3 follow the order: Severe+ miles, then High, then avg risk, then time. |
| E4 | Toggle 10 / 25 / 50 mi on E2 | The recommendation may change, because coarser sampling counts different miles. The selected route follows the new recommendation. |
| E5 | A trip where even the best route has Severe | An amber warning: "Even the best route has Severe conditions — drive with caution or delay." |

## F. Map, heatmap & 0–48 h slider

| # | Steps | Expected |
|---|---|---|
| F1 | After planning | The heatmap appears ~1 s after the routes, only in a band around the routes, with soft edges. |
| F2 | Drag the slider from 0 to 48 | The clock label updates (+00h … +48h), the heatmap changes smoothly with no flicker, and the truck markers move along the routes. |
| F3 | Press **▶** | Plays through 48 h in ~12 s and stops at 48. Pressing again restarts from 0. |
| F4 | Hover or click bars in **Worst risk in corridor** | The tooltip shows the hour and worst level; clicking jumps the slider to that hour. |
| F5 | Pick an hour after a **10h** rest starts | The selected route's truck sits still at the rest marker until the rest ends. |
| F6 | Switch **Risk / Wind / Rain / Snow** | The heatmap recolours instantly and the legend title and ticks change (e.g. Wind: 0 / 25 / 35 / 45 / 55+). |
| F7 | Toggle the heatmap switch off | The heatmap hides; routes and labels stay. |
| F8 | Hover the trip timeline, then click it | The tooltip follows the cursor; clicking flies the map to that checkpoint. Clicking a table row does the same. |

## G. Robustness & layout

| # | Steps | Expected |
|---|---|---|
| G1 | Start a plan, then start another before it finishes | Only the second result shows; there's no flicker of the first. |
| G2 | Stop the backend and plan | A readable red error, not a blank screen. |
| G3 | Phone width (DevTools, 390 px) | The map is on top, the forecast controls below it, then the form. No sideways scroll. After planning, the page scrolls up to the map. |
| G4 | Keyboard only | Tab reaches every control, focus rings are visible, and Enter picks suggestions and checkpoint rows. |

## API spot checks (optional)

```bash
# validation → 400 with a message
curl -s -X POST localhost:8000/api/plan -H 'Content-Type: application/json' \
  -d '{"origin":"Chicago","destination":"Chicago","departure":"2030-01-01T00:00:00Z","load_lbs":1}'

# a real plan: 3 routes, checkpoints keyed "10","25","50", recommendation per spacing
curl -s -X POST localhost:8000/api/plan -H 'Content-Type: application/json' \
  -d "{\"origin\":\"Chicago, IL\",\"destination\":\"Denver, CO\",\"departure\":\"$(date -u -v+1H +%Y-%m-%dT%H:00:00Z)\",\"load_lbs\":42000}" \
  | python3 -c "import sys,json;d=json.load(sys.stdin);print(len(d['routes']),[len(d['routes'][0]['checkpoints'][k]) for k in ('10','25','50')],d['recommendation']['25']['reason'])"
```
