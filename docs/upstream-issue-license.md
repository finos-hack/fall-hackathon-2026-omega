# Draft issue for finos-hack/ai-steel-thread-demo (not yet posted)

To be posted manually by the maintainer of this project at
https://github.com/finos-hack/ai-steel-thread-demo/issues/new

---

**Title:** Add a LICENSE file (e.g. Apache-2.0) so the CALM architecture can be reused

**Body:**

Hi, and thanks for the AI Steel Thread demo. The CALM architecture in `architecture/loan-approval.calm.json`, with its controls linked to FINOS AIGF mitigations and risks, is a really useful worked example of Governance-as-Code.

I'm building a small FINOS Fall 2026 Hackathon project (Track 2) that reads this architecture and produces an AIGF coverage and evidence report. While checking licensing, I noticed the repository has no LICENSE file, and GitHub shows no license for it. Without one, others can't safely copy or redistribute the architecture and control-requirement files, even as test fixtures. For now my project only references this repo by URL and commit SHA.

Would you consider adding a license? Apache-2.0 would match most FINOS code projects, but whatever the maintainers prefer is fine. If the architecture and docs should carry a different license from the code (for example CC-BY-4.0, as `finos/ai-governance-framework` uses), a note saying so would help too.

Thanks!
