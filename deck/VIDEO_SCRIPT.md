# ClaimRight: 3-minute demo video script

**Tabs to open before recording (in this order)**
1. Family app: https://claimright-809314822230.us-central1.run.app (reset it: Settings → tap the version 5× → RESET APP)
2. Hospital desk: https://claimright-809314822230.us-central1.run.app/hospital.html (zoom out to 80–90% so all the cards fit)
3. The deck, on the **Architecture** slide

**Warm-up (2 min before recording):** do one check and one chat question in tab 1, and pick Deluxe once in tab 2, then reload both. Keep the 3 knee PDFs on the Desktop (`claimright\demo\cases\knee_pune\`). Hard-refresh both tabs (Ctrl+Shift+R).

**Recording:** Clipchamp → Record & create → Screen + mic. Cut the waiting (checking, chat thinking) afterwards with the scissors. Export at 1080p.

---

### 0:00–0:15 · Problem (tab 1, Home screen)
"Hi, we're Team Aviti, and this is ClaimRight. When a health insurer cuts a hospital claim in India, most families never fight it, especially small cuts of two to fifty thousand rupees. The rules are hard to read, and nobody helps with claims this small."

### 0:15–0:40 · Family: upload and check (Check my claim → upload 3 PDFs → Check)
"A family uploads three documents: the hospital bill, the insurer's settlement letter and the policy. Gemini 3.8 Flash on Vertex AI reads every line. Then our rules engine checks each cut against IRDAI rules and the policy. All the rupee maths is done in code, never by the AI."

### 0:40–1:00 · Report and one cut (report → tap cut 01 → EN/हिं toggle)
"This family can claim back sixty-two thousand rupees. Every cut is marked wrong, ask the insurer, or looks right, with the exact rule and its official source, in English or Hindi."

### 1:00–1:20 · Ask ClaimRight (ASK → "Does this insurer do this to other people too?")
"Families can ask questions. This agent is built with Google's Agent Development Kit. For this question it queries BigQuery through a private MCP Toolbox, and it shows this insurer breaks the same rule far more often than others."

### 1:20–1:35 · Fight (back → Fight this cut → Pay (demo) → letter)
"To fight, the family pays two ninety-nine plus a refundable ten percent. ClaimRight writes the complaint letter and the dated next steps, up to the free Insurance Ombudsman."

### 1:35–2:25 · Hospitals: the pre-check (switch to tab 2)
"But the bigger customer is the hospital. Here ClaimRight runs **inside the hospital's billing software**, before the claim is sent."
- *Pick* **Deluxe** *in the room dropdown:*
  "The billing desk picks a Deluxe room. ClaimRight instantly warns: the room is above this patient's policy limit, so the insurer will cut thirty-seven percent of the doctor and procedure charges. Eighty-four thousand rupees at risk."
- *Click* **Switch to Twin sharing**:
  "Choose a room within the limit, or tell the patient upfront, and the risk is gone."
- *Click* **Move into OT package** *on the consumables card:*
  "Gloves and drapes billed as a separate line are something insurers commonly cut. Billed inside the OT package, they're paid. Zero rupees at risk."
- *Click* **Pre-check & submit claim**:
  "Now the claim goes out clean. Same rules engine, used upfront, so the cut never happens. And it's plain code: instant, with zero AI cost."

### 2:25–3:00 · Architecture and close (tab 3, Architecture slide)
"Everything runs on Google Cloud: Cloud Run, Gemini on Vertex AI, the Agent Development Kit, the MCP Toolbox and BigQuery, plus a BigQuery data agent in Data Studio that shows which insurers cut wrongly. We built the data side in Antigravity with the Data Agent Kit. A full family check costs about one rupee in AI. Families today, hospitals next: ClaimRight, small claims fought right. Thank you."

---

**Don't say:** that ClaimRight tells doctors what to use (it only says how an item will be **paid**), or name IRDAI's "List I–IV" or NHCX (not verified on the official sites). Say "items insurers commonly cut".
