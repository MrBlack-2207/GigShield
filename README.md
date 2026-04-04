# GigShield – Phase 2: Automation & Protection

## Overview

Phase 2 of **GigShield** transforms the platform from a conceptual insurance architecture into a **working automated protection system for quick-commerce delivery workers (Zepto / Blinkit)**.

GigShield implements **parametric micro-insurance**. Instead of requiring workers to manually file claims, the system continuously monitors disruption signals (weather, traffic, outages, etc.) and **automatically calculates compensation when disruptions occur**.

This phase delivers the **complete automated pipeline**:

Worker Onboarding → Policy Purchase → Dynamic Premium Calculation → Disruption Detection → Automatic Claim Processing → Wallet Payout.

The result is a **zero-touch insurance experience**, where gig workers are protected without paperwork or manual claims.

---

# Key Capabilities Implemented

## 1. Worker Registration & Platform Mapping

Workers register with:

- Platform (Zepto / Blinkit)
- Dark store assignment
- Income tier
- Worker identifier

Each worker is linked to a **dark store and zone**, allowing the system to detect disruptions **without relying on live GPS**, reducing fraud risk and ensuring reliable event attribution.

---

## 2. Insurance Policy Management

Workers can purchase policies with flexible tenures:

- 1 month
- 3 months
- 6 months
- 12 months

Policies operate on a **weekly premium model**, keeping insurance affordable for gig workers.

### Policy Lifecycle States

- `pending_activation` (48-hour anti-fraud cooldown)
- `active`
- `inactive`
- `expired`
- `cancelled`

The cooldown prevents workers from purchasing insurance **after a disruption has already started**.

---

## 3. Dynamic Premium Calculation (ML-Informed)

Premiums are dynamically calculated using **historical disruption patterns per zone**.

A machine learning model predicts:

> **Expected weekly disruption days per zone**

This prediction feeds into the premium engine.

### Premium Inputs

- Worker income tier
- Seasonal disruption patterns
- Historical zone disruption frequency
- Coverage ratio

This ensures premiums reflect **localized operational risk**.

---

## 4. Automated Disruption Detection

The platform monitors hyper-local signals every **15 minutes**.

Signals include:

- Rain intensity
- Traffic congestion
- Platform outages
- Air quality disruptions
- Event flags (bandh, strike, curfew, lockdown)

These signals are combined into a **Zone Disruption Index (ZDI)**.

---

# ZDI Event Boost Logic

Certain events increase disruption severity.

| Event | ZDI Boost |
|------|------|
Strike | +15 |
Petrol Crisis | +20 |
Bandh | +30 |
Curfew | +40 |
Lockdown | +50 |

The final ZDI score is capped at **100**.

---

# Claim Automation Logic

GigShield uses a **parametric payout system**.

A disruption qualifies when:




ZDI ≥ 25


Once triggered, payouts are calculated automatically.

---

# Payout Formula




EventPayout =
DailyIncome
× CoverageRatio
× PayoutRate
× (AffectedHours / WorkingHours)


### Variables Explained

| Variable | Meaning |
|------|------|
DailyIncome | Worker’s average daily earnings |
CoverageRatio | Fixed at **30%** |
PayoutRate | Determined by disruption severity |
AffectedHours | Duration of disruption |
WorkingHours | Standard shift length (**10 hours**) |

---

# Severity Tiers

Disruption severity determines payout rate.

| ZDI Range | Payout Rate |
|------|------|
25 – 50 | 0.40 |
50 – 75 | 0.70 |
75 – 100 | 1.00 |

---

# Weekly Payout Cap

To ensure financial sustainability, payouts are capped weekly:




WeeklyCap = CoverageRatio × DailyIncome


This prevents excessive payouts during extreme disruptions.

---

# AI Integration in Phase 2

GigShield integrates three machine learning models.

### 1. Disruption Frequency Model
Predicts **expected disruption days per zone**.

Used for:
- dynamic premium pricing.

### 2. Disruption Duration Model
Predicts **how long disruptions last**.

Improves payout accuracy.

### 3. Disruption Severity Model
Predicts **disruption intensity tiers**.

Maps events to payout levels.

These models ensure GigShield remains:

- financially sustainable
- fair to workers
- adaptive to local operating conditions.

---

# Wallet & Automatic Payout System

When a disruption occurs:

1. Claim is generated automatically
2. Payout is computed using the parametric formula
3. Funds are credited to the worker wallet
4. Worker can withdraw instantly

All payouts are recorded through a **wallet ledger system** for transparency and auditing.

---

# End-to-End Flow Demonstrated

The Phase 2 demo showcases the complete automated protection pipeline:

1. Worker registers
2. Worker purchases policy
3. System calculates dynamic premium
4. Disruption occurs in worker's zone
5. ZDI crosses payout threshold
6. Claim is automatically triggered
7. Payout is calculated using the formula
8. Funds are credited to worker wallet
9. Worker withdraws funds

This demonstrates how GigShield provides **instant income protection without manual claims**.

---

# Impact

GigShield addresses a key challenge in the gig economy:

> **Income volatility caused by operational disruptions.**

By combining:

- Parametric insurance
- Hyper-local disruption monitoring
- Machine learning risk models
- Automated claim processing

GigShield creates a scalable insurance system tailored specifically for gig workers.
