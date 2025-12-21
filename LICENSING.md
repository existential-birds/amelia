# Licensing

Amelia Core is dual-licensed under the **Mozilla Public License 2.0 (MPL-2.0)** and a **Commercial License**.

## Quick Summary

| Use Case | License Required |
|----------|------------------|
| Internal use at your company | MPL-2.0 (free) |
| Dev tooling, CI/CD pipelines | MPL-2.0 (free) |
| Building proprietary extensions | MPL-2.0 (free) |
| Selling Amelia or derivatives | Commercial License |
| Hosting Amelia as a service | Commercial License |
| Embedding in paid products | Commercial License |

## Open-Source License (MPL-2.0)

The source code is available under the [Mozilla Public License 2.0](LICENSE). Under MPL-2.0, you can:

- Use Amelia for any purpose, including commercial internal use
- Modify the source code
- Distribute modifications (modifications to MPL-licensed files must remain MPL-licensed)
- Create proprietary extensions in separate files
- Combine Amelia with proprietary code in a "Larger Work"

See the full [LICENSE](LICENSE) file for the complete terms.

## Commercial License

A Commercial License is required for **Restricted Uses** as defined below.

### Restricted Uses (Require Commercial License)

You need a Commercial License if you:

1. **Sell or sublicense** Amelia or substantial portions of it
2. **Repackage for distribution** as a commercial product
3. **Offer as a hosted/managed service** where users interact with Amelia functionality (SaaS, PaaS, managed orchestration)
4. **Embed in a paid product** where Amelia is a material component of the value delivered
5. **Provide paid access** to Amelia functionality, directly or indirectly
6. **White-label or OEM** Amelia for third parties

### Permitted Uses (No Commercial License Required)

You do NOT need a Commercial License for:

1. **Internal company use** - running Amelia for your organization's own development
2. **CI/CD pipelines** - integrating Amelia into your build and test infrastructure
3. **Developer tooling** - using Amelia as a tool for your engineers
4. **Modifications for internal use** - customizing Amelia for your team
5. **Proprietary extensions in separate files** - MPL-2.0 allows this by design
6. **Integration into internal systems** - connecting Amelia to your internal tools
7. **Evaluation and testing** - trying Amelia before committing to a license
8. **Non-commercial research and education** - academic and personal learning

## Examples

### Allowed Under MPL-2.0 (No Commercial License)

| Scenario | Why It's Allowed |
|----------|------------------|
| A startup uses Amelia to automate code reviews internally | Internal use, not distributed |
| A company modifies Amelia's prompts for their codebase | Internal modifications |
| An enterprise builds a proprietary plugin that connects to their ticketing system | Extension in separate files |
| A consultancy uses Amelia to help deliver client projects | Tool usage, not resale |
| A university teaches agentic systems using Amelia | Non-commercial education |
| A developer runs Amelia in their CI pipeline | Internal dev tooling |

### Requires Commercial License

| Scenario | Why It Requires License |
|----------|------------------------|
| A company sells "DevBot Pro" which is Amelia with custom branding | Repackaging for sale |
| A SaaS platform offers "AI Code Review" powered by Amelia | Hosted service |
| A consulting firm resells Amelia as part of a "development platform" bundle | Distribution/sublicensing |
| A company embeds Amelia in their paid IDE extension | Embedding in paid product |
| A managed service provider hosts Amelia for clients | Managed service offering |
| An enterprise sells internal tools built on Amelia to other companies | Commercial distribution |

## FAQ

### Do we have to contribute back modifications?

Under MPL-2.0, you must make the source code of any modifications to MPL-licensed files available if you distribute them. Modifications kept internal do not require disclosure. Extensions in separate files can remain proprietary.

### What counts as "distribution"?

Distribution means providing the software to others outside your organization. Internal use within your company is not distribution. Offering access via a hosted service is generally treated as a form of distribution for licensing purposes.

### Does running Amelia as an internal service trigger the Commercial License?

No. If your internal teams access Amelia via an internal API or service, that's internal use. The trigger is offering the service to external customers or the public.

### Can we keep proprietary plugins?

Yes. MPL-2.0 explicitly allows "Larger Works" - you can combine Amelia with proprietary code in separate files. Only modifications to the original MPL-licensed files must remain MPL-licensed.

### What if we're uncertain about our use case?

Reach out. We're happy to clarify whether your specific situation requires a Commercial License.

### Is there a grace period for startups?

Contact us to discuss startup-friendly terms.

## Contact

For Commercial License inquiries:

- **Email**: licensing@YOURDOMAIN.com
- **GitHub**: Open an issue with the label `licensing`

For general questions about licensing, feel free to open a GitHub Discussion.

---

*This document is for informational purposes. The authoritative license terms are in the [LICENSE](LICENSE) file and any signed Commercial License agreement.*
