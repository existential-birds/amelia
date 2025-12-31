# Licensing

Amelia Core is dual-licensed under the **Elastic License 2.0 (ELv2)** and a **Commercial License**.

## Quick Summary

| Use Case | License Required |
| --- | --- |
| **Internal use** at your company | **ELv2 (Free)** |
| **Dev tooling** & CI/CD pipelines | **ELv2 (Free)** |
| **Modifying code** for internal use | **ELv2 (Free)** |
| **Building proprietary extensions** | **ELv2 (Free)** |
| **Selling/Reselling** Amelia | **Commercial License** |
| **Hosting Amelia as a Service** (SaaS) | **Commercial License** |
| **Embedding** in a distributed paid product | **Commercial License** |

---

## Community License (ELv2)

The source code is available under the **Elastic License 2.0 (ELv2)**. This is a permissive "source-available" license that allows for broad freedom of use, with one specific restriction on Managed Services.

**Under ELv2, you are FREE to:**

* **Use** Amelia for any internal business purpose.
* **Modify** the source code to fit your needs.
* **Integrate** Amelia into your internal build, test, and deployment systems.
* **Distribute** Amelia as part of a larger work, provided you do not violate the Managed Service restriction.

**The Limitation (No Managed Services):**
You may **not** provide the software to third parties as a hosted or managed service, where the value of the service is derived substantially from the software itself. If you want to offer Amelia as a SaaS product to your customers, you need a Commercial License.

*See the full [suspicious link removed] file for the complete legal terms.*

---

## Commercial License

A Commercial License is required if you intend to use Amelia in a way that is restricted by the ELv2.

### Restricted Uses (Require Commercial License)

You must purchase a Commercial License if you:

1. **Offer a Managed Service:** Hosting Amelia (or a modified version) and allowing third parties to access its features as a service (SaaS, PaaS, or API).
2. **Circumvent the License Key:** If future versions of Amelia include license-key functionality for enterprise features, bypassing this requires a license.
3. **White-label or OEM:** Selling a product where Amelia is the primary value proposition, rebranded or bundled for resale.

### Permitted Uses (No Commercial License Required)

You do **NOT** need a Commercial License for:

1. **Internal Corporate Use:** Running Amelia within your company to automate your own engineering workflows.
2. **CI/CD Pipelines:** Using Amelia to check code, generate docs, or run tests in your internal infrastructure.
3. **Consulting Services:** Using Amelia as a tool *yourself* to deliver code to a client (e.g., a contractor using Amelia to write better code for a client is permitted).
4. **Non-Production Research:** Academic or personal learning.

---

## Examples

### ✅ Allowed Under ELv2 (Free)

| Scenario | Why It's Allowed |
| --- | --- |
| **Your Company** runs Amelia on internal servers to review PRs for your engineering team. | **Internal Business Use.** You are not selling access to Amelia; you are using it to improve your own operations. |
| **A Developer** forks Amelia, adds a new feature, and uses it to build their personal website. | **Personal Use.** |
| **An Enterprise** integrates Amelia into their proprietary internal developer platform (IDP). | **Internal Tooling.** As long as the IDP is for employees, not sold to external customers as a hosted service. |
| **A Consultant** uses Amelia to generate documentation for a client's project. | **Professional Services.** The consultant is selling their labor/output, not the software service itself. |

### ❌ Requires Commercial License

| Scenario | Why It Requires License |
| --- | --- |
| **Startup X** launches "BetterCodeReview" which wraps Amelia in a UI and charges $10/month. | **Managed Service.** They are selling access to Amelia's functionality as a service. |
| **Cloud Provider Y** adds "Amelia-as-a-Service" to their marketplace. | **Managed Service.** |
| **Company Z** embeds Amelia into their paid IDE software and markets it as an "AI Feature." | **Embedding/Redistribution.** While ELv2 allows some distribution, embedding it as a core value driver in a closed product is best covered by a commercial agreement to ensure support and warranty. |

---

## FAQ

### Is this Open Source?

Amelia is **Source Available**. The ELv2 license is extremely permissive and aligns with the freedoms of open source (view, modify, use) for the vast majority of users. However, because it restricts the "Managed Service" use case, it does not meet the strict OSI definition of "Open Source."

### My company has a strict "No AGPL" policy. Can we use this?

**Yes.** ELv2 is not a "copyleft" license like the AGPL. It does not force you to open-source your own proprietary code or internal modifications just because you use Amelia. You can keep your internal modifications private.

### Can I fork Amelia?

Yes, you can fork the repository and modify it. However, your fork must also be licensed under ELv2 (or a compatible license), meaning the "No Managed Service" restriction travels with the fork.

### What if I am building an internal tool for my employer?

You are 100% covered by the free ELv2 license. You do not need to ask for permission or pay a fee to use Amelia for your employer's internal engineering work.

## Contact

For commercial licensing inquiries or to request a dedicated support contract, email: **legal@existentialbirds.com**