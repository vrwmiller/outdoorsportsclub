# proposal.md

## Objective

To architect a secure, AWS-hosted digital ecosystem for the **Outdoor Sports Club**. This project replaces legacy infrastructure with a high-performance hub that centralizes member services and streamlines on-site operations using stable, "managed" technologies.

## 1. AWS Serverless Foundation

* **Managed Hosting:** **AWS Amplify** handles front-end and back-end logic, providing automated CI/CD and SSL certificates with no manual server patching required.
* **Elastic Data:** **Amazon Aurora Serverless (v2)** scales the database instantly based on demand, ensuring performance during peak renewal seasons while dropping to near-zero cost during inactive periods.
* **Scalability:** Automatically handling traffic spikes during annual membership renewal windows without manual intervention.

## 2. Multimodal Member Engagement

* **Social Identity Integration:** Members log in on personal devices using Google or Facebook via **AWS Cognito** for account management, training progress, and annual dues.
* **Tokenized Kiosk Access:** Range-side tablets use a secure **Kiosk Token** to allow instant, scan-based check-ins without requiring a personal social login on shared hardware.
* **Technical Continuity:** Implementation of a **Webmaster (Level 6)** role to manage system health, device pairing, and secure account recovery protocols.

## 3. Fiscal Security & Cash Management

* **Cashless-First Logic:** Integrating secure, mobile-friendly payment processing (NFC/Tap-to-Pay) for guest fees and consumables at the point of activity.
* **Risk Mitigation:** Reducing the volume of physical cash on-hand at remote facilities to lower the profile for potential theft and simplify financial auditing through an immutable digital ledger.

## 4. Compliance & Safety

* **Automated Rule Enforcement:** System-level validation of membership status and training credentials before granting range access.
* **Liability Management:** Digitizing the waiver process with automated expiration tracking to ensure 100% legal coverage for all active participants.

## 5. Range Safety

A safe firing line requires a **Range Safety Officer (RSO)**'s undivided attention. Under the current paper-based process, **RSOs** are routinely pulled away from watching the line to collect guest fees, verify paper waivers, and manually log check-ins — each interruption is a window for a safety incident.

The kiosk-first design shifts all of these tasks to the member or guest at the tablet before they step onto the range:

* **Uninterrupted Supervision:** Check-in, waiver verification, and payment are completed at the kiosk. By the time a person reaches the firing line, their credentials and waiver status have already been confirmed by the system — the **RSO** does not need to leave their post.
* **Training-Level Gating:** The system refuses check-in for a range that exceeds a member's verified training level, removing a class of safety decisions that currently relies on an **RSO** recognizing a member by face or badge.
* **Real-Time Range Status:** **RSOs** (Level 4 and above) can open and close ranges from the kiosk or **Admin Portal**. A closed range cannot be checked into — the system enforces it, not the **RSO**'s verbal instruction alone.
* **Mandatory Checkout:** Range users must scan out when leaving. This gives the **RSO** an accurate, real-time count of who is on each range without manual headcounts.
