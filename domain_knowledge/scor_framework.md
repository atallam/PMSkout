# SCOR Framework — Domain Knowledge Reference
*Supply Chain Operations Reference Model v12.0 (APICS/ASCM)*

## Overview
The SCOR model defines six process types. Every supply chain recommendation must map to at least one domain. Unmapped recommendations lack grounding and should be flagged.

---

## PLAN
**Scope:** Demand management, S&OP, inventory optimization, capacity planning, supply planning.

### Key Risk Signals
- Recommendations that improve planning accuracy **without addressing data quality** fail within 12 months (garbage in, garbage out)
- S&OP improvements require **cross-functional buy-in** (Sales, Finance, Ops) — tech alone cannot fix alignment gaps
- Demand sensing initiatives assume **clean, granular POS data** — validate data availability before scoping
- Capacity planning changes in **constrained industries** (pharma, semi) have 12–24 month lag before impact

### Minimum Viable Context
- Forecast accuracy baseline (MAPE or bias)
- Current planning cycle cadence (weekly/monthly/quarterly)
- ERP/planning system in use (SAP APO, o9, Kinaxis, etc.)
- Demand volatility profile (stable / seasonal / lumpy / new product)

### Red Flags for Evaluation
- Promising >20% forecast accuracy improvement in year 1 without historical baseline
- Inventory optimization that ignores service level tradeoff
- S&OP process change without executive sponsorship confirmation

---

## SOURCE
**Scope:** Supplier selection, procurement, contract management, purchase order management, tail spend, supplier risk.

### Key Risk Signals
- Supplier consolidation below **3 qualified sources** for critical components creates catastrophic risk
- Payment term extension beyond **90 days** risks supplier financial distress in SME-heavy supply bases
- Contract compliance improvements require **ERP/CLM system integration** — manual compliance is unsustainable
- Tail spend programs typically yield **3–7% savings** — claims above this need methodology scrutiny

### Minimum Viable Context
- Current supplier base size and concentration
- Critical vs. non-critical category classification
- Existing contract management maturity
- Supplier financial health profile

### Red Flags for Evaluation
- Single-source dependency without dual-source qualification plan
- Supplier performance improvement without SLA/KPI definition
- Procurement automation without ERP integration path

---

## MAKE
**Scope:** Production scheduling, manufacturing execution, quality, WIP management, asset utilization.

### Key Risk Signals
- OEE (Overall Equipment Effectiveness) improvements > 15% in year 1 are rarely achievable without major capex
- Quality control digitization requires **sensor/IoT infrastructure** that is often missing in legacy plants
- Production scheduling optimization requires **real-time WIP visibility** — batch ERP updates are insufficient

### Minimum Viable Context
- Current OEE baseline
- Production scheduling system (MES, APS, or manual)
- Quality defect rate baseline
- Maintenance regime (reactive vs. predictive)

### Red Flags for Evaluation
- Make improvements without addressing upstream sourcing or downstream delivery constraints
- Automation recommendations without labor reskilling plan

---

## DELIVER
**Scope:** Order management, warehouse operations, transportation, last-mile, trade compliance, customs.

### Key Risk Signals
- Last-mile cost reduction often **shifts cost to customer experience** — validate NPS/CSAT impact
- Customs compliance technology requires **country-specific HS code** database maintenance (high ongoing cost)
- Carrier consolidation below **2 alternatives per lane** creates service disruption risk
- Warehouse automation ROI assumes **consistent SKU mix and volume** — validate with 3 years of volume data

### Minimum Viable Context
- Transportation mode mix and lane coverage
- Current WMS/TMS in use
- Trade lanes and customs complexity
- Last-mile model (owned fleet / 3PL / carrier)

### Red Flags for Evaluation
- Transportation cost reduction without service level impact model
- Warehouse automation without volume stability analysis
- Cross-border compliance without local legal review

---

## RETURN
**Scope:** Reverse logistics, warranty management, repairs/MRO, refurbishment, returns processing.

### Key Risk Signals
- Warranty fraud detection requires **historical claims data** of at least 2 years to build reliable models
- Reverse logistics network design is often **5–10x more complex** than forward logistics
- Repair turnaround improvement requires **parts availability** — don't optimize scheduling without fixing parts

### Minimum Viable Context
- Return rate baseline by category
- Current reverse logistics network (owned vs. 3PL)
- Warranty claim rate and fraud rate estimates
- Repair cycle time baseline

### Red Flags for Evaluation
- Returns reduction without root cause analysis of why returns occur
- Repair cost reduction without parts availability assessment

---

## ENABLE
**Scope:** Business rules, performance management, data management, regulatory compliance, risk management, fraud detection.

### Key Risk Signals
- Fraud detection ML models require **labeled training data** — if fraud cases haven't been tracked historically, model accuracy will be low
- Regulatory compliance changes have **mandatory timelines** that override business prioritization
- Risk management improvements must address **Tier 2 and Tier 3 supplier visibility** — Tier 1 visibility alone is insufficient for resilience

### Minimum Viable Context
- Data governance maturity
- Regulatory framework applicable (FDA, EU MDR, CTPAT, etc.)
- Current risk register and escalation process
- Historical fraud/exception incident rate

### Red Flags for Evaluation
- Risk management without Tier 2 supplier mapping
- Compliance technology without legal/regulatory team involvement
- Fraud detection without historical labeled dataset

---

## Cross-Domain Risk: Tradeoff Matrix
Every recommendation that improves one dimension typically degrades another:

| If you improve... | Watch for degradation in... |
|---|---|
| Cost (lower) | Service level, resilience |
| Lead time (shorter) | Cost (expediting), quality |
| Inventory (lower) | Service level, fill rate |
| Supplier count (fewer) | Resilience, negotiation leverage |
| Forecast horizon (longer) | Accuracy, planning agility |
| Automation | Change management, flexibility |

**Rule:** Any recommendation that claims to improve two or more dimensions simultaneously requires exceptional evidence or a phased implementation plan.
