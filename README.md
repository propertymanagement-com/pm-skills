# pm-skills

Packaged Claude skills for PropertyManagement.com members.

## Skills

- **property-owner-retention-radar** — weekly retention page from AppFolio exports and PM.com survey data.
- **property-owner-newsletter** — monthly owner-specific email package with merge files and review studio.

Both skills require **code execution** enabled in Claude so the Python scripts can run.

## Install

1. **Individual upload** — Download the skill zip from [GitHub Releases](https://github.com/propertymanagement-com/pm-skills/releases), then in Claude: **Customize → Skills → Upload skill**.
2. **Team / Enterprise admin** — Provision the same zip org-wide under **Organization settings → Plugins & skills**.
3. **Claude Code marketplace** — Add this repository as a marketplace, then install:

   ```bash
   claude plugin marketplace add propertymanagement-com/pm-skills
   claude plugin install property-owner-retention-radar@pm-skills
   claude plugin install property-owner-newsletter@pm-skills
   ```

   Or in a session: `/plugin install property-owner-retention-radar@pm-skills`.

Connect the PropertyManagement.com MCP connector from the Client Dashboard for survey data, org seeding, and benchmarks.

## Development

```bash
python3 -m pytest
python3 tools/check_public_safety.py .
python3 tools/package.py
```

## License

MIT — see [LICENSE](LICENSE). The PropertyManagement.com name and brand are not licensed for use outside PM.com’s programs.
