# GigShield

**Parametric micro-insurance for quick-commerce delivery workers.**  
No claims. No paperwork. Automatic payouts when disruptions occur.

> Guidewire DEVTrails 2026 · Q-Commerce Track · Bengaluru · Phase 1

---

## Table of Contents

1. [Problem and Persona-Based Workflow](#1-problem-and-persona-based-workflow)
2. [Parametric Triggers and System Design](#2-parametric-triggers-and-system-design)
3. [Weekly Premium Model](#3-weekly-premium-model)
4. [AI and ML Integration](#4-ai-and-ml-integration)
5. [Adversarial Defense and Anti-Fraud Architecture](#5-adversarial-defense-and-anti-fraud-architecture)
6. [Why a Mobile App](#6-why-a-mobile-app)
7. [Tech Stack and Architecture](#7-tech-stack-and-architecture)
8. [Development Plan](#8-development-plan)

---

## 1. Problem and Persona-Based Workflow

### The Income Volatility Problem

Quick-commerce delivery workers in India earn between Rs. 400 and Rs. 800 per
day. Their income is not salaried. It is shift-based, hyperlocal, and entirely
contingent on conditions outside their control — rainfall, platform uptime,
road congestion, and air quality.

The disruptions that destroy a shift are short, sharp, and geographically
contained. A storm drain overflows in a 2-kilometre radius. The Zepto app goes
down for 50 minutes. A flooded street makes a dark store unreachable. In each
case, every delivery assigned to that zone stops. Income drops to zero. The
disruption is over in hours. The worker has no buffer, no employer coverage,
and no insurance product accessible to them.

Traditional insurance fails this population on three structural counts:

- Claim filing requires documentation — delivery logs, income proof, loss
  verification — that gig workers cannot reliably produce
- Settlement cycles of days or weeks are useless when the financial need is
  immediate
- Indemnity-based models require verifying actual loss per worker, which
  creates unresolvable adverse selection and moral hazard at scale

Parametric insurance eliminates all three. The payout is triggered by an
objective external event — not by the worker's reported loss. When the trigger
fires, every eligible policyholder in the affected zone receives a predetermined
payout automatically.

### Why Quick-Commerce and Not Food Delivery

This distinction is architectural, not cosmetic.

| Factor | Food Delivery (Zomato / Swiggy) | Quick-Commerce (Zepto / Blinkit) |
|---|---|---|
| Zone structure | City-wide, no fixed assignment | Hyperlocal dark store, 2–3 km radius |
| Deliveries per shift | 8–12 | 40–80 |
| Disruption impact | Partial — rain slows, does not stop | Near-total — one flooded street ends the shift |
| Trigger precision | Low basis risk difficult to achieve | High — disruption is binary and verifiable |
| Premium cycle fit | Weekly possible but loose | Weekly — exact match |

Food delivery workers operate city-wide with no fixed zone. A parametric
trigger must verify their location at event time — which requires runtime GPS
checks that are manipulable. The trigger fires imprecisely and basis risk
(the gap between trigger and actual loss) is high.

Quick-commerce workers are permanently assigned to a specific dark store at
enrollment. Zone assignment is a database record — verified once, stored
permanently. The trigger evaluates whether a disruption occurred in Zone X.
Every worker whose `home_store_id = Zone X` receives a payout. No runtime
location check is needed. The trigger is precise. Basis risk is low. The
parametric model fits correctly.

### Worker Personas

**Persona 1 — Ravi, Koramangala Zone 4-B**  
Age 27. Zepto delivery partner for 14 months. Earns approximately Rs. 620/day
on good days. Has no savings buffer. During the June 2023 Bengaluru flood, lost
three full days of income with no recourse. Pays Rs. 28/week for GigShield
coverage at the Rs. 600/day tier. When a ZDI event fires in his zone, he
receives Rs. 420 within the same day — no action required on his part.

**Persona 2 — Lakshmi, HSR Layout Zone 2**  
Age 34. Blinkit partner, primary household earner. Declares Rs. 800/day income
tier. Enrolled during pre-monsoon after checking the 5-day forecast on the
dashboard. Locked in at Rs. 35/week before the risk-adjusted price rose to
Rs. 44. Has received two payouts in six weeks. Trust score: high. Eligible for
loyalty discount at renewal.

**Persona 3 — Arjun, Whitefield Zone 7**  
Age 22. New Zepto partner, 3 weeks enrolled. Declares Rs. 400/day tier. Pays
Rs. 19/week. His policy has a 48-hour look-back exclusion active from
enrollment — payouts are deferred for the first two days to prevent adverse
selection abuse. On day 3, coverage is fully active.

### Full System Lifecycle

```
1. ONBOARDING
   Worker downloads app → completes Aadhaar KYC → Platform API verifies
   real driver account and zone assignment → home_store_id stored in DB

2. POLICY PURCHASE
   Worker selects income tier (Rs. 400 / Rs. 600 / Rs. 800 per day)
   System calculates WeeklyPremium → worker pays via UPI
   Policy record created with active status and enrollment timestamp

3. DISRUPTION DETECTION
   APScheduler polls every 15 minutes
   ZDI computed per zone from weather, outage, traffic, AQI signals
   If ZDI >= 25: disruption event created for that zone

4. PAYOUT CALCULATION
   System queries: active policies where home_store_id = affected zone
   For each eligible worker:
     payout = DailyIncome × CoverageRatio × PayoutRate × (AffectedHours / WorkingHours)
   Fraud checks run (deterministic rules + Isolation Forest flag)

5. PAYOUT EXECUTION
   Composite fraud score < 25: full payout within 15 minutes via UPI
   Score 26–55: 50% immediate, 50% held 24 hours
   Score 56–75: full hold, manual review within 24 hours
   Score > 75: auto-reject with appeal option

6. AUDIT AND TRANSPARENCY
   Every trigger, inference, and payout decision logged immutably
   Worker sees: ZDI at trigger time, payout amount, income recovery score
   Dashboard shows: "This payout covers 73% of estimated lost income
   for this disruption window"
```

---

## 2. Parametric Triggers and System Design

### Why Parametric Over Claims-Based Insurance

In a claims-based model, the worker files a claim, documents the loss, and
waits for verification and settlement. For a gig worker earning Rs. 600/day,
this model is unusable. They cannot produce documentation. They cannot wait
days. And at scale, verifying actual income loss for thousands of workers after
every monsoon event is operationally impossible.

In a parametric model, the trigger is an external objective measurement
independent of the policyholder's behavior. Rainfall at a weather station
cannot be influenced by the worker. A platform API going offline cannot be
influenced by the worker. When the trigger fires, every eligible policyholder
receives a predetermined payout — no filing, no verification, no delay.

The tradeoff is basis risk: the gap between the trigger firing and the actual
loss experienced by an individual worker. GigShield minimises basis risk through
zone granularity (2–3 km radius dark store zones) and the platform outage
trigger, which is directly correlated with zero income for every worker on that
platform in that zone.

### Zone Disruption Index

The ZDI is a weighted composite score computed every 15 minutes for each zone:

```
ZDI = Rain×0.45 + Outage×0.30 + Traffic×0.15 + AQI×0.10
```

Each component is normalised to a 0–100 scale before weighting.

**Why these weights:**

- Rainfall (0.45): The primary driver of delivery impossibility in Bengaluru.
  Heavy rainfall floods feeder roads, makes bikes undriveable, and creates
  standing water at dark store access points. It is causal, not merely
  correlated, with income loss.

- Platform outage (0.30): A Zepto or Blinkit app outage means zero order
  assignment regardless of weather. This is a direct income cut with a
  verifiable, objective signal — the platform's own StatusPage. It is
  GigShield's most defensible trigger because it is binary, timestamped, and
  entirely independent of the worker.

- Traffic congestion (0.15): Secondary amplifier. Congestion alone rarely stops
  deliveries but extends trip time enough to reduce shift income materially.
  Weighted lower because it is a partial disruption, not a full one.

- AQI (0.10): Extreme AQI events (above 300) create safety-based delivery
  stoppages. Weighted lowest because severe AQI events in Bengaluru are
  infrequent compared to rainfall.

These initial weights are assumptions used at launch. The ML layer (see Section
4) learns the correct weights from historical disruption outcome data.

### Trigger Threshold and Payout Ladder

A ZDI score of 25 or above triggers the payout chain. Below 25, the event is
logged but no payout fires.

```
ZDI 25–50   →  40% of declared daily income
ZDI 50–75   →  70% of declared daily income
ZDI 75–100  →  100% of declared daily income
```

### Prorated Payout Formula

```
EventPayout =
    DailyIncome
  × CoverageRatio
  × PayoutRate         (from ladder above)
  × (AffectedHours / WorkingHours)
```

Where `AffectedHours` is the duration the ZDI remained above threshold, and
`WorkingHours` is standardised at 10 hours for Bengaluru Q-commerce.

### Weekly Payout Cap

```
WeeklyPayoutCap = CoverageRatio × DailyIncome × 5
```

Caps at 5 insured working days regardless of the 7-day policy week. This is
the insurer's maximum exposure per policy per week.

| Tier | Max Weekly Payout |
|---|---|
| Rs. 400/day | Rs. 1,600 |
| Rs. 600/day | Rs. 2,400 |
| Rs. 800/day | Rs. 3,200 |

---

## 3. Weekly Premium Model

### Why This Formula and Not Something Simpler

**Rejected: Flat premium**  
A flat Rs. 25/week for every worker in every zone in every season ignores all
risk variation. It overcharges workers in dry zones and undercharges workers in
flood-prone zones. The pool either underreserves during monsoon or overprices
during dry months. It is not a pricing model — it is an arbitrary number.

**Rejected: Naive income-scaled formula**  
`Premium = DailyIncome × SomeRate` ignores disruption frequency, severity,
and duration entirely. It assumes every rupee of income faces the same risk
probability, which is false. A Rs. 600/day worker in a low-disruption zone
should not pay the same rate as a Rs. 600/day worker adjacent to a storm drain.

**Rejected: Full payout rate applied directly**  
`Premium = DailyIncome × AvgPayoutRate × AvgDisruptionDays` double-counts
frequency if `AvgPayoutRate` is computed from the full ZDI distribution
including non-disruption days where payout is zero. Monsoon premiums inflate
40–60% above actuarially fair levels. This is a structural error, not a
calibration error.

**The correct approach: Frequency-Severity-Duration decomposition**

Actuarial pricing requires separating three independent dimensions of loss:

- Frequency: how often does a disruption occur?
- Severity: when it occurs, how large is the payout?
- Duration: when it occurs, how long does it last?

Multiplying these three dimensions against the insured income gives the
expected weekly loss. Applying loading factors gives the premium.

### Derivation

Start from first principles:

```
ExpectedLoss = Probability(disruption) × Impact(disruption)
```

Expand probability into a weekly frequency:

```
Probability(disruption in a given week) = SeasonalDisruptionDays / 7
```

Expand impact into income fraction:

```
Impact = DailyIncome × CoverageRatio × ConditionalPayoutRate × AvgHoursFraction
```

Combine:

```
ExpectedWeeklyLoss =
    DailyIncome
  × CoverageRatio
  × (SeasonalDisruptionDays / 7)
  × ConditionalPayoutRate
  × AvgHoursFraction
```

Apply loadings:

```
WeeklyPremium =
    ExpectedWeeklyLoss
  × CorrelationLoad
  × LoadingFactor
  + AdminFee
```

### Parameter Definitions

| Parameter | Definition | Value | Source |
|---|---|---|---|
| `DailyIncome` | Worker's declared income tier | Rs. 400 / 600 / 800 | Declared at onboarding, verified against UPI history |
| `CoverageRatio` | Fraction of declared income that is insured | 0.80 | Fixed platform parameter |
| `SeasonalDisruptionDays` | Expected disruption days per week for this zone and season | Dry: 1.0 · Pre-monsoon: 1.6 · Monsoon: 2.5 · Post: 1.3 | ML model output (see Section 4) |
| `ConditionalPayoutRate` | E[payout% given ZDI >= 25] — severity only, not frequency | 0.50 baseline | ML model output (see Section 4) |
| `AvgHoursFraction` | E[disruption hours / working hours given disruption] | 0.40 baseline (4hrs of 10hr day) | ML model output (see Section 4) |
| `CorrelationLoad` | Systemic simultaneity surcharge for correlated claims | 1.18 baseline | ML model output (see Section 4) |
| `LoadingFactor` | Insurer margin and opex | 1.25 | Fixed platform parameter |
| `AdminFee` | Flat weekly platform fee | Rs. 5.00 | Fixed |

### Resulting Premium Table

| Tier | Dry Season | Monsoon Peak | Within Rs. 20–80 band |
|---|---|---|---|
| Rs. 400/day | Rs. 18.5/week | Rs. 38.2/week | Yes |
| Rs. 600/day | Rs. 25.2/week | Rs. 55.6/week | Yes |
| Rs. 800/day | Rs. 31.9/week | Rs. 72.4/week | Yes |

### Why CorrelationLoad Is Not Optional

Classical insurance risk pooling assumes independent claims. If Worker A claims
and Worker B claims, the events are statistically unrelated. This allows risk
diversification across the pool.

GigShield's pool is a single city. When the monsoon arrives, every worker in
Bengaluru faces the same trigger simultaneously. Claims are not independent —
they are correlated. The pool faces not a distribution of individual claims but
a single large simultaneous draw.

Without a CorrelationLoad, the expected loss calculation understates peak
exposure and the pool is structurally undercapitalised during monsoon. The
1.18 multiplier builds a reserve surplus during normal weeks that partially
absorbs the correlated monsoon draw.

This does not fully eliminate insolvency risk. That requires reinsurance, which
is scoped for a future phase. The CorrelationLoad is an actuarial acknowledgment
of the problem and a partial structural response to it.

---

## 4. AI and ML Integration

### Why Static Parameters Are Insufficient

A static parametric system using fixed seasonal tables and hardcoded weights
has one fundamental problem: every worker in the same city in the same season
gets the same risk parameters, regardless of their zone's actual disruption
history. A zone adjacent to Bellandur Lake in Bengaluru has three times the
flood frequency of a zone on elevated ground in the same city during the same
monsoon week. A flat seasonal lookup cannot capture this.

AI is used in GigShield to replace fixed assumptions with learned, data-driven
estimates for exactly four parameters in the premium formula and one trigger
gate. Every ML component maps to exactly one formula parameter or system
decision. No ML component exists outside this structure.

### The Formula and Where ML Plugs In

```
ExpectedWeeklyLoss =
    DailyIncome                          -- declared, no ML
  × CoverageRatio                        -- fixed, no ML
  × (SeasonalDisruptionDays / 7)         -- ML: LightGBM regressor
  × ConditionalPayoutRate                -- ML: LightGBM classifier
  × AvgHoursFraction                     -- ML: gradient boosted regressor

WeeklyPremium =
    ExpectedWeeklyLoss
  × CorrelationLoad                      -- ML: linear regression
  × LoadingFactor                        -- fixed, no ML
  + AdminFee                             -- fixed, no ML
```

Additionally, the ZDI trigger gate uses a learned model to replace hardcoded
signal weights.

### ML Component 1 — SeasonalDisruptionDays (Frequency)

**File:** `engine/premium_calculator.py`

**What it replaces:** A flat seasonal lookup (Dry: 1.0, Pre-monsoon: 1.6,
Monsoon: 2.5, Post-monsoon: 1.3) applied uniformly to every zone in the city.

**Model:** LightGBM regressor

**Inputs:** Zone ID, calendar week, historical ZDI breach frequency for that
zone, IMD 5-day forecast rainfall probability, prior season disruption count
for the zone

**Target:** Number of days in the coming week where ZDI exceeded 25, derived
from synthetic historical disruption logs

**Output:** Continuous value between 0 and 7, replacing the seasonal lookup
directly in the formula

**Why this matters:** Zone-level disruption frequency is not uniform within a
city or within a season. A flood-prone zone in northeast Bengaluru may see 3.2
disruption days per week during peak monsoon while a zone on elevated ground
sees 1.4. Using the same 2.5 figure for both misprices one up and the other
down. The LightGBM regressor learns zone-specific frequency from historical
data and produces the correct input to the formula for each zone independently.

### ML Component 2 — ConditionalPayoutRate (Severity)

**File:** `engine/claims_engine.py`

**What it replaces:** A fixed 0.50 value derived from payout ladder midpoint
averaging across the full ZDI distribution.

**Model:** LightGBM classifier with three output classes (40%, 70%, 100%
corresponding to the three payout tiers)

**Inputs:** ZDI score at trigger time, season flag, time of day, zone density
class (hyperlocal dark store vs broader delivery zone), duration of prior
disruptions in the same zone

**Target:** Actual payout tier triggered in historical synthetic disruption
events

**Output:**
```
ConditionalPayoutRate = 0.40 × P(tier1) + 0.70 × P(tier2) + 1.00 × P(tier3)
```

**Why this matters:** A fixed 0.50 assumes the ZDI distribution is uniform
across zones and seasons. During monsoon peak in a flood-prone zone, the
distribution shifts heavily toward the upper tiers — the true conditional
payout rate is closer to 0.70 or above. Underestimating severity in high-risk
zones produces premiums that cannot cover expected claims. The classifier
learns zone-specific and season-specific severity distributions and prices
each zone at its true conditional severity.

### ML Component 3 — AvgHoursFraction (Duration)

**File:** `engine/claims_engine.py`

**What it replaces:** A fixed 0.40 value (4 hours of a 10-hour working day)
applied to every disruption event regardless of type or time.

**Model:** Gradient boosted regressor

**Inputs:** ZDI score at trigger onset, rate of ZDI change (rising vs falling),
rainfall intensity trajectory, platform outage duration history for the zone,
time of day at trigger onset

**Target:** Actual disruption duration in hours, binned as a fraction of a
10-hour working day

**Output:** Replaces the fixed 0.40 both in the premium formula (as expected
duration) and in the live payout formula (as actual `AffectedHours /
WorkingHours` for each event)

**Why this matters:** A platform outage beginning at 6 PM typically resolves
within 1 to 2 hours because engineering teams respond during business hours.
A rainfall event beginning at 6 PM during monsoon peak in Bengaluru can last
6 to 8 hours. Applying a flat 0.40 to both events misprices the expected
loss in opposite directions. The regressor learns duration patterns from
event type, onset time, and zone history.

### ML Component 4 — CorrelationLoad (Systemic Risk)

**File:** `engine/premium_calculator.py`

**What it replaces:** A flat 1.18 surcharge applied uniformly regardless of
event type, season, or pool composition.

**Model:** Linear regression — chosen deliberately for interpretability and
auditability, as this parameter feeds directly into a financial formula that
must be explainable to a carrier partner or regulator

**Inputs:** Season flag, number of active policies in the zone, ratio of
zone-level to city-level disruption frequency, proportion of ZDI score
explained by rainfall vs platform outage

**Target:** Observed simultaneous claim rate as a fraction of active policies
during historical disruption events

**Output:** Float in the range 1.10 to 1.25:
```
Dry season:     1.10
Pre-monsoon:    1.18
Monsoon peak:   1.24
```

**Why this matters:** A city-wide monsoon event produces near-total
simultaneous claims across the pool. A localised platform outage on one dark
store cluster produces partial simultaneous claims in one zone. Applying a
flat 1.18 to both overcharges workers during outage events and undercharges
during monsoon events. The linear regression separates these two correlation
regimes. A linear model is used rather than a complex one because this output
is a financial multiplier that must be auditable.

### ML Component 5 — ZDI Scorer (Trigger Gate)

**File:** `engine/zdi_scorer.py`

**What it replaces:** Hardcoded weights (Rain: 0.45, Outage: 0.30,
Traffic: 0.15, AQI: 0.10) that are informed assumptions at launch.

**Model:** LightGBM classifier

**Inputs:** Rainfall intensity, platform outage status, traffic congestion
drop percentage, AQI reading

**Target:** Binary — did a qualifying disruption event occur in this zone on
this observation? Derived from synthetic historical disruption logs.

**Output:** Learned feature importances replace the hardcoded weights

**Why this matters:** The ZDI threshold of 25 is the gate that determines
whether any payout chain fires at all. If the weights are wrong, the gate
misfires. False positives drain the pool. False negatives mean workers with
genuine income loss receive nothing. The LightGBM model ensures weights
reflect actual disruption outcomes rather than intuition.

### ML Component 6 — Fraud Detection

**File:** `engine/fraud_checker.py`

Three deterministic rules run first:

| Rule | What it blocks |
|---|---|
| Worker GPS active during trigger window | Worker was delivering — income loss did not occur |
| Policy age under 48 hours | Look-back exclusion — blocks last-minute adverse selection |
| Income tier declared vs UPI history mismatch | Tier misrepresentation at onboarding |

One ML flag runs after the deterministic rules pass:

**Model:** Isolation Forest on claim frequency features per worker

**Inputs:** Claim count per worker, claim frequency relative to zone average,
time between policy purchase and first claim

**Output:** Anomaly score — flagged workers are held for manual review, not
auto-rejected

**Why Isolation Forest and not a classifier:** There are no labelled fraud
cases at launch. The Isolation Forest is unsupervised — it identifies
statistical outliers without requiring training labels, which makes it the
correct model for a system with no fraud history.

### ML Summary Table

| ML Component | Formula Parameter | Model | File |
|---|---|---|---|
| Disruption frequency estimation | `SeasonalDisruptionDays` | LightGBM regressor | `premium_calculator.py` |
| Disruption severity estimation | `ConditionalPayoutRate` | LightGBM classifier | `claims_engine.py` |
| Disruption duration estimation | `AvgHoursFraction` | Gradient boosted regressor | `claims_engine.py` |
| Dynamic correlation loading | `CorrelationLoad` | Linear regression | `premium_calculator.py` |
| ZDI weight learning | Trigger gate (ZDI >= 25) | LightGBM classifier | `zdi_scorer.py` |
| Fraud anomaly detection | Pre-payout gate | Isolation Forest | `fraud_checker.py` |

---

## 5. Adversarial Defense and Anti-Fraud Architecture

### The Central Insight

> GigShield does not check GPS coordinates at claim time. Not at any step
> of the payout process. This is not a gap. It is proof that the architecture
> is correct.

Payout eligibility in GigShield is a database record set at enrollment — not a
runtime location check. When a disruption fires in Zone X, the system queries:
which workers have an active policy with `home_store_id = Zone X`? Every
matching worker receives a payout. The GPS question is structurally irrelevant.

A GPS spoofing attack manipulates coordinates reported at the moment a system
checks location. GigShield never checks location at that moment.

- A fraudster spoofing GPS during a disruption event in their own zone
  accomplishes nothing — they would have received the payout regardless.
- A fraudster spoofing GPS to appear in a different zone also accomplishes
  nothing — the system routes payouts by `home_store_id`, not runtime location.

To defeat GigShield's payout system, a fraudster would need to change a
database record. That requires defeating the enrollment verification layer.
There is no GPS to spoof.

### Why GPS Matters for Food Delivery But Not for GigShield

Food delivery drivers (Zomato, Swiggy) operate city-wide with no fixed zone
assignment. A parametric product on this model must check GPS at event time —
it is the only way to know which drivers were in the affected area. That signal
is manipulable in under three minutes on any Android device using a free mock
location app. The entire fraud defense collapses at the software layer.

Quick-commerce workers are assigned to a specific dark store at enrollment.
That assignment is verified against the Platform API once and stored. Runtime
GPS adds nothing because zone membership is already known. The structural
difference between these two models is the reason GigShield chose Q-commerce.

### Real Fraud Surface: Enrollment and Policy Management

Every material fraud vector in GigShield is an enrollment-time or
policy-management problem.

| Fraud Vector | Description | Defense |
|---|---|---|
| Fake enrollment | Creating a fictitious driver account in a high-risk zone | Aadhaar KYC + Platform API verification of real active driver account |
| Adverse selection | Enrolling after seeing a forecast to collect next-day payout | 48-hour look-back exclusion on all new policies |
| Policy stacking | Enrolling on multiple platforms to collect multiple payouts per event | Aadhaar-linked unique policy ID — one active policy per person |
| Zone misrepresentation | Claiming assignment to a higher-risk zone | Platform API cross-check at enrollment confirms real `home_store_id` |

### Hardware-Level Spoofing Defense (Extension — Not Core System)

For platforms where runtime GPS verification is unavoidable — food delivery
and e-commerce models — a hardware-level defense architecture is available
that shifts verification from the manipulable software layer to physical signals
that no application can reach.

**Signal 1 — GNSS Satellite Signal Strength**

Every Android device contains a GPS chipset that receives signals from GNSS
satellites. Signal strength is measured as Carrier-to-Noise density (C/N0)
in dB-Hz. This reading comes from the hardware modem — not the software
location layer. A mock location app has no access to it.

| Physical Environment | C/N0 Range (dB-Hz) | Fraud Signal |
|---|---|---|
| Outdoors, clear | 35–50 | None |
| Outdoors, heavy rain | 25–38 | None — consistent with rain per ITU-R P.838 |
| Indoors | 0–20 | High if GPS claims outdoor road location |
| Spoofed from indoors | 0–20 (hardware truth) | Critical — GPS and modem contradict |

**Signal 2 — Cellular Tower Transition Detection**

Physical movement causes a device to cross tower boundaries and hand off to
new cell towers — readable via Android's `TelephonyManager` API. A fraudster
scripting GPS movement at home shows zero tower transitions while GPS reports
active travel. Zero tower transitions at GPS velocity above 15 km/h is
physically impossible for a genuine mobile driver. Reference database:
OpenCelliD India (MCC 404/405, approximately 8 million towers, free).

**Signal 3 — WiFi BSSID Geographic Fingerprinting**

Every WiFi router broadcasts a unique hardware identifier (BSSID) that is
fixed to the router. Any device can passively scan visible BSSIDs within
approximately 50 metres. At enrollment, the app records the BSSID set visible
from the worker's assigned dark store. A driver claiming to be at their dark
store while at home shows zero BSSID overlap with the stored fingerprint.
GPS coordinates can be fabricated. The set of physical routers visible from
a location cannot be. Reference: WiGLE API for Indian cities (free tier).

**Composite Fraud Score**

| Signal | Weight | Primary Fraud Pattern |
|---|---|---|
| GNSS SNR Profile | 25% | Indoor spoofing during claimed outdoor session |
| Cell Tower Transitions | 25% | Scripted GPS movement |
| WiFi BSSID Match Rate | 20% | Dark store anchor spoofing |
| Server Ping Coverage + Velocity | 15% | Retroactive log injection |
| Behavioural Patterns | 15% | Adverse selection, collusion rings |

**Adjudication Tiers**

| Score | Decision | Action |
|---|---|---|
| 0–25 | Auto-approve | Full payout within 15 minutes |
| 26–55 | Soft flag | 50% immediate, 50% held 24 hours |
| 56–75 | Manual review | Full hold, human adjudicator within 24 hours |
| 76–100 | Auto-reject | No payout, appeal option, account flagged |

**Community Validation**

If the majority of workers in a zone show similar anomalous readings during
the same event, the system classifies this as a shared environmental condition
and releases held payouts automatically. Individual anomaly resembles fraud.
Collective anomaly resembles weather. The system distinguishes between them.

### UX Principle

Honest workers should never be harassed by fraud systems. No worker is hard-
rejected by a single signal. Flags result in delayed review, not rejection.
Appeals are available for all auto-rejects. The default assumption is that a
worker with an active policy in an affected zone is a legitimate claimant.

---

## 6. Why a Mobile App

GigShield is a mobile-first product. This is not a UX preference — it is
a system architecture requirement.

**Worker behavior:** Quick-commerce delivery workers do not use desktops.
They operate entirely on smartphones during shifts. Policy purchase,
dashboard access, and payout notifications must be available on a device
that fits in a delivery bag.

**Device signal access:** The fraud defense architecture described in
Section 5 — GNSS SNR attestation, cellular tower transition detection,
WiFi BSSID fingerprinting — requires access to hardware-level signals
that are available only through native mobile APIs. These signals cannot
be accessed from a web browser. A web-only product cannot implement this
defense layer.

**Real-time push notifications:** When a ZDI event fires in a worker's
zone, the worker should know within minutes. Push notifications via
Firebase Cloud Messaging (FCM) are reliable and free. Browser-based
notifications require the browser to be open and are unreliable on mobile
networks.

**UPI payment integration:** Workers pay premiums and receive payouts via
UPI. Native UPI deep-linking from a mobile app provides a seamless one-tap
payment experience. Web-based UPI redirect flows have significantly higher
dropout rates on low-end Android devices.

**Offline resilience:** Bengaluru delivery zones can have intermittent
connectivity. A native app can cache the worker's policy status, zone
assignment, and recent payout history locally and sync when connectivity
returns. A web app cannot do this reliably.

---

## 7. Tech Stack and Architecture

### Stack

| Layer | Technology | Why |
|---|---|---|
| Frontend | Next.js + Tailwind CSS | Server-side rendering for fast initial load on slow connections; Tailwind for rapid UI iteration without a design system overhead |
| Backend | FastAPI + Uvicorn | Async request handling by default — essential when 15-minute scheduler events trigger simultaneous payout processing for multiple zones |
| Database | PostgreSQL + SQLAlchemy + Alembic | Relational guarantees for financial data; foreign key constraints enforce policy-to-payout integrity; Alembic for auditable schema migration history |
| Cache and State | Redis | Sub-millisecond reads for ZDI state per zone; prevents redundant API polling within a 15-minute window; pub/sub support for future event-driven architecture |
| Scheduler | APScheduler | Lightweight in-process scheduler for the 15-minute disruption detection loop; no external queue dependency for Phase 1 |
| Map Layer | Leaflet.js + GeoJSON | Zone-level disruption heatmap; open-source with no API cost; GeoJSON zone boundaries load once and are cached |
| Payments | Razorpay (sandbox) | UPI payout API; sandbox environment for demo; production-ready with the same integration |
| Infrastructure | Docker + Docker Compose | Single-command environment setup; all services (backend, frontend, PostgreSQL, Redis) run as a composed stack with no host-level dependencies |

### System Architecture

```
Mobile App (React Native) / Web Dashboard (Next.js)
                    |
                    | REST API
                    v
              FastAPI Backend
                    |
        ____________|____________
        |            |           |
   Policy API   Disruption    Payout API
   /policy      Engine        /payout
        |            |           |
        v            v           v
   PostgreSQL    APScheduler  fraud_checker.py
   (policies,    (15-min)     claims_engine.py
    payouts,          |       payout_service.py
    audit_log)        v
                  ZDI Scorer
                      |
              ________|________
              |       |       |
           Weather  Outage  Traffic
           Adapter  Adapter  Adapter
           (mock)   (mock)   (mock)
                      |
                   Redis
                (ZDI state,
                 zone cache)
```

### Audit Log

Every trigger event, model inference, and payout decision is immutably
recorded in the `audit_log` table:

```sql
event_id        UUID PRIMARY KEY
timestamp       TIMESTAMPTZ NOT NULL
event_type      VARCHAR(50)   -- TRIGGER, FRAUD_CHECK, PAYOUT, REJECTION
zone_id         VARCHAR(20)
trigger_value   JSONB         -- raw ZDI components at event time
model_version   VARCHAR(20)   -- which model version made the inference
decision        VARCHAR(20)   -- APPROVED, FLAGGED, REJECTED
payout_amount   NUMERIC(10,2)
worker_id       UUID REFERENCES workers(id)
```

This is not optional. Insurance systems are audited. When a payout decision
is disputed, the system must reproduce the exact model inference and trigger
values that produced it.

---

## 8. Development Plan

### Phase 1 — Current (Hackathon Scope)

**Implemented:**

- Docker Compose stack: FastAPI, PostgreSQL, Redis, Next.js
- Database schema with Alembic migrations: workers, policies, events, payouts,
  audit_log
- Premium calculator with full formula implementation
- ZDI scorer with hardcoded initial weights
- Payout ladder logic and prorated payout formula
- Fraud checker: three deterministic rules + Isolation Forest flag
- Scheduler: 15-minute APScheduler loop
- Dashboard: ZDI by zone, policy status, payout history, income recovery score

**Mocked:**

- Weather adapter: synthetic rainfall data from realistic Bengaluru
  distributions (IMD historical patterns)
- Traffic adapter: synthetic congestion data
- AQI adapter: synthetic CPCB-range values
- Platform outage adapter: toggle-based outage simulation
- Payment execution: mock UPI payout with realistic settlement delay simulation
- ML models: trained on synthetic data; disclosed explicitly in all demo
  materials

**Not implemented in Phase 1:**

- Live IMD, CPCB, and platform StatusPage API integration
- Aadhaar KYC flow (requires UIDAI partnership)
- Platform API enrollment verification (requires Zepto/Blinkit agreement)
- DPDP Act 2023 consent management flow
- MLflow model registry and versioning
- Reinsurance simulation panel
- Multi-city pool (Delhi, Mumbai, Chennai)
- IRDAI-licensed carrier integration

### Phase 2 — Post-Hackathon

- Replace mock adapters with live IMD gridded rainfall, CPCB AQI, and
  OpenWeatherMap feeds
- Implement Aadhaar KYC via a licensed KYC aggregator
- MLflow integration for model versioning and inference reproducibility
- DPDP Act consent management for GPS signal collection
- Proactive forecast premium feature using IMD 5-day forecast data

### Phase 3 — Production

- IRDAI-licensed carrier partnership (Acko or Digit Insurance as the insurance
  wrapper; GigShield as the parametric trigger engine distributed via API)
- Multi-city pool expansion to reduce monsoon correlation risk structurally
- Reinsurance backstop modelling and carrier negotiation
- Full hardware-level spoofing defense implementation if platform expansion
  includes food delivery or e-commerce workers

### Regulatory Position

GigShield is a parametric trigger engine. In India, calling a product
insurance without IRDAI licensing requires a minimum Rs. 100 crore capital
base — not a startup constraint. The correct architecture for this product
is a technology platform that provides the trigger, pricing, and payout
engine while the insurance regulatory wrapper is provided by a licensed
carrier partner via API. This is how Acko, Digit, and similar InsurTech
companies operate. GigShield is designed for this model from the ground up.

---

*GigShield · Guidewire DEVTrails 2026 · Q-Commerce Parametric Income
Insurance · Bengaluru*
